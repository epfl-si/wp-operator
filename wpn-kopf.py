# Kopf documentation : https://kopf.readthedocs.io/
#
# Run with `python3 wpn-kopf.py run -- --db-host mariadb-min.wordpress-test.svc --wp-php-ensure manage-plugins.php --wp-dir=/home/you/dev/wp-dev/volumes/wp/6/`
#
import argparse
import kopf
import kopf.cli
import logging
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.exceptions import ApiException
import base64
import os
import subprocess
import sys
import yaml
import re
from datetime import datetime, timezone
import time

class Config:
    secret_name = "nginx-conf-site-tree"
    saved_argv = [arg for arg in sys.argv]

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(
            prog='wpn-kopf',
            description='The WordPress Next Operator',
            epilog='Happy operating!')
        
        parser.add_argument('--wp-dir', help='The path to the WordPress sources to load and call.',
                            default="../volumes/wp/6/")   # TODO: this only makes sense in dev.
        parser.add_argument('--wp-host', help='The hostname of the WordPresses to create.',
                            default="wpn.fsd.team")       # TODO: read that from the CR instead.
        parser.add_argument('--php', help='The path to the PHP command-line (CLI) executable.',
                            default="php")
        parser.add_argument('--wp-php-ensure', help='The path to the PHP script that ensures the postconditions.',
                            default=cls.file_in_script_dir("ensure-wordpress-and-theme.php"))
        parser.add_argument('--db-host', help='Hostname of the database to connect to with PHP.',
                            default="mariadb-min")
        return parser

    @classmethod
    def load_from_command_line(cls):
        argv = cls.splice_our_argv()
        if argv is None:
            # Passing no flags to .parser() is legit, since all of them have default values.
            argv = []

        cmdline = cls.parser().parse_args(argv)
        cls.php = cmdline.php
        cls.wp_php_ensure = cmdline.wp_php_ensure
        cls.wp_dir = os.path.join(cmdline.wp_dir, '')
        cls.wp_host = cmdline.wp_host
        cls.db_host = cmdline.db_host

    @classmethod
    def script_dir(cls):
        for arg in cls.saved_argv:
            if "wpn-kopf.py" in arg:
                script_full_path = os.path.join(os.getcwd(), arg)
                return os.path.dirname(script_full_path)
        return "."  # Take a guess

    @classmethod
    def file_in_script_dir(cls, basename):
        return os.path.join(cls.script_dir(), basename)

    @classmethod
    def splice_our_argv(cls):
        if "--" in sys.argv:
            # E.g.   python3 ./wpn-kopf.py run -n wordpress-toto -- --php=/usr/local/bin/php --wp-dir=yadda/yadda
            end_of_kopf = sys.argv.index("--")
            ret = sys.argv[end_of_kopf + 1:]
            sys.argv[end_of_kopf:] = []
            return ret
        else:
            return None

# Ensuring that the "WordpressSites" CRD exists. If not, create it from the "WordPressSite-crd.yaml" file.     
def ensure_wp_crd_exists():
    config.load_kube_config()
    dyn_client = DynamicClient(client.ApiClient())
    api_instance = client.ApiextensionsV1Api()
    crd_name = "wordpresssites.wordpress.epfl.ch"

    try:
        crd_list = api_instance.list_custom_resource_definition()
        exists = any(crd.metadata.name == crd_name for crd in crd_list.items)

        if exists:
            logging.info(f"↳ CRD '{crd_name}' already exists, doing nothing...")
            return True
        else:
            logging.info(f"↳ CRD '{crd_name}' does not exists, creating it...")
            with open("WordPressSite-crd.yaml") as file:
                crd_file = yaml.safe_load(file)
            crd_resource = dyn_client.resources.get(api_version='apiextensions.k8s.io/v1', kind='CustomResourceDefinition')

            try:
                crd_resource.create(body=crd_file)
                logging.info(f"↳ CRD '{crd_name}' created")
                return True
            except client.exceptions.ApiException as e:
                logging.error("Error trying to create CRD :", e)
    except ApiException as e:
        logging.error(f"Error verifying CRD file: {e}")
    return False

# Function that runs when the operator starts
@kopf.on.startup()
def startup_fn(**kwargs):
    print("Operator started and initialized")
    # TODO: check the presence of namespaces or cluster-wide flag here.

    ensure_wp_crd_exists()

