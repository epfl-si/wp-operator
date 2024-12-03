import asyncio
import kopf
import kopf.cli
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.dynamic import DynamicClient
from kubernetes_asyncio.client.exceptions import ApiException
import logging
import os
import sys
import threading
import time
import yaml

class WordPressCRDOperator:
    crd_name = "wordpresssites.wordpress.epfl.ch"
    _kube_config_loaded = False

    @classmethod
    def hook (cls):
        self = cls()
        @kopf.on.startup()
        async def on_kopf_startup (**kwargs):
            await self.ensure_crd_exists()

        @kopf.on.delete('customresourcedefinition',
                        field='metadata.name', value=self.crd_name)
        async def on_kopf_delete_crd (**kwargs):
            logging.info("CRD is being deleted!")

            async def recreate_later ():
                for _ in range(0, 30):
                    if not await self.exists():
                        await self.ensure_crd_exists()
                        return
                    else:
                        await asyncio.sleep(1)
                else:
                    raise kopf.PermanentError("Zombie CRD won't die!")

            asyncio.create_task(recreate_later())

    async def _load_kube_config (self):
        if not self._kube_config_loaded:
            await config.load_kube_config()
            self._kube_config_loaded = True

    async def exists (self):
        await self._load_kube_config()
        async with ApiClient() as api:
            api_extensions = client.ApiextensionsV1Api(api)
            crd_list = await api_extensions.list_custom_resource_definition()
            return any(crd.metadata.name == self.crd_name for crd in crd_list.items)

    async def ensure_crd_exists(self):
        await self._load_kube_config()
        if await self.exists():
            logging.info(f"↳ CRD '{self.crd_name}' already exists, doing nothing...")
            return True

        logging.info(f"↳ CRD '{self.crd_name}' does not exists, creating it...")
        with open("WordPressSite-crd.yaml") as file:  # TODO: blocking
            crd_file = yaml.safe_load(file)
        async with ApiClient() as api:
            dyn_client = await DynamicClient(api)
            crd_resource = await dyn_client.resources.get(api_version='apiextensions.k8s.io/v1', kind='CustomResourceDefinition')
          
            try:
                await crd_resource.create(body=crd_file)
                logging.info(f"↳ CRD '{self.crd_name}' created")
                return True
            except client.exceptions.ApiException as e:
                logging.error("Error trying to create CRD :", e)
                raise e

if __name__ == '__main__':
    WordPressCRDOperator.hook()
    sys.exit(kopf.cli.main())
