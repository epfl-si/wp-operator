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

@kopf.on.create('wordpresssites')
def create_fn(spec, name, namespace, logger, **kwargs):
    
    path = spec.get('path')
    config.load_kube_config()
    networking_v1_api = client.NetworkingV1Api()
    custom_api = client.CustomObjectsApi()

    create_ingress(networking_v1_api, namespace, name, path)
    create_database(custom_api, namespace, name)
