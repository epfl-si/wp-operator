import asyncio
import kopf
import kopf.cli
from kubernetes_asyncio import client, config
from kubernetes_asyncio.client import ApiClient
from kubernetes_asyncio.dynamic import DynamicClient
from kubernetes_asyncio.client.exceptions import ApiException
from kubernetes_asyncio.dynamic.exceptions import NotFoundError
import logging
import os
import sys
import threading
import time
import yaml

class ClusterWideExistenceOperator:
    def __init__ (self, definition):
        self.definition = definition

    @property
    def name (self):
        return self.definition["metadata"]["name"]

    @property
    def kind (self):
        return self.definition["kind"]

    @property
    def api_version (self):
        return self.definition["apiVersion"]

    @property
    def moniker (self):
        return f"{self.kind}/{self.name}"

    def hook (self):
        @kopf.on.startup()
        async def on_kopf_startup (**kwargs):
            await self.ensure_exists()

        @kopf.on.delete(self.kind,
                        field='metadata.name', value=self.name)
        async def on_kopf_delete_crd (**kwargs):
            logging.info(f"{self.moniker} is being deleted!")

            async def recreate_later ():
                for _ in range(0, 30):
                    if not await self.exists():
                        await self.ensure_exists()
                        return
                    else:
                        await asyncio.sleep(1)
                else:
                    logging.error(f"Zombie {self.moniker} won't die!")
                    raise kopf.PermanentError(f"Zombie {self.moniker} won't die!")

            asyncio.create_task(recreate_later())

    _kube_config_loaded = False

    async def _load_kube_config (self):
        if not self._kube_config_loaded:
            await config.load_kube_config()
            self._kube_config_loaded = True

    async def exists (self):
        await self._load_kube_config()
        async with ApiClient() as api:
            dyn_client = await DynamicClient(api)
            resource = await dyn_client.resources.get(api_version=self.api_version, kind=self.kind)
            got = await resource.get(name=self.name)
            return got.reason != 'NotFound'

    async def ensure_exists (self):
        if await self.exists():
            logging.info(f"↳ {self.moniker} already exists, doing nothing...")
            return True

        logging.info(f"↳ {self.moniker} does not exist, creating it...")
        async with ApiClient() as api:
            dyn_client = await DynamicClient(api)
            resource = await dyn_client.resources.get(api_version=self.api_version, kind=self.kind)

            try:
                await resource.create(body=self.definition)
                logging.info(f"↳ {self.moniker}: created")
            except ApiException as e:
                logging.error(f"Error trying to create {self.moniker} :", e)
                raise e

if __name__ == '__main__':
    ClusterWideExistenceOperator(yaml.safe_load(open('WordPressSite-crd.yaml'))).hook()
    sys.exit(kopf.cli.main())
