import os
import shlex
import subprocess
import datetime
import logging
import json

from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.exceptions import ApiException

from wp_kubernetes import WordpressSite, KubernetesAPI


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


class WordpressSiteWithWpCli (WordpressSite):
    """Models a WordPress site.

    This class bridges the Kubernetes and PHP states together (the
    latter as seen through the `wp` CLI). It is-a
    `wp_kubernetes.WordpressSite` with extra fields (i.e., an
    `site_name`) to use when invoking WP-CLI.
    """

    @classmethod
    def all (cls, namespace):
        return [cls(wp.body, site_name=wp.name)
                for wp in WordpressSite.all(namespace)]

    def __init__ (self, body, site_name):
        super(WordpressSiteWithWpCli, self).__init__(body)

        self._site_name = site_name

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
        cmdline = ['wp', f'--site={self._site_name}'] + cmdline
        if 'DEBUG' in os.environ:
            cmdline.insert(0, 'echo')
        logging.info("Running: %s" % shlex.join(cmdline))
        return subprocess.run(cmdline, check=True, **kwargs)
