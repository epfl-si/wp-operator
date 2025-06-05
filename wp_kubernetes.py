"""A Kubernetes bag-of-tricks, with no pretention for general reusability."""

import base64
from functools import cached_property
import logging
import re
import threading
import time
import uuid
import sys

import kubernetes
import kubernetes.client
import kubernetes.dynamic
import kubernetes.leaderelection.leaderelection
import kubernetes.leaderelection.electionconfig
from kubernetes.leaderelection.resourcelock.configmaplock import ConfigMapLock


class classproperty:
    def __init__(self, func):
        self.fget = func
    def __get__(self, instance, owner):
        return self.fget(owner)


class KubernetesAPI:
    """A dispenser of singletons to access the Kubernetes API easily."""
    __singleton = None

    @classmethod
    def __get(cls):
        if cls.__singleton is None:
            cls.__singleton = cls()

        return cls.__singleton

    def __init__(self):
        kubernetes.config.load_config()

        self._custom = kubernetes.client.CustomObjectsApi()
        self._core = kubernetes.client.CoreV1Api()
        self._extensions = kubernetes.client.ApiextensionsV1Api()
        self._dynamic = kubernetes.dynamic.DynamicClient(kubernetes.client.ApiClient())
        self._networking = kubernetes.client.NetworkingV1Api()

        class ApiClientForJsonPatch(kubernetes.client.ApiClient):
            """As seen in https://github.com/kubernetes-client/python/issues/1216#issuecomment-691116322"""
            def call_api(self, resource_path, method,
                         path_params=None, query_params=None, header_params=None,
                         body=None, post_params=None, files=None,
                         response_type=None, auth_settings=None, async_req=None,
                         _return_http_data_only=None, collection_formats=None,
                         _preload_content=True, _request_timeout=None):
                header_params['Content-Type'] = self.select_header_content_type(['application/json-patch+json'])
                return super().call_api(resource_path, method, path_params, query_params, header_params, body,
                                        post_params, files, response_type, auth_settings, async_req, _return_http_data_only,
                                        collection_formats, _preload_content, _request_timeout)

        self._custom_jsonpatch = kubernetes.client.CustomObjectsApi(ApiClientForJsonPatch())

    @classproperty
    def custom(cls):
        return cls.__get()._custom

    @classproperty
    def custom_jsonpatch(cls):
        return cls.__get()._custom_jsonpatch

    @classproperty
    def core(cls):
        return cls.__get()._core

    @classproperty
    def extensions(cls):
        return cls.__get()._extensions

    @classproperty
    def dynamic(cls):
        return cls.__get()._dynamic

    @classproperty
    def networking(cls):
        return cls.__get()._networking


class KubernetesObject:
    """Model for a persistent record in the Kubernetes API server.

    This is an abstract base class. Instantiable subclasses are named after
    the `kind:` of the objects they model.
    """
    @property
    def moniker (self):
        # Do *not* call self.field (even indirectly) to avoid a loop:
        namespace_moniker_fragment = f" in namespace {self.namespace}" if self.namespace else ""
        return f"<{self.kind}/{self.name}{namespace_moniker_fragment}>"

    @property
    def uid (self):
        return self.field('metadata.uid')

    @property
    def owner_uid (self):
        owners = self.field('metadata.ownerReferences', None)
        if not owners:
            return None
        elif len(owners) > 1:
            raise ValueError("wp_operator cannot deal with objects that have multiple owners")
        else:
            return self.field("uid", starting_from=owners[0])

    @property
    def owner_reference (self):
        return dict(
            apiVersion=self.api_version,
            kind=self.kind,
            name=self.name,
            uid=self.uid)

    def _filter_owned (self, candidates):
        return [c for c in candidates
                if c.owner_uid == self.uid]

    def _sole_owned (self, candidates):
        candidates = self._filter_owned(candidates)
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) == 0:
            raise ValueError(f"No object owned by {self.moniker}")
        else:
            raise ValueError(f"Found {len(candidates)} {candidates[0].kind}s owned by {self.moniker}, expected just one")
            return candidates


