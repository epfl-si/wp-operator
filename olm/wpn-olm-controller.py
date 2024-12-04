import asyncio
import copy
import kopf
import kopf.cli
from kubernetes_asyncio import client, config, dynamic
from kubernetes_asyncio.client import ApiClient
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
    def namespace (self):
        return self.definition["metadata"].get("namespace")

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

    def copy (self, namespace=None):
        new_def = copy.deepcopy(self.definition)
        if namespace is not None:
            new_def["metadata"]["namespace"] = namespace

        return self.__class__(new_def)


async def get_dynamic_resource (api, api_version, kind, *args, **kwargs):
        dyn_client = await dynamic.DynamicClient(api)
        resource = await dyn_client.resources.get(api_version=api_version, kind=kind)
        return await resource.get(*args, **kwargs)

async def create_dynamic_resource (api, api_version, kind, **kwargs):
        dyn_client = await dynamic.DynamicClient(api)
        resource = await dyn_client.resources.get(api_version=api_version, kind=kind)
        return await resource.create(**kwargs)

async def delete_dynamic_resource (api, api_version, kind, **kwargs):
        dyn_client = await dynamic.DynamicClient(api)
        resource = await dyn_client.resources.get(api_version=api_version, kind=kind)
        return await resource.delete(**kwargs)


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
            got = await get_dynamic_resource(api, api_version=self.k8s_object.api_version, kind=self.k8s_object.kind, name=self.k8s_object.name)
            return got.reason != 'NotFound'

    async def ensure_exists (self):
        if await self.exists():
            logging.info(f"↳ {self.k8s_object.moniker} already exists, doing nothing...")
            return True

        logging.info(f"↳ {self.k8s_object.moniker} does not exist, creating it...")
        async with ApiClient() as api:
            try:
                await create_dynamic_resource(api, api_version=self.k8s_object.api_version, kind=self.k8s_object.kind, body=self.k8s_object.definition)
                logging.info(f"↳ {self.k8s_object.moniker}: created")
            except ApiException as e:
                logging.error(f"Error trying to create {self.k8s_object.moniker} :", e)
                raise e


class PerNamespaceObjectCounter:
    def __init__ (self, kind):
        logging.info("Constructing PerNamespaceObjectCounter")
        self.kind = kind
        self.on_namespace_populated_callbacks = []
        self.on_namespace_emptied_callbacks = []
        self._previous_by_namespace = {}

    def hook (self):
        id = f'{self.kind}_by_namespace'
        @kopf.index(self.kind, id=id)
        def by_namespace(name, namespace, **_):
            return { namespace: name }

        @kopf.on.event(self.kind)
        async def reconcile_by_namespace(event, **kwargs):
            by_namespace = kwargs[id]

            before = set(self._previous_by_namespace.keys())
            after = set(by_namespace.keys())

            for emptied_namespace in before - after:
                for callback in reversed(self.on_namespace_emptied_callbacks):
                    # TODO: should feed as a kopf sub-task, rather than this try/catch.
                    try:
                        await callback(emptied_namespace)
                    except BaseException as e:
                        logging.error(e)

            for populated_namespace in after - before:
                for callback in self.on_namespace_populated_callbacks:
                    # TODO: should feed as a kopf sub-task, rather than this try/catch.
                    try:
                        await callback(populated_namespace)
                    except BaseException as e:
                        logging.error(e)

            self._previous_by_namespace = copy.deepcopy(by_namespace)

    def on_namespace_populated (self, f):
        self.on_namespace_populated_callbacks.append(f)

    def on_namespace_emptied (self, f):
        self.on_namespace_emptied_callbacks.append(f)


if __name__ == '__main__':
    sites = PerNamespaceObjectCounter('wordpresssites')
    sites.hook()

    namespaced_objects = []
    for o in KubernetesObjectData.load_all("operator.yaml"):
        if not o.is_namespaced():
            ClusterWideExistenceOperator(o).hook()
        else:
            namespaced_objects.append(o)

    def rename_namespaced_objects (namespace):
        return [o.copy(namespace=namespace) for o in namespaced_objects]

    @sites.on_namespace_populated
    async def startup_operator (namespace):
        async with ApiClient() as api:
            for o in rename_namespaced_objects(namespace):
                try:
                    await create_dynamic_resource(
                        api,
                        o.api_version,
                        o.kind,
                        body=o.definition)
                    logging.info(f"{o.moniker}: created")
                except BaseException as e:
                    logging.error(f"Error creating {o.moniker}: {e}")

    @sites.on_namespace_emptied
    async def shutdown_operator (namespace):
        async with ApiClient() as api:
            for o in reversed(rename_namespaced_objects(namespace)):
                try:
                    await delete_dynamic_resource(
                        api,
                        o.api_version,
                        o.kind,
                        namespace=o.namespace,
                        name=o.name)
                    logging.info(f"{o.moniker}: deleted")
                except BaseException as e:
                    logging.error(f"Error deleting {o.moniker}: {e}")

    sys.exit(kopf.cli.main())