def list_wordpress_sites(namespace):
    logging.info(f"   ↳ [{namespace}] list_wordpress_sites")
    api = client.CustomObjectsApi()
    
    wordpress_sites = api.list_namespaced_custom_object(
        group="wordpress.epfl.ch",
        version="v1",
        plural="wordpresssites",
        namespace=namespace
    )
    logging.debug("f{len(wordpress_sites) WordPress sites")
    
    active_sites = [
        site for site in wordpress_sites.get('items', [])
        if 'deletionTimestamp' not in site['metadata']
    ]
    logging.debug("f{len(active_sites) active WordPress sites")
    
    logging.info(f"   ↳ [{namespace}] END OF list_wordpress_sites")
    return active_sites


def generate_nginx_index(wordpress_sites):
    nginx_conf = '''
    # nginx sites start here.
'''
    for site in wordpress_sites:
        path = site['spec']['path']
        name = site['metadata']['name']

        template_vars = dict(
            path=path, name=name,
            db_host='mariadb-min',
            db_name=f'wp-db-{name}',
            db_user=f'wp-db-user-{name}',
            db_password='secret',
            wp_home_dir='/wp/6')

        nginx_conf = nginx_conf + '''

    # START: configuring %(name)s here.
    location = %(path)s {
      return 301 %(path)s/;
    }
    location = %(path)s/wp-admin {
      return 301 %(path)s/wp-admin/;
    }
    location %(path)s/ {
''' % template_vars
        # PHP queries are those with no dot in them, 
        # or those that end with .php:
        nginx_conf = nginx_conf + '''
      location ~ ^[^.]*$ {
        fastcgi_pass unix:/run/php-fpm.sock;
      }
      location ~ \\.php$ {
        fastcgi_pass unix:/run/php-fpm.sock;
      }
''' % template_vars

        # Under nginx' priority rules, locations that match plain
        # files must come after PHP, so as to give priority to the
        # former. (There are PHP files under wp-admin/ etc. which we
        # don't want to mask out.)
        nginx_conf = nginx_conf + '''
      location ~ (wp-includes|wp-admin|wp-content/(plugins|mu-plugins|themes))/ {
        rewrite .*/((wp-includes|wp-admin|wp-content/(plugins|mu-plugins|themes))/.*) /$1 break;
        root %(wp_home_dir)s/;
      }

      location ~ (wp-content/uploads)/ {
        rewrite .*/(wp-content/uploads/(.*)) /$2 break; 
        root /data/%(name)s/uploads/;
      } 
''' % template_vars
        # All the PHP traffic goes through a single entry point. This
        # avoids stat()s on NFS when we know (through regexes below)
        # that the query is for WordPress. If, on the other hand, the
        # query turns out to be for a static file, then all
        # fastcgi_param directives will have bo effect.
        nginx_conf = nginx_conf + '''
      fastcgi_param SCRIPT_FILENAME /wp/nginx-entrypoint/nginx-entrypoint.php;
 
      fastcgi_param WP_DEBUG           true;
      fastcgi_param WP_ROOT_URI        %(path)s/;
      fastcgi_param WP_SITE_NAME       %(name)s;
      fastcgi_param WP_ABSPATH         %(wp_home_dir)s/;
      fastcgi_param WP_DB_HOST         %(db_host)s;
      fastcgi_param WP_DB_NAME         %(db_name)s;
      fastcgi_param WP_DB_USER         %(db_user)s;
      fastcgi_param WP_DB_PASSWORD     %(db_password)s;

      fastcgi_param QUERY_STRING       $query_string;
      fastcgi_param REQUEST_METHOD     $request_method;
      fastcgi_param REQUEST_SCHEME     $scheme;
      fastcgi_param CONTENT_TYPE       $content_type;
      fastcgi_param CONTENT_LENGTH     $content_length;
 
      fastcgi_param REQUEST_URI        $request_uri;
      fastcgi_param DOCUMENT_URI       $document_uri;
      fastcgi_param SERVER_PROTOCOL    $server_protocol;
      fastcgi_param HTTPS              on;
 
      fastcgi_param SERVER_SOFTWARE    nginx/$nginx_version;
 
      fastcgi_param REMOTE_ADDR        $remote_addr;
      fastcgi_param REMOTE_PORT        $remote_port;
      fastcgi_param SERVER_ADDR        $server_addr;
      fastcgi_param SERVER_PORT        $server_port;
      fastcgi_param SERVER_NAME        $server_name;
 
      fastcgi_param WP_ENV             test;
''' % template_vars
        # PHP only, required if PHP was built with --enable-force-cgi-redirect
        nginx_conf = nginx_conf + '''
      fastcgi_param REDIRECT_STATUS 200;
      fastcgi_param HTTP_PROXY      '';
    }
    # END: configuring %(name)s here.

''' % template_vars

    nginx_conf = nginx_conf + '''
    # nginx sites end here.
'''

    return nginx_conf