class KubernetesBuiltinObject (KubernetesObject):
    """One of the “built-in” (metaprogrammed) objects in the Kubernetes store.

    This is an abstract base class. Instantiable subclasses are named after
    the `kind:` of the objects they model.
    """

    @classmethod
    def from_list (cls, k8s_list, owner=None):
        return [cls(s) for s in k8s_list.items]

    def __init__ (self, definition):
        self._definition = definition

    @property
    def kind (self):
        return self.__class__.__name__   # Meh - Good enough, we don't use it
                                         # for anything serious anyway 😜

    @property
    def api_version (self):
        return "v1"                      # See comment above

    @property
    def name (self):
        return self._definition.metadata.name

    @property
    def namespace (self):
        return self._definition.metadata.namespace

    __UNSET = object()

    def field (self, field_path, default=__UNSET, *, starting_from=None):
        walk = starting_from if starting_from is not None else self._definition
        for fragment in field_path.split("."):
            try:
                walk = getattr(walk, self._to_snake_case(fragment))
            except AttributeError:
                # At some point during the drill-down (e.g. below a
                # Secret's `.data`), even the “built-in” types turn to
                # dicts 🤷‍♂️
                if default is not self.__UNSET and fragment not in walk:
                    return default
                walk = walk.get(fragment)
        return walk

    @classmethod
    def _to_snake_case(cls, name):
        """
        Convert camelCase or PascalCase to snake_case.
        Example: 'ownerReferences' → 'owner_references'
        """
        s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
        s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()


class Secret (KubernetesBuiltinObject):
    kind = "Secret"

    @classmethod
    def all (cls, namespace):
        return cls.from_list(
            KubernetesAPI.core.list_namespaced_secret(namespace=namespace))

    def decode (self, field):
        return base64.b64decode(self.field(f"data.{field}"))

    @property
    def mariadb_password (self):
        return self.decode("password")


class Service (KubernetesBuiltinObject):
    @classmethod
    def all (cls, namespace):
        return cls.from_list(
            KubernetesAPI.core.list_namespaced_service(
                namespace=namespace))

    @property
    def publish_not_ready_addresses (self):
        return self._definition.spec.publish_not_ready_addresses

    @property
    def ports (self):
        return self._definition.spec.ports


class CustomAPIKubernetesObject (KubernetesObject):
    """An instance of one of the Kubernetes object whose type is not
    known until run time (e.g. because it belongs to a CRD).

    This is an abstract base class. Instantiable subclasses are named after
    the `kind:` of the objects they model.
    """
    def __init__ (self, definition):
        if not isinstance(definition, dict):
            raise ValueError(f"{definition} is not a Kubernetes object")
        self._definition = definition

    @classmethod
    def all (cls, namespace):
        return cls.from_list(
            KubernetesAPI.custom.list_namespaced_custom_object(
                namespace=namespace, **cls._search_kwargs))

    @classmethod
    def from_list (cls, k8s_list):
        if "items" in k8s_list:
            return [cls(s) for s in k8s_list["items"]]
        else:
            raise ValueError(f"Unexpected type {type(k8s_list)} in from_list")

    @classmethod
    def get (cls, namespace, name):
        return cls(KubernetesAPI.custom.get_namespaced_custom_object(
            name = name,
            namespace=namespace,
            **cls._search_kwargs))

    __UNSET = object()

    def field (self, field_path, default=__UNSET, *, starting_from=None):
        walk = starting_from if starting_from is not None else self._definition
        for fragment in field_path.split("."):
            walk = walk.get(fragment)
            if walk is None:
                if default is self.__UNSET:
                    raise ValueError(f"{field_path} not found in {self.moniker}")
                else:
                    return default
        return walk

    # These accessors are called by `KubernetesObject().moniker` and
    # therefore, should not use `.field`:
    @property
    def kind (self):
        return self._definition.get("kind", "(Unknown kind)")

    @property
    def api_version (self):
        return self._definition.get("apiVersion", "(Unknown apiVersion)")

    @property
    def name (self):
        return self._definition.get("metadata", {}).get("name", None)

    @property
    def namespace (self):
        return self._definition.get("metadata", {}).get("namespace", None)


