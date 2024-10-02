# Kopf documentation : https://kopf.readthedocs.io/
import kopf
from kubernetes import client, config
import base64
import subprocess

configmap_name = "wpn-nginx"
namespace_name = "wordpress-test"

def list_wordpress_sites():
    api = client.CustomObjectsApi()
    
    wordpress_sites = api.list_cluster_custom_object(
        group="wordpress.epfl.ch",
        version="v1",
        plural="wordpresssites"
    )
    
    return wordpress_sites.get('items', [])

def generate_php_get_wordpress(wordpress_sites):
    php_code = """<?php
    
namespace __entrypoint;
    
function get_wordpress ($wp_env, $host, $uri) {
    $common_values = [
        'host'       => 'wp-httpd',
        'wp_env'     => getenv('WP_ENV'), // why ?
        'wp_version' => '6'
    ];

    $sites_values = ["""

    for site in wordpress_sites:
        path = site['spec']['path']
        php_code += f"""
        '{path}' => [
            'site_uri' => '{path}/',
            'wp_debug' => TRUE
        ],"""

    php_code+="""
        '/' => [ // this is mandatory (used as default)!
            'site_uri' => '/',
            'wp_debug' => TRUE
        ],
    ];
    $key = $uri;
    $array_paths = explode('/', $uri);
    while ( ! array_key_exists($key, $sites_values) && $key != '' ) {{
        array_pop($array_paths);
        $key = implode('/', $array_paths);
    }}
    if ( $key == '' ) $key = '/';
    error_log("Selected uri_path → " . $key);
    return array_merge($common_values, $sites_values[$key]);
}
"""

    return php_code

def generate_php_get_credentials(wordpress_sites):
    php_code ="""<?php
    
namespace __entrypoint;
    
function get_db_credentials ($wordpress) {

    $databases_config = ["""

    for site in wordpress_sites:
        path = site['spec']['path']
        name = site['metadata']['name']
        php_code += f"""
            '{path}/' => [
                'db_host' => 'mariadb-min',
                'db_name' => 'wp-db-{name}',
                'db_user' => 'wp-db-user-{name}',
                'db_password' => 'secret'
            ],"""

    php_code+= """
    ];
    error_log(print_r($wordpress, true));
    return $databases_config[$wordpress['site_uri']];
}
"""

    return php_code

def get_nginx_configmap():
    api = client.CoreV1Api()
    configmap = api.read_namespaced_config_map(name=configmap_name, namespace=namespace_name)
    return configmap

def get_nginx_secret():
    api = client.CoreV1Api()
    secret = api.read_namespaced_secret(name=configmap_name, namespace=namespace_name)
    return secret

def regenerate_nginx_configmap(logger):
    api = client.CoreV1Api()
    
    wordpress_sites = list_wordpress_sites()
    
    php_code_get_wordpress = generate_php_get_wordpress(wordpress_sites)
    php_code_get_credentials = generate_php_get_credentials(wordpress_sites)
    configmap = get_nginx_configmap()
    secret = get_nginx_secret()

    b = base64.b64encode(bytes(php_code_get_credentials, 'utf-8'))
    base64_str = b.decode('utf-8')

    configmap.data['get_wordpress.php'] = php_code_get_wordpress
    secret.data['get_db_credentials.php'] = base64_str


    api.replace_namespaced_config_map(name=configmap_name, namespace=namespace_name, body=configmap)
    api.replace_namespaced_secret(name=configmap_name, namespace=namespace_name, body=secret)

def execute_php_via_stdin(path, name):
    # https://stackoverflow.com/a/92395
    subprocess.call(f"php ../../ensure-wordpress-and-theme.php {path} {name}", shell=True)

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

def create_database(custom_api, namespace, name):
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

    custom_api.create_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        namespace=namespace,
        plural="databases",
        body=body
    )

def create_secret(api_instance, namespace, name, secret):
    body = client.V1Secret(
        type="Opaque",
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        string_data={"password": secret}
    )

    api_instance.create_namespaced_secret(namespace=namespace, body=body)

def delete_secret(api_instance, namespace, name):
    api_instance.delete_namespaced_secret(namespace=namespace, name=f"wp-db-password-{name}")

def create_user(custom_api, namespace, name):
    body = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "User",
        "metadata": {
            "name": f"wp-db-user-{name}",
            "namespace": namespace
        },
        "spec": {
            "mariaDbRef": {
                "name": "mariadb-min"
            },
            "passwordSecretKeyRef": {
                "name": f"wp-db-password-{name}",
                "key": "password"
            },
            "host": "%",
            "cleanupPolicy": "Delete"
        }
    }

    custom_api.create_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        namespace=namespace,
        plural="users",
        body=body
    )

def create_grant(custom_api, namespace, name):
    body = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "Grant",
        "metadata": {
            "name": f"wordpress-{name}",
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

    custom_api.create_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        namespace=namespace,
        plural="grants",
        body=body
    )

def delete_custom_object_mariadb(custom_api, namespace, name, plural):
    custom_api.delete_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        plural=plural,
        namespace=namespace,
        name=name
    )

@kopf.on.create('wordpresssites')
def create_fn(spec, name, namespace, logger, **kwargs):
    
    path = spec.get('path')
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    secret = "secret" # Password, for the moment hard coded.

    #   create_ingress(networking_v1_api, namespace, name, path)
    create_database(custom_api, namespace, name)
    create_secret(api_instance, namespace, f"wp-db-password-{name}", secret)
    create_user(custom_api, namespace, name)
    create_grant(custom_api, namespace, name)

    regenerate_nginx_configmap(logger)
    execute_php_via_stdin(path, name)

@kopf.on.delete('wordpresssites')
def delete_fn(spec, name, namespace, logger, **kwargs):
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    # delete_ingress(networking_v1_api, namespace, name)
    # Deleting database
    delete_custom_object_mariadb(custom_api, namespace, f"wp-db-{name}", "databases")
    delete_secret(api_instance, namespace, name)
    # Deleting user
    delete_custom_object_mariadb(custom_api, namespace, f"wp-db-user-{name}", "users")
    # Deleting grant
    delete_custom_object_mariadb(custom_api, namespace, f"wordpress-{name}", "grants")