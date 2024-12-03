import kopf
import kopf.cli
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.dynamic import DynamicClient
from kubernetes_asyncio.client.exceptions import ApiException
import logging
import os
import sys
import yaml


@kopf.on.startup()
async def on_kopf_startup (**kwargs):
    await WordPressCRDOperator.ensure_wp_crd_exists()


class WordPressCRDOperator:
    @classmethod
    async def ensure_wp_crd_exists(cls):
      crd_name = "wordpresssites.wordpress.epfl.ch"

      try:
          await config.load_kube_config()
          async with ApiClient() as api:
              api_extensions = client.ApiextensionsV1Api(api)
              crd_list = await api_extensions.list_custom_resource_definition()
              exists = any(crd.metadata.name == crd_name for crd in crd_list.items)
              
              if exists:
                  logging.info(f"↳ CRD '{crd_name}' already exists, doing nothing...")
                  return True

              logging.info(f"↳ CRD '{crd_name}' does not exists, creating it...")
              with open("WordPressSite-crd.yaml") as file:  # TODO: blocking
                  crd_file = yaml.safe_load(file)
              dyn_client = await DynamicClient(api)
              crd_resource = await dyn_client.resources.get(api_version='apiextensions.k8s.io/v1', kind='CustomResourceDefinition')

              try:
                  await crd_resource.create(body=crd_file)
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
