import kopf
import kopf.cli
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.exceptions import ApiException
import logging
import os
import sys
import yaml



class classproperty:
    def __init__(self, func):
        self.fget = func
    def __get__(self, instance, owner):
        return self.fget(owner)


class KubernetesAPI:
  __singleton = None

  @classmethod
  def __get(cls):
      if cls.__singleton is None:
          cls.__singleton = cls()

      return cls.__singleton

  def __init__(self):
      config.load_config()

      self._custom = client.CustomObjectsApi()
      self._core = client.CoreV1Api()
      self._extensions = client.ApiextensionsV1Api()
      self._dynamic = DynamicClient(client.ApiClient())
      self._networking = client.NetworkingV1Api()

  @classproperty
  def extensions(cls):
    return cls.__get()._extensions

  @classproperty
  def dynamic(cls):
    return cls.__get()._dynamic


@kopf.on.startup()
def on_kopf_startup (**kwargs):
    WordPressCRDOperator.ensure_wp_crd_exists()


class WordPressCRDOperator:
    @classmethod
    def ensure_wp_crd_exists(cls):
      dyn_client = KubernetesAPI.dynamic
      api_extensions_instance = KubernetesAPI.extensions
      crd_name = "wordpresssites.wordpress.epfl.ch"

      try:
          crd_list = api_extensions_instance.list_custom_resource_definition()
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
          print("Operator started and initialized")
      except ApiException as e:
          logging.error(f"Error verifying CRD file: {e}")
      return False

if __name__ == '__main__':
    sys.exit(kopf.cli.main())