def generate_php_get_wordpress(wordpress_sites):
    logging.debug(f"   ↳ [generate_php_get_wordpress] get_wordpress.php")
    php_code = """<?php
    
namespace __entrypoint;
/**
 * This function is dynamically built by the WordPress Operator!
 * Its main objectif is to match a URL's path to a k8s WordPress
 * object name (https://domain/site-A/site-C/ ←→ `site-c`).
 * It's also used to trigger some configuration, from the WordPress
 * k8s object (defined in the CR), to a specific WordPress site.
 */
function get_wordpress ($wp_env, $host, $uri) {
    $common_values = [
        'host'       => 'wp-httpd',
        'wp_env'     => getenv('WP_ENV'), // why ?
        'wp_version' => '6'
    ];

    $sites_values = ["""

    logging.debug(f"     → MAYBE HELLP")
    logging.debug(f"     {wordpress_sites}")
    
    for site in wordpress_sites:
        name = site['metadata']['name']
        logging.debug(f"     → DOING {name}")
        path = site['spec']['path']
        debug = site['spec']['wordpress']['debug']
        
        if (name != 'www'):
            logging.debug(f"     ↳ [{generate_php_get_wordpress}] {name=}, {path=}")
            php_code += f"""
        '{path}' => [
            'site_uri' => '{path}/',
            'site_name' => '{name}',
            'wp_debug' => {debug},
        ],"""

    php_code+="""
        '/' => [ // this is mandatory (used as default)!
            'site_uri' => '/',
            'site_name' => 'www', ## FIXME
            'wp_debug' => true,
        ],
    ];
    $key = $uri;
    $array_paths = explode('/', $uri);
    while ( ! array_key_exists($key, $sites_values) && $key != '' ) {
        array_pop($array_paths);
        $key = implode('/', $array_paths);
    }
    if ( $key == '' ) $key = '/';
    
    error_log("Selected uri_path → " . $key);
    return array_merge($common_values, $sites_values[$key]);
}
"""

    return php_code

def generate_php_get_credentials(wordpress_sites):
    logging.debug(f"   ↳ [generate_php_get_credentials] get_db_credentials.php")
    php_code ="""<?php
    
namespace __entrypoint;
    
function get_db_credentials ($wordpress) {

    $databases_config = ["""

    for site in wordpress_sites:
        path = site['spec']['path']
        name = site['metadata']['name']
        
        if (path != '/'):
            php_code += f"""
        '{path}/' => [
            'db_host' => 'mariadb-min',
            'db_name' => 'wp-db-{name}',
            'db_user' => 'wp-db-user-{name}',
            'db_password' => 'secret'
        ],"""

    php_code+= """
        '/' => [ # This is the root site and is mandatory
            'db_host' => 'mariadb-min',
            'db_name' => 'wordpress-test',
            'db_user' => 'wordpress',
            'db_password' => 'secret'
        ],
    ];
    error_log(print_r($wordpress, true));
    return $databases_config[$wordpress['site_uri']];
}
"""

    return php_code

def get_nginx_secret(namespace):
    api = client.CoreV1Api()
    try:
        return api.read_namespaced_secret(name=Config.secret_name, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            raise e
    return api.create_namespaced_secret(
        namespace=namespace,
        body=client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(name=Config.secret_name, namespace=namespace)))

def regenerate_nginx_secret(logger, namespace):
    logging.info(f" ↳ [{namespace}/cm+secret] Recreating the nginx index secret {Config.secret_name})")
    api = client.CoreV1Api()
    
    wordpress_sites = list_wordpress_sites(namespace)

    nginx_conf = generate_nginx_index(wordpress_sites)
    secret = get_nginx_secret(namespace)

    b = base64.b64encode(bytes(nginx_conf, 'utf-8'))
    base64_str = b.decode('utf-8')

    if not secret.data:
        secret.data = {}
    secret.data['nginx-all-wordpresses.conf'] = base64_str

    api.replace_namespaced_secret(name=Config.secret_name, namespace=namespace, body=secret)

