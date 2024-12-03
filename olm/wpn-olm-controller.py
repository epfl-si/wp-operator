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


class KubernetesObjectData:
    @classmethod
    def load (cls, path):
        [o] = cls.load_all(path)
        return o

    @classmethod
    def load_all (cls, path):
        return (cls(o) for o in yaml.safe_load_all(open(path, 'r')))

    def __init__ (self, deserialized_data):
        self.definition = deserialized_data

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

    def is_namespaced (self):
        return "namespace" in self.definition["metadata"]


class ClusterWideExistenceOperator:
    def __init__ (self, k8s_object):
        self.k8s_object = k8s_object

    def hook (self):
        @kopf.on.startup()
        async def on_kopf_startup (**kwargs):
            await self.ensure_exists()

        @kopf.daemon(self.k8s_object.kind,
                     field='metadata.name', value=self.k8s_object.name)
        async def watch (stopped, meta, **kwargs):
            while not stopped:
                # As per https://kopf.readthedocs.io/en/stable/daemons/#safe-sleep
                # stopped.wait() puts us in a “light sleep”; therefore a long delay is best.
                await stopped.wait(3600)
            if "deletionTimestamp" not in meta:
                return     # We are being stopped because the whole process is terminating

            async def recreate_later ():
                """Wait for our Kubernetes object to actually go off the books; then recreate it."""
                for _ in range(0, 30):
                    if not await self.exists():
                        await self.ensure_exists()
                        return
                    else:
                        await asyncio.sleep(1)
                else:
                    logging.error(f"Zombie {self.k8s.moniker} won't die!")
                    raise kopf.PermanentError(f"Zombie {self.k8s.moniker} won't die!")

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
            resource = await dyn_client.resources.get(api_version=self.k8s_object.api_version, kind=self.k8s_object.kind)
            got = await resource.get(name=self.k8s_object.name)
            return got.reason != 'NotFound'

    async def ensure_exists (self):
        if await self.exists():
            logging.info(f"↳ {self.k8s_object.moniker} already exists, doing nothing...")
            return True

        logging.info(f"↳ {self.k8s_object.moniker} does not exist, creating it...")
        async with ApiClient() as api:
            dyn_client = await DynamicClient(api)
            resource = await dyn_client.resources.get(api_version=self.k8s_object.api_version, kind=self.k8s_object.kind)

            try:
                await resource.create(body=self.k8s_object.definition)
                logging.info(f"↳ {self.k8s_object.moniker}: created")
            except ApiException as e:
                logging.error(f"Error trying to create {self.k8s_object.moniker} :", e)
                raise e


if __name__ == '__main__':
    crd = KubernetesObjectData.load('WordPressSite-crd.yaml')
    ClusterWideExistenceOperator(crd).hook()
    for o in KubernetesObjectData.load_all("operator.yaml"):
        if not o.is_namespaced():
            ClusterWideExistenceOperator(o).hook()
    sys.exit(kopf.cli.main())
