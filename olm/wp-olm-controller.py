import asyncio
import copy
from functools import cached_property
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

    @classmethod
    def by_meta (cls, meta):
        """Returns a “dud” object with only the metadata.

        This object is sufficient for equality checking."""
        return cls(dict(metadata=meta))

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

    def kopf_daemon(self, f):
        def is_me (name, namespace, **_):
            return (self.name == name and
                    self.namespace == namespace)

        return kopf.daemon(self.api_version, self.kind, when=is_me)(f)

    @property
    def as_get_dynamic_resource_args (self):
        ret = dict(api_version=self.api_version, kind=self.kind, name=self.name)

        if self.namespace:
            ret["namespace"] = self.namespace

        return ret

    def move_to_namespace (self, new_namespace):
        other = copy.deepcopy(self.definition)
        other["metadata"]["namespace"] = new_namespace
        return self.__class__(other)

    @property
    def moniker (self):
        moniker = f"{self.kind}/{self.name}"
        namespace = self.namespace
        if namespace:
            moniker = f"{moniker} in namespace {namespace}"
        return moniker

    def __eq__ (self, other):
        return self.name == other.name and self.namespace == other.namespace


def raise_if_status_failed(resource_instance):
    """
    Raises an exception if the ResourceInstance indicates a failure.
    """
    if getattr(resource_instance, 'kind', None) != 'Status':
        return   # Something has been returned, e.g. from `get_dynamic_resource()`
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
        ret = await resource.get(**kwargs)
        raise_if_status_failed(ret)
        return ret


class ExistenceReconciler:
    """Enforce that an object exists, and continues doing so.

    Create it on startup, or after it is actually deleted (i.e. is
    gone from the Kubernetes store; as opposed to just being marked
    for deletion).

    Works for both namespaced and cluster-wide objects.

    """
    def __init__ (self, k8s_object):
        self.k8s_object = k8s_object

    @property
    def moniker (self):
        return f"<{self.__class__.__name__}({self.k8s_object.moniker})>"

    def hook (self):
        logging.info(f"{self.moniker}: starting")
        @kopf.on.startup()
        async def on_kopf_startup (**kwargs):
            logging.info(f"{self.moniker}: started")
            await self.ensure_exists()

        @self.k8s_object.kopf_daemon
        async def watch (stopped, meta, **kwargs):
            if self.k8s_object != KubernetesObjectData.by_meta(meta):
                return

            while not stopped:
                # As per https://kopf.readthedocs.io/en/stable/daemons/#safe-sleep
                # stopped.wait() puts us in a “light sleep”; therefore a long delay is best.
                await stopped.wait(3600)
            if "deletionTimestamp" not in meta:
                return     # We are being stopped because the whole process is terminating

            asyncio.create_task(self._recreate_later())

    _kube_config_loaded = False

    async def _load_config (self):
        if not self._kube_config_loaded:
            await config.load_config()
            self._kube_config_loaded = True

    async def exists (self):
        await self._load_config()
        async with ApiClient() as api:
            try:
                await get_dynamic_resource(api, **self.k8s_object.as_get_dynamic_resource_args)
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

    async def _recreate_later (self):
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


class OperatorController:
    """Ensure that the WordPress operator and its support objects run
    in every namespace with at least one WordpressSite.

    Conversely, delete everything once the last `WordpressSite` object
    in a namespace is deleted.

    The `hook` class method gets everything going (using the
    `PerNamespaceObjectCounter` class as the watcher). Per-namespace
    instances are then created on-demand behind the scenes.
    """
    controlled_objects_file = "operator-namespaced.yaml"
    sample_namespace_in_controlled_objects_file = "wordpress-test"

    @classmethod
    def hook (cls):
        sites = PerNamespaceObjectCounter('wordpresssites')
        sites.hook()

        @sites.on_namespace_populated
        async def startup_operator (namespace):
            await cls.by_namespace(namespace).ensure_objects_created()

        @sites.on_namespace_emptied
        async def shutdown_operator (namespace):
            await cls.by_namespace(namespace).ensure_objects_deleted()

    _instances = {}
    @classmethod
    def by_namespace (cls, namespace):
        if namespace not in cls._instances:
            cls._instances[namespace] = OperatorController(namespace)
        return cls._instances[namespace]

    def __init__ (self, namespace):
        """Private constructor, please call `by_namespace()` instead."""
        self.namespace = namespace

    @cached_property
    def k8s_objects (self):
        """Personalize the objects that need controlling for `self.namespace`.

        This involves full-text substitution in the YAML (YUCK!!), so that
        Kubernetes-style object pointers are updated correctly; and also to maintain a
        per-namespace copy of non-namespaced objects (such as
        `ClusterRoleBinding`s).

        Returns a `reversed`-friendly iterable.
        """
        with open(self.controlled_objects_file) as f:
            yaml_substituted = re.sub(self.sample_namespace_in_controlled_objects_file,
                                      self.namespace,
                                      f.read())

        return list(KubernetesObjectData.parse_all(yaml_substituted))

    async def ensure_objects_created (self):
        async with ApiClient() as api:
            for o in self.k8s_objects:
                try:
                    await create_dynamic_resource(
                        api,
                        o.api_version,
                        o.kind,
                        body=o.definition)
                    logging.info(f"{o.moniker}: created")
                except BaseException as e:
                    logging.error(f"Error creating {o.moniker}: {e}")

    async def ensure_objects_deleted (self):
        async with ApiClient() as api:
            for o in reversed(self.k8s_objects):
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


@kopf.on.startup()
def tune_kopf_settings(settings, **_):
    settings.posting.level = logging.DEBUG
    # We are never going to set a finalizer in a WordPressSite object...
    # but we also do *not* want to keep removing the ones that the
    # operator sets; and cause a causality loop with it!
    settings.persistence.finalizer = 'epfl.ch/olm-controller-you-should-never-see-this-finalizer'


if __name__ == '__main__':
    for o in KubernetesObjectData.load_all("operator-non-namespaced.yaml"):
        ExistenceReconciler(o).hook()

    OperatorController.hook()

    sys.exit(kopf.cli.main())