def install_wordpress_via_php(name, path, title, tagline):
    logging.info(f" ↳ [install_wordpress_via_php] Configuring (ensure-wordpress-and-theme.php) with {name=}, {path=}, {title=}, {tagline=}")
    # https://stackoverflow.com/a/89243
    result = subprocess.run([Config.php, Config.wp_php_ensure,
                             f"--name={name}", f"--path={path}",
                             f"--wp-dir={Config.wp_dir}",
                             f"--wp-host={Config.wp_host}",
                             f"--db-host={Config.db_host}",
                             f"--db-name=wp-db-{name}",
                             f"--db-user=wp-db-user-{name}",
                             f"--db-password=secret",
                             f"--title={title}", f"--tagline={tagline}"], capture_output=True, text=True)
    print(result.stdout)
    if "WordPress successfully installed" not in result.stdout:
        raise subprocess.CalledProcessError(0, "PHP script failed")
    else:
        logging.info(f" ↳ [install_wordpress_via_php] End of configuring")

def manage_plugins_php(name, plugins):
    logging.info(f" ↳ [manage_plugins_php] Configuring (manage-plugins.php) with {name=} and {plugins=}")
    # https://stackoverflow.com/a/89243
    result = subprocess.run([Config.php, Config.wp_php_ensure,
                             f"--name={name}",
                             f"--wp-dir={Config.wp_dir}",
                             f"--wp-host={Config.wp_host}",
                             f"--db-host={Config.db_host}",
                             f"--db-name=wp-db-{name}",
                             f"--db-user=wp-db-user-{name}",
                             f"--db-password=secret",
                             f"--plugins={plugins}"], capture_output=True, text=True)
    print(result.stdout)
    if "WordPress plugins successfully installed" not in result.stdout:
        raise subprocess.CalledProcessError(0, "PHP script failed")
    else:
        logging.info(f" ↳ [manage_plugins_php] End of configuring")

def create_database(custom_api, namespace, name):
    logging.info(f" ↳ [{namespace}/{name}] Create Database wp-db-{name}")
    body = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "Database",
        "metadata": {
            "name": f"wp-db-{name}",
            "namespace": namespace
        },
        "spec": {
            "mariaDbRef": {
                "name": "mariadb-min"
            },
            "characterSet": "utf8mb4",
            "collate": "utf8mb4_unicode_ci"
        }
    }


    try:
        custom_api.create_namespaced_custom_object(
            group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=namespace,
            plural="databases",
            body=body
        )
    except ApiException as e:
        if e.status != 409:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] Database wp-db-{name} already exists")

def create_secret(api_instance, namespace, name, prefix, secret):
    logging.info(f" ↳ [{namespace}/{name}] Create Secret name={prefix + name}")
    secret_name = prefix + name
    body = client.V1Secret(
        type="Opaque",
        metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace),
        string_data={"password": secret}
    )

    try:
        api_instance.create_namespaced_secret(namespace=namespace, body=body)
    except ApiException as e:
        if e.status != 409:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] Secret {secret_name} already exists")

def delete_secret(api_instance, namespace, name, prefix):
    secret_name = prefix + name
    try:
        logging.info(f" ↳ [{namespace}/{name}] Delete Secret {secret_name}")

        api_instance.delete_namespaced_secret(namespace=namespace, name=secret_name)
    except ApiException as e:
        if e.status != 404:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] Secret {secret_name} already deleted")

def create_user(custom_api, namespace, name):
    user_name = f"wp-db-user-{name}"
    password_name = f"wp-db-password-{name}"
    logging.info(f" ↳ [{namespace}/{name}] Create User name={user_name}")
    body = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "User",
        "metadata": {
            "name": user_name,
            "namespace": namespace
        },
        "spec": {
            "mariaDbRef": {
                "name": "mariadb-min"
            },
            "passwordSecretKeyRef": {
                "name": password_name,
                "key": "password"
            },
            "host": "%",
            "cleanupPolicy": "Delete"
        }
    }

    try:
        custom_api.create_namespaced_custom_object(
            group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=namespace,
            plural="users",
            body=body
        )
    except ApiException as e:
        if e.status != 409:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] User {user_name} already exists")


