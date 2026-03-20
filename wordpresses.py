import os
import shlex
import subprocess
import datetime
import logging
import json

from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.exceptions import ApiException

from wp_kubernetes import WordpressSite as WordpressSiteK8s, KubernetesAPI


class _BagBase:
    def __init__ (self, items):
        self._bag = {}
        for i in items:
            self.add(i)

    def lookup (self, uid):
        return self._bag[uid]

    def items (self):
        return self._bag.items()

    def keys (self):
        return self._bag.keys()

    def values (self):
        return self._bag.values()


class BagOfWordpressSites (_BagBase):
    def add (self, wp):
        uid = wp.uid
        self._bag[uid] = wp


class BagOfIngresses (_BagBase):
    def add (self, ingress):
        if (ingress['metadata'].get('ownerReferences')):
            owner_uid = ingress['metadata']['ownerReferences'][0]['uid']
            self._bag[owner_uid] = ingress


class WordpressSite:
    """Models a WordPress site.

    This class bridges the Kubernetes and PHP states together (the
    latter as seen through the `wp` CLI). It is-a
    `wp_kubernetes.WordpressSite` with extra fields (i.e., an
    `ingress_name`) to use when invoking WP-CLI.
    """

    @classmethod
    def all (cls, namespace):
        def get_custom_resource_items (group, version, namespace, plural):
            api_response = KubernetesAPI.custom.list_namespaced_custom_object(group, version, namespace, plural)
            return api_response['items']

        ingresses = get_custom_resource_items(
            "networking.k8s.io", "v1", namespace, "ingresses")
        wordpresssites = WordpressSiteK8s.all(namespace)

        bag_ingress = BagOfIngresses(ingresses)
        bag_wp = BagOfWordpressSites(wordpresssites)

        ret = []
        for uid, ingress in bag_ingress.items():
            wp = bag_wp.lookup(uid)
            if not wp:
                continue

            ret.append(cls(wp.body, ingress_name=ingress["metadata"]["name"]))

        return ret

    def __init__ (self, body, ingress_name):
        super(WordpressSite, self).__init__(body)

        self._ingress_name = ingress_name


    def status_deep_merge(self, *args, **kwargs):
        return self.status_deep_merge(*args, **kwargs)

    def status_set_key(self, *args, **kwargs):
        return self.status_set_key(*args, **kwargs)

    def update_php_status (self):
        """
        Patch the `wordpressite` field in the CR status with
        the structure returned by the `wp_operator_status` WordPress filter.
        """
        logging.info(f"{self.moniker}: update_php_status")
        if 'DEBUG' in os.environ:
            return

        armor = "===== %s WORDPRESS JSON STATUS ====="
        armor_begin = armor % "BEGIN"
        armor_end = armor % "END"

        cmdline = ['eval',
                   '''$w = apply_filters('wp_operator_status',[]); ''' +
                   '''echo("%s\n"); ''' % armor_begin +
                   '''echo(json_encode($w, JSON_PRETTY_PRINT)); ''' +
                   '''echo("%s\n");''' % armor_end]
        result = self.run_wp_cli(cmdline, capture_output=True, text=True)

        start = result.stdout.find(armor_begin)
        end = result.stdout.find(armor_end)
        if start == -1 or end == -1 or end <= start:
          raise RuntimeError("No armored JSON output: %s" % result.stdout)

        unarmored = result.stdout[start + len(armor_begin):end]
        try:
          status_wordpresssite = json.loads(unarmored)
        except json.JSONDecodeError:
          raise RuntimeError("unparseable JSON: %s" % unarmored)

        self.status_set_key("wordpresssite", status_wordpresssite)

    def run_wp_cli (self, cmdline, **kwargs):
        cmdline = ['wp', f'--ingress={self._ingress_name}'] + cmdline
        if 'DEBUG' in os.environ:
            cmdline.insert(0, 'echo')
        logging.info("Running: %s" % shlex.join(cmdline))
        return subprocess.run(cmdline, check=True, **kwargs)
