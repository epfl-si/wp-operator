# Kopf documentation : https://kopf.readthedocs.io/
#
# Run with `kopf run -n wordpress-test wpn-kopf.py [--verbose]`
#
import kopf
import logging
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
import base64
import subprocess
import json

configmap_name = "nginx-php-site-tree"
secret_name = "nginx-php-mariadb-credentials"
namespace_name = "wordpress-test"

# Function that runs when the operator starts
@kopf.on.startup()
def startup_fn(**kwargs):
    print("Operator started and initialized")
    # TODO: check the presence of namespaces or cluster-wide flag here.

def list_wordpress_sites():
    logging.info(f"   ↳ [{namespace_name}] list_wordpress_sites")
    api = client.CustomObjectsApi()
    
    wordpress_sites = api.list_cluster_custom_object(
        group="wordpress.epfl.ch",
        version="v1",
        plural="wordpresssites"
    )
    logging.info(wordpress_sites)
    
    active_sites = [
        site for site in wordpress_sites.get('items', [])
        # if site.get('status', {}).get('phase') == 'active' # FIXME
    ]
    logging.info(active_sites)
    
    logging.info(f"   ↳ [{namespace_name}] END OF list_wordpress_sites")
    return active_sites

def generate_php_get_wordpress(wordpress_sites):
    logging.info(f"   ↳ [{namespace_name}/cm] get_wordpress.php")
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

    logging.info(f"     → MAYBE HELLP")
    logging.info(f"     {wordpress_sites}")
    
    for site in wordpress_sites:
        name = site['metadata']['name']
        logging.info(f"     → DOING {name}")
        path = site['spec']['path']
        debug = site['spec']['wordpress']['debug']
        
        if (name != 'www'):
            print(f"DEBUG MAISON: {name=}, {path=}") # DEBUG
            logging.info(f"     ↳ [{namespace_name}/cm] {name=}, {path=}")
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
    logging.info(f"   ↳ [{namespace_name}/secret] get_db_credentials.php")
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

def get_nginx_configmap():
    api = client.CoreV1Api()
    try:
        return api.read_namespaced_config_map(name=configmap_name, namespace=namespace_name)
    except ApiException as e:
        if e.status != 404:
            raise e

    return api.create_namespaced_config_map(
        namespace=namespace_name,
        body=client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=client.V1ObjectMeta(name=configmap_name, namespace=namespace_name)))

def get_nginx_secret():
    api = client.CoreV1Api()
    try:
        return api.read_namespaced_secret(name=secret_name, namespace=namespace_name)
    except ApiException as e:
        if e.status != 404:
            raise e
    return api.create_namespaced_secret(
        namespace=namespace_name,
        body=client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace_name)))

def regenerate_nginx_configmap(logger):
    logging.info(f" ↳ [{namespace_name}/cm+secret] Recreating the config map + secret ({configmap_name})")
    api = client.CoreV1Api()
    
    wordpress_sites = list_wordpress_sites()
    
    php_code_get_wordpress = generate_php_get_wordpress(wordpress_sites)
    php_code_get_credentials = generate_php_get_credentials(wordpress_sites)
    configmap = get_nginx_configmap()
    secret = get_nginx_secret()

    b = base64.b64encode(bytes(php_code_get_credentials, 'utf-8'))
    base64_str = b.decode('utf-8')

    if not configmap.data:
        configmap.data = {}
    configmap.data['get_wordpress.php'] = php_code_get_wordpress
    if not secret.data:
        secret.data = {}
    secret.data['get_db_credentials.php'] = base64_str


    api.replace_namespaced_config_map(name=configmap_name, namespace=namespace_name, body=configmap)
    api.replace_namespaced_secret(name=secret_name, namespace=namespace_name, body=secret)

def execute_php_via_stdin(name, path, title, tagline):
    # Quick way to escape string before passing them to the shell
    # see https://stackoverflow.com/a/44820658/960623
    title = json.dumps(title)
    tagline = json.dumps(tagline)
    logging.info(f" ↳ [{namespace_name}/{name}] Configuring (ensure-wordpress-and-theme.php) with {name=}, {path=}, {title=}, {tagline=}")
    # https://stackoverflow.com/a/89243
    subprocess.run(["php",  f"--name={name}", "--path={path}", f"--title={title}", f"--tagline={tagline}"])
    logging.info(f" ↳ [{namespace_name}/{name}] End of configuring")

# Thanks to https://blog.knoldus.com/how-to-create-ingress-using-kubernetes-python-client%EF%BF%BC/
def create_ingress(networking_v1_api, namespace, name, path):
    body = client.V1Ingress(
        api_version="networking.k8s.io/v1",
        kind="Ingress",
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1IngressSpec(
            rules=[client.V1IngressRule(
                host="wpn.fsd.team",
                http=client.V1HTTPIngressRuleValue(
                    paths=[client.V1HTTPIngressPath(
                        path=path,
                        path_type="Prefix",
                        backend=client.V1IngressBackend(
                            service=client.V1IngressServiceBackend(
                                name="wpn-nginx-service",
                                port=client.V1ServiceBackendPort(
                                    number=80,
                                )
                            )
                        )
                    )]
                )
            )
            ]
        )
    )

    networking_v1_api.create_namespaced_ingress(
        namespace=namespace,
        body=body
    )

def delete_ingress(networking_v1_api, namespace, name):
    networking_v1_api.delete_namespaced_ingress(
        namespace=namespace,
        name=name
    )
    try:
        networking_v1_api.delete_namespaced_ingress(
            namespace=namespace,
            name=name
        )
    except ApiException as e:
        if e.status != 404:
            raise e
        logging.info(f" ↳ [{namespace}/{name}] Ingress {name} already deleted")

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
            "characterSet": "utf8",
            "collate": "utf8_general_ci"
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
    logging.info(f" ↳ [{namespace}/{name}] Delete MariaDB object {prefix + name}")
    custom_api.delete_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        plural=plural,
        namespace=namespace,
        name=prefix + name
    )
    mariadb_name = prefix + name;
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

@kopf.on.create('wordpresssites')
def create_fn(spec, name, namespace, logger, **kwargs):
    logging.info(f"Create WordPressSite {name=} in {namespace=}")
    path = spec.get('path')
    wordpress = spec.get("wordpress")
    title = wordpress["title"]
    tagline = wordpress["tagline"]
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    secret = "secret" # Password, for the moment hard coded.

    #   create_ingress(networking_v1_api, namespace, name, path)
    create_database(custom_api, namespace, name)
    create_secret(api_instance, namespace, name, 'wp-db-password-', secret)
    create_user(custom_api, namespace, name)
    create_grant(custom_api, namespace, name)

    regenerate_nginx_configmap(logger)
    execute_php_via_stdin(name, path, title, tagline)
    logging.info(f"End of create WordPressSite {name=} in {namespace=}")


@kopf.on.delete('wordpresssites')
def delete_fn(spec, name, namespace, logger, **kwargs):
    print(kwargs['meta']['namespace'])
    logging.info(f"Delete WordPressSite {name=} in {namespace=}")
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    # delete_ingress(networking_v1_api, namespace, name)
    # Deleting database
    delete_custom_object_mariadb(custom_api, namespace, name, "wp-db-", "databases")
    delete_secret(api_instance, namespace, name, 'wp-db-password-')
    # Deleting user
    delete_custom_object_mariadb(custom_api, namespace, name, "wp-db-user-", "users")
    # Deleting grant
    delete_custom_object_mariadb(custom_api, namespace, name, "wordpress-", "grants")

    regenerate_nginx_configmap(logger)
