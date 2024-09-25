# Kopf documentation : https://kopf.readthedocs.io/
import kopf
from kubernetes import client, config

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

    create_ingress(networking_v1_api, namespace, name, path)
    create_database(custom_api, namespace, name)
    create_secret(api_instance, namespace, f"wp-db-password-{name}", secret)
    create_user(custom_api, namespace, name)
    create_grant(custom_api, namespace, name)

@kopf.on.delete('wordpresssites')
def delete_fn(spec, name, namespace, logger, **kwargs):
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()
    api_instance = client.CoreV1Api()

    delete_ingress(networking_v1_api, namespace, name)
    # Deleting database
    delete_custom_object_mariadb(custom_api, namespace, f"wp-db-{name}", "databases")
    delete_secret(api_instance, namespace, name)
    # Deleting user
    delete_custom_object_mariadb(custom_api, namespace, f"wp-db-user-{name}", "users")
    # Deleting grant
    delete_custom_object_mariadb(custom_api, namespace, f"wordpress-{name}", "grants")