class MariaDBUser (CustomAPIKubernetesObject):
    _search_kwargs = dict(group="k8s.mariadb.com",
                          version="v1alpha1",
                          plural="users")

    @property
    def username (self):
        explicit_name = self.field("spec.name", None)
        return (explicit_name if explicit_name is not None
                else self.name)


class MariaDBDatabase (CustomAPIKubernetesObject):
    _search_kwargs = dict(group="k8s.mariadb.com",
                          version="v1alpha1",
                          plural="databases")

    @property
    def dbname (self):
        explicit_name = self.field("spec.name", None)
        return (explicit_name if explicit_name is not None
                else self.name)

    @property
    def mariadb (self):
        return MariaDB.get(
            name=self.field("spec.mariaDbRef.name"),
            namespace=self.namespace)


class MariaDB (CustomAPIKubernetesObject) :
    _search_kwargs = dict(group="k8s.mariadb.com",
                          version="v1alpha1",
                          plural="mariadbs")

    @property
    def service (self):
        for s in self._filter_owned(Service.all(namespace=self.namespace)):
            if not s.publish_not_ready_addresses:
                for p in s.ports:
                    if p.name == "mariadb":
                        return s


class WordpressSite (CustomAPIKubernetesObject):
    _search_kwargs = dict(group='wordpress.epfl.ch',
                          version='v2',
                          plural='wordpresssites')

    @property
    def path (self):
        return self.field("spec.path")

    @property
    def hostname (self):
        return self.field("spec.hostname")

    @property
    def protection_script (self):
        return self.field("spec.wordpress.downloadsProtectionScript", None)

    @property
    def unit_id (self):
        return self.field("spec.owner.epfl.unitId")

    @property
    def title (self):
        return self.field("spec.wordpress.title")

    @property
    def tagline (self):
        return self.field("spec.wordpress.tagline")

    @cached_property
    def database (self):
        return self._sole_owned(MariaDBDatabase.all(namespace=self.namespace))

    @cached_property
    def user (self):
        return self._sole_owned(MariaDBUser.all(namespace=self.namespace))

    @cached_property
    def secret (self):
        return self._sole_owned(Secret.all(namespace=self.namespace))


class NamespaceLeaderElection:
    def __init__(self, namespace, onstarted_leading):
        self.lock_namespace = namespace
        self.onstarted_leading = onstarted_leading
        self.lock_name = f"wp-operator-lock"
        self.candidate_id = uuid.uuid4()
        self.config = kubernetes.leaderelection.electionconfig.Config(
            ConfigMapLock(
                self.lock_name,
                self.lock_namespace,
                self.candidate_id
            ),
            lease_duration = 17,
            renew_deadline = 15,
            retry_period = 5,
            onstarted_leading = self.start_work_in_thread,
            onstopped_leading = self.exit_immediately
        )

    def start_work_in_thread(self):
        logging.info(f"Instance {self.candidate_id} is the leader for namespace {self.lock_namespace}.")

        threading.Thread(target=self.onstarted_leading).run()

    def exit_immediately(self):
        logging.info(f"Instance {self.candidate_id} stopped being the leader for namespace {self.lock_namespace}.")
        sys.exit(0)

    @classmethod
    def go (cls, namespace, onstarted_leading):
        kubernetes.config.load_config()
        leader_election = cls(namespace, onstarted_leading)

        class QuietLeaderElection(kubernetes.leaderelection.leaderelection.LeaderElection):
            def update_lock(self, leader_election_record):
                """(Copied and) overridden to silence the “has successfully acquired lease” message every 5 seconds."""
                # Update object with latest election record
                update_status = self.election_config.lock.update(self.election_config.lock.name,
                                                                 self.election_config.lock.namespace,
                                                                 leader_election_record)

                if update_status is False:
                    logging.info("{} failed to acquire lease".format(leader_election_record.holder_identity))
                    return False

                self.observed_record = leader_election_record
                self.observed_time_milliseconds = int(time.time() * 1000)
                return True

        QuietLeaderElection(leader_election.config).run()