def create_grant(custom_api, namespace, name):
    grant_name = f"wordpress-{name}"
    logging.info(f" ↳ [{namespace}/{name}] Create Grant {name=}")
    body = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "Grant",
        "metadata": {
            "name": grant_name,
            "namespace": namespace
        },
        "spec": {
            "mariaDbRef": {
                "name": "mariadb-min"
            },
            "privileges": [
                "ALL PRIVILEGES"
            ],
            "database": f"wp-db-{name}",
            "table" : "*",
            "username": f"wp-db-user-{name}",
            "grantOption": False,
            "host": "%"
        }
    }

    try:
        custom_api.create_namespaced_custom_object(
            group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=namespace,
            plural="grants",
            body=body
        )
    except ApiException as e:
        if e.status != 409:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] Grant {grant_name} already exists")

def delete_custom_object_mariadb(custom_api, namespace, name, prefix, plural):
    mariadb_name = prefix + name
    logging.info(f" ↳ [{namespace}/{name}] Delete MariaDB object {mariadb_name}")
    try:
        custom_api.delete_namespaced_custom_object(
            group="k8s.mariadb.com",
            version="v1alpha1",
            plural=plural,
            namespace=namespace,
            name=mariadb_name
        )
    except ApiException as e:
        if e.status != 404:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] MariaDB object {mariadb_name} already deleted")

def get_os3_credentials(namespace, name, profile_name):
    logging.info(f"   ↳ [{namespace}/{name}] Get Restic and S3 secrets")

    file_path = "/keybase/team/epfl_wp_prod/aws-cli-credentials"

    with open(file_path, 'r') as file:
        content = file.read()

    profile_pattern = re.compile(rf'\[{profile_name}\](.*?)(?=\[|$)', re.DOTALL)
    profile_content = profile_pattern.search(content)
    
    profile_content = profile_content.group(1)

    return {
        "AWS_SECRET_ACCESS_KEY": re.search(r'aws_secret_access_key\s*=\s*(\S+)', profile_content).group(1),
        "AWS_ACCESS_KEY_ID": re.search(r'aws_access_key_id\s*=\s*(\S+)', profile_content).group(1),
        "RESTIC_PASSWORD": re.search(r'restic_password\s*=\s*(\S+)', profile_content).group(1),
        "BUCKET_NAME": re.search(r'bucket_name\s*=\s*(\S+)', profile_content).group(1),
        "AWS_SHARED_CREDENTIALS_FILE": file_path
    }

