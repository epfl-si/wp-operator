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
import re
import io


class KubernetesObjectData:
    @classmethod
    def load (cls, path):
        [o] = cls.load_all(path)
        return o

    @classmethod
    def load_all (cls, path):
        return cls._load_all_from_stream(open(path, "r"))

    @classmethod
    def parse_all (cls, yaml_string):
        return cls._load_all_from_stream(io.StringIO(yaml_string))

    @classmethod
    def _load_all_from_stream (cls, f):
        return (cls(o) for o in yaml.safe_load_all(f))

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
    def as_kopf_resource_selector (self):
        return (self.api_version, self.kind)

    @property
    def moniker (self):
        moniker = f"{self.kind}/{self.name}"
        namespace = self.namespace
        if namespace:
            moniker = f"{moniker} in namespace {namespace}"
        return moniker


def raise_if_status_failed(resource_instance):
    """
    Raises an exception if the ResourceInstance indicates a failure.
    """
    if getattr(resource_instance, 'status', None) == "Failure":
        reason = getattr(resource_instance, 'reason', 'Unknown reason')
        message = getattr(resource_instance, 'message', 'No message provided')
        code = getattr(resource_instance, 'code', 500)

        raise ApiException(status=code, reason=f'{reason}. {message}')

async def create_dynamic_resource (api, api_version, kind, **kwargs):
        dyn_client = await dynamic.DynamicClient(api)
        resource = await dyn_client.resources.get(api_version=api_version, kind=kind)
        status = await resource.create(**kwargs)
        raise_if_status_failed(status)

async def delete_dynamic_resource (api, api_version, kind, **kwargs):
        dyn_client = await dynamic.DynamicClient(api)
        resource = await dyn_client.resources.get(api_version=api_version, kind=kind)
        status = await resource.delete(**kwargs)
        raise_if_status_failed(status)

async def get_dynamic_resource (api, api_version, kind, **kwargs):
        dyn_client = await dynamic.DynamicClient(api)
        resource = await dyn_client.resources.get(api_version=api_version, kind=kind)
        status = await resource.get(**kwargs)
        raise_if_status_failed(status)


class ClusterWideExistenceOperator:
    def __init__ (self, k8s_object):
        self.k8s_object = k8s_object

    def hook (self):
        @kopf.on.startup()
        async def on_kopf_startup (**kwargs):
            await self.ensure_exists()

        @kopf.daemon(*self.k8s_object.as_kopf_resource_selector,
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

    async def _load_config (self):
        if not self._kube_config_loaded:
            await config.load_config()
            self._kube_config_loaded = True

    async def exists (self):
        await self._load_config()
        async with ApiClient() as api:
            try:
                await get_dynamic_resource(api, api_version=self.k8s_object.api_version, kind=self.k8s_object.kind, name=self.k8s_object.name)
                return True
            except ApiException as e:
                if not e.reason.startswith('NotFound'):
                    raise
                else:
                    return False

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
        self._previous_objects_by_namespace = {}
        self._previous_objects_by_namespace_mutex = threading.Lock()

    def hook (self):
        index_name = f'{self.kind}_by_namespace'
        @kopf.index(self.kind, id=index_name)
        def by_namespace(name, namespace, **_):
            return { namespace: name }

        @kopf.on.event(self.kind)
        async def reconcile_by_namespace(event, **kwargs):
            new_objects_by_namespace = kwargs[index_name]   # Provided by the `@kopf.index` thing, above

            with self._previous_objects_by_namespace_mutex:
                before = set(self._previous_objects_by_namespace.keys())
                after = set(new_objects_by_namespace.keys())
                self._previous_objects_by_namespace = copy.deepcopy(new_objects_by_namespace)

            for emptied_namespace in before - after:
                logging.info(f"Namespace {emptied_namespace} is now empty of {self.kind}s")
                for callback in reversed(self.on_namespace_emptied_callbacks):
                    # TODO: should feed as a kopf sub-task, rather than this try/catch.
                    try:
                        await callback(emptied_namespace)
                    except BaseException as e:
                        logging.error(e)

            for populated_namespace in after - before:
                logging.info(f"Namespace {populated_namespace} now contains at least one {self.kind}")
                for callback in self.on_namespace_populated_callbacks:
                    # TODO: should feed as a kopf sub-task, rather than this try/catch.
                    try:
                        await callback(populated_namespace)
                    except BaseException as e:
                        logging.error(e)

    def on_namespace_populated (self, f):
        self.on_namespace_populated_callbacks.append(f)

    def on_namespace_emptied (self, f):
        self.on_namespace_emptied_callbacks.append(f)


@kopf.on.startup()
def tune_kopf_settings(settings, **_):
    settings.posting.level = logging.DEBUG
    # We are never going to set a finalizer in a WordPressSite object...
    # but we also do *not* want to keep removing the ones that the
    # operator sets; and cause a causality loop with it!
    settings.persistence.finalizer = 'epfl.ch/olm-controller-you-should-never-see-this-finalizer'

if __name__ == '__main__':
    sites = PerNamespaceObjectCounter('wordpresssites')
    sites.hook()

    for o in KubernetesObjectData.load_all("operator-non-namespaced.yaml"):
        ClusterWideExistenceOperator(o).hook()

    def load_namespaced_objects (substitute_namespace):
        with open("operator-namespaced.yaml") as f:
            namespaced_objects_yaml = f.read()
            namespaced_objects_yaml = re.sub("wordpress-test", substitute_namespace, namespaced_objects_yaml)

        return KubernetesObjectData.parse_all(namespaced_objects_yaml)

    @sites.on_namespace_populated
    async def startup_operator (namespace):
        async with ApiClient() as api:
            for o in load_namespaced_objects(substitute_namespace=namespace):
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
            for o in reversed(list(load_namespaced_objects(substitute_namespace=namespace))):
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