def restore_wordpress_from_os3(custom_api, namespace, name, path, prefix, environment, ansible_host):
    logging.info(f" ↳ [{namespace}/{name}] Restoring WordPress from OS3")

    target = f"/tmp/backup/{name}"
    profile_name = "backup-wwp"
    backup_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'

    # Retrieve S3 credentials
    credentials = get_os3_credentials(namespace, name, profile_name)

    try:
        # Execute the Restic command to restore the backup
        restic_restore = subprocess.run([f"restic -r s3:https://s3.epfl.ch/{credentials['BUCKET_NAME']}/backup/wordpresses/www{path.replace('/','__').replace('-','_')}/sql restore latest --target {target}"], env=credentials, shell=True, capture_output=True, text=True)
        logging.info(f"   ↳ [{namespace}/{name}] SQL backup restored from S3")

        # Open file to write the modified SQL
        backup_file_path = f"/tmp/backup/{name}/backup.{backup_time}.sql"
        
        with open(backup_file_path, "w") as backup_file:
            logging.info(f"   ↳ [{namespace}/{name}] Replacing www.epfl.ch with wpn.fsd.team in SQL backup")
            sed_command = ["sed", "s/www\.epfl\.ch/wpn.fsd.team/g", f"{target}/db-backup.sql"]
            
            subprocess.run(sed_command, stdout=backup_file, check=True)

        copy_backup = subprocess.run([f"aws --endpoint-url=https://s3.epfl.ch --profile={profile_name} s3 cp {backup_file_path} s3://{credentials['BUCKET_NAME']}/backup/k8s/{name}/"], env=credentials, shell=True, capture_output=True, text=True)
        logging.info(f"   ↳ [{namespace}/{name}] SQL backup copied to S3")

        # Initiate the restore process in MariaDB
        restore_spec = {
            "apiVersion": "k8s.mariadb.com/v1alpha1",
            "kind": "Restore",
            "metadata": {
                "name": f"restore-{name}-{round(time.time())}",
                "namespace": namespace
            },
            "spec": {
                "mariaDbRef": {
                    "name": "mariadb-min"
                },
                "s3": {
                    "bucket": credentials["BUCKET_NAME"],
                    "prefix": f"backup/k8s/{name}",
                    "endpoint": "s3.epfl.ch",
                    "accessKeyIdSecretKeyRef": {
                        "name": "s3-backup-credentials",
                        "key": "keyId"
                    },
                    "secretAccessKeySecretKeyRef": {
                        "name": "s3-backup-credentials",
                        "key": "accessSecret"
                    },
                    "tls": {
                        "enabled": True
                    }
                },
                "targetRecoveryTime": backup_time,
                "args": [
                    "--verbose",
                    f"--database={prefix}{name}"
                ]
            }
        }

        logging.info(f"   ↳ [{namespace}/{name}] Creating restore object in Kubernetes")
        custom_api.create_namespaced_custom_object(
            group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=namespace,
            plural="restores",
            body=restore_spec
        )
        logging.info(f"   ↳ [{namespace}/{name}] Restore initiated on MariaDB")

        logging.info(f"   ↳ [{namespace}/{name}] Restoring media from OS3")

        pvc_name = "wordpress-test-wp-uploads-pvc-f401a87f-d2e9-4b20-85cc-61aa7cfc9d30"
        copy_media = subprocess.run([f"ssh -t root@itswbhst0020.xaas.epfl.ch 'cp -r /mnt/data-prod-ro/wordpress/{environment}/www.epfl.ch/htdocs{path}/wp-content/uploads/ /mnt/data/nfs-storageclass/{pvc_name}/wp-uploads/{name}/; chown -R 33:33 /mnt/data/nfs-storageclass/{pvc_name}/wp-uploads/{name}/uploads'"], shell=True, capture_output=True, text=True)

        logging.info(f"   ↳ [{namespace}/{name}] Restored media from OS3")
    except subprocess.CalledProcessError as e:
        logging.error(f"Subprocess error in backup restoration: {e}")
    except FileNotFoundError as e:
        logging.error(f"File error in backup restoration: {e}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")


@kopf.on.create('wordpresssites')
def create_fn(spec, name, namespace, logger, **kwargs):
    logging.info(f"Create WordPressSite {name=} in {namespace=}")
    path = spec.get('path')
    wordpress = spec.get("wordpress")
    epfl = spec.get("epfl")
    import_from_os3 = epfl.get("importFromOS3")
    environment = import_from_os3["environment"]
    ansible_host = import_from_os3["ansibleHost"]
    title = wordpress["title"]
    tagline = wordpress["tagline"]
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    secret = "secret" # Password, for the moment hard coded.

    create_database(custom_api, namespace, name)
    create_secret(api_instance, namespace, name, 'wp-db-password-', secret)
    create_user(custom_api, namespace, name)
    create_grant(custom_api, namespace, name)

    regenerate_nginx_secret(logger, namespace)
    if (not import_from_os3):
        install_wordpress_via_php(name, path, title, tagline)
    else:
        restore_wordpress_from_os3(custom_api, namespace, name, path, "wp-db-", environment, ansible_host)
        manage_plugins_php(name, "test,test,test")

    logging.info(f"End of create WordPressSite {name=} in {namespace=}")


@kopf.on.delete('wordpresssites')
def delete_fn(spec, name, namespace, logger, **kwargs):
    print(kwargs['meta']['namespace'])
    logging.info(f"Delete WordPressSite {name=} in {namespace=}")
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    # Deleting database
    delete_custom_object_mariadb(custom_api, namespace, name, "wp-db-", "databases")
    delete_secret(api_instance, namespace, name, 'wp-db-password-')
    # Deleting user
    delete_custom_object_mariadb(custom_api, namespace, name, "wp-db-user-", "users")
    # Deleting grant
    delete_custom_object_mariadb(custom_api, namespace, name, "wordpress-", "grants")

    regenerate_nginx_secret(logger, namespace)

if __name__ == '__main__':
    Config.load_from_command_line()
    sys.exit(kopf.cli.main())
