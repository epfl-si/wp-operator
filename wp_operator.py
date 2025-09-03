# Kopf documentation : https://kopf.readthedocs.io/
#
# Run with `python3 wp_operator.py run --`
#
import argparse
import base64
import datetime
from functools import cached_property
import logging
import os
import re
import secrets
import sys
import time
import shlex
import subprocess
import json

import kopf
import kopf.cli
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from urllib3 import disable_warnings
# Remove warning: InsecureRequestWarning (Unverified HTTPS request is being made to host 'api.okd-test.fsd.team'.
# Adding certificate verification is strongly advised. See: https://urllib3.readthedocs.io/en/latest/advanced-usage.html#tls-warnings)
from urllib3.exceptions import InsecureRequestWarning

from php import phpize
from wp_kubernetes import KubernetesAPI, WordpressSite, NamespaceLeaderElection


disable_warnings(InsecureRequestWarning)

class Config:
    secret_name = "nginx-conf-site-tree"
    saved_argv = [arg for arg in sys.argv]

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(
            prog='wp-operator',
            description='The EPFL WordPress Operator',
            epilog='Happy operating!')

        parser.add_argument('--wp-dir', help='The path to the WordPress sources to load and call.',
                            default="../volumes/wp/")   # TODO: this only makes sense in dev.
        parser.add_argument('--php', help='The path to the PHP command-line (CLI) executable.',
                            default="php")
        parser.add_argument('--wp-php-ensure', help='The path to the PHP script that ensures the postconditions.',
                            default=cls.file_in_script_dir("ensure-wordpress-and-theme.php"))
        parser.add_argument('--secret-dir', help='Secret file\'s directory.',
                            default="secretFiles")
        parser.add_argument('--max-workers', help='Max number of `WordPressSite`s to operate on at the same time',
                            type=int,
                            default=10)
        return parser

    @classmethod
    def load_from_command_line(cls):
        argv = cls.splice_our_argv()
        if argv is None:
            # Passing no flags to .parser() is legit, since all of them have default values.
            argv = []

        cmdline = cls.parser().parse_args(argv)
        cls.php = cmdline.php
        cls.wp_dir = os.path.join(cmdline.wp_dir, '')
        cls.secret_dir = cmdline.secret_dir
        cls.max_workers = cmdline.max_workers

    @classmethod
    def script_dir(cls):
        for arg in cls.saved_argv:
            if "wp_operator.py" in arg:
                script_full_path = os.path.join(os.getcwd(), arg)
                return os.path.dirname(script_full_path)
        return "."  # Take a guess

    @classmethod
    def file_in_script_dir(cls, basename):
        return os.path.join(cls.script_dir(), basename)

    @classmethod
    def splice_our_argv(cls):
        if "--" in sys.argv:
            # E.g.   python3 ./wp_operator.py run -n wordpress-toto -- --php=/usr/local/bin/php --wp-dir=yadda/yadda
            end_of_kopf = sys.argv.index("--")
            ret = sys.argv[end_of_kopf + 1:]
            sys.argv[end_of_kopf:] = []
            return ret
        else:
            return None

@kopf.on.startup()
def on_kopf_startup (settings, **_):
    settings.scanning.disabled = True
    settings.execution.max_workers = Config.max_workers


class MariaDBPlacer:
    def __init__(self):
        self._mariadbs_by_namespace = {}

        # TODO wait for KOPF to be done sending us the initial updates

        @kopf.on.event('databases.k8s.mariadb.com')
        def on_event_database(event, spec, name, namespace, patch, **kwargs):
            if (event['type'] in [None, 'ADDED', 'MODIFIED']):
                databases = self._mariadbs_at(namespace, spec['mariaDbRef']['name']).setdefault("databases", [])
                db_exist = False
                for db in databases:
                    if (db['name'] == name and db['namespace'] == namespace):
                        db_exist = True
                if not db_exist:
                    self._mariadbs_at(namespace, spec['mariaDbRef']['name']).setdefault("databases", []).append(
                        {'name': name, 'namespace': namespace, 'spec': spec})
            elif (event['type'] == 'DELETED'):
                previous_databases = self._mariadbs_at(namespace, spec['mariaDbRef']['name']).setdefault("databases",
                                                                                                         [])
                self._mariadbs_at(namespace, spec['mariaDbRef']['name'])["databases"] = [
                    db for db in previous_databases
                    if not (db['name'] == name and db['namespace'] == namespace)
                ]
            self._log_mariadbs()

        @kopf.on.event('mariadbs')
        def on_event_mariadb(event, spec, name, namespace, labels, patch, **kwargs):
            if (labels and labels['wpAutoallocate']):
                if (event['type'] in [None, 'ADDED', 'MODIFIED']):
                    self._mariadbs_at(namespace, name)["spec"] = spec
                elif (event['type'] == 'DELETED'):
                    if namespace in self._mariadbs_by_namespace:
                        if name in self._mariadbs_by_namespace[namespace]:
                            del self._mariadbs_by_namespace[namespace][name]
            self._log_mariadbs()

    def _mariadbs_at(self, namespace, name):
        return self._mariadbs_by_namespace.setdefault(namespace, {}).setdefault(name, {})

    def _log_mariadbs(self):
        for namespace_name, content in self._mariadbs_by_namespace.items():
            # Create a copy to prevent RuntimeError (dictionary changed size during iteration)
            content_copy = content.copy()
            if content_copy.items():
                for mariadb_name, mariadb_content in content_copy.items():
                    logging.info(f"[MariaDBPlacer] mariadb_name: {mariadb_name}, db_count: {len(mariadb_content.get('databases', []))}")

    def place_and_create_database(self, namespace, prefix, name, ownerReferences):
        mariadb_ref = self._least_populated_mariadb(namespace)
        db_spec = {
            "mariaDbRef": {
                "name": mariadb_ref
            },
            "characterSet": "utf8mb4",
            "collate": "utf8mb4_unicode_ci"
        }
        db_name = f"{prefix['db']}{name}"
        self._mariadbs_at(namespace, mariadb_ref).setdefault("databases", []).append(
            {'name': db_name, 'namespace': namespace, 'spec': db_spec})
        body = {
            "apiVersion": "k8s.mariadb.com/v1alpha1",
            "kind": "Database",
            "metadata": {
                "name": db_name,
                "namespace": namespace,
                "ownerReferences": [ownerReferences]
            },
            "spec": db_spec
        }

        try:
            KubernetesAPI.custom.create_namespaced_custom_object(
                group="k8s.mariadb.com",
                version="v1alpha1",
                namespace=namespace,
                plural="databases",
                body=body
            )
        except ApiException as e:
            if e.status != 409:
                raise e
            database = KubernetesAPI.custom.get_namespaced_custom_object(group="k8s.mariadb.com",
                                                            version="v1alpha1",
                                                            namespace=namespace,
                                                            plural="databases",
                                                            name=db_name)
            mariadb_ref = database.get("spec", {}).get("mariaDbRef", {}).get("name", '')
            logging.info(f" ↳ [{namespace}/{name}] Database {db_name} already exists in {mariadb_ref}")

        return mariadb_ref

    def _least_populated_mariadb(self, namespace):
        db_count_by_mariadb = []
        for namespace_name, content in self._mariadbs_by_namespace.items():
            # TODO filter on mariadb-[0-5] (without mariadb-restore)
            if namespace_name == namespace:
                for mariadb_name, mariadb_content in content.items():
                    db_count_by_mariadb.append(
                        {'mariadb_name': mariadb_name, 'len': len(mariadb_content.setdefault("databases", []))})
        mariadb_min = min(db_count_by_mariadb, key=lambda x: x['len'])
        return mariadb_min['mariadb_name']


class RouteController:
    def __init__(self):
        self._routes_by_namespace = {}

        @kopf.on.event('routes')
        def on_event_routes(event, spec, name, namespace, **kwargs):
            # Convert kopf Spec object to a dictionary (especially for the `update`)
            spec_dict = dict(spec)
            if (event['type'] in [None, 'ADDED', 'MODIFIED']):
                if name in self._routes_at(namespace):
                    self._routes_at(namespace)[name]['spec'].update(spec_dict)
                else:
                    self._routes_at(namespace)[name] = {'spec': spec_dict}
            elif (event['type'] == 'DELETED'):
                if namespace in self._routes_by_namespace:
                    if name in self._routes_by_namespace[namespace]:
                        del self._routes_by_namespace[namespace][name]
            else:
                logging.error(f"[ERROR] @kopf.on.event('routes'): Unknown event.type '{event['type']}' for route '{name}'")

    def _routes_at(self, namespace):
        return self._routes_by_namespace.setdefault(namespace, {})

    def _is_a_parent_route(self, site_url, route_full_path):
        s = [part for part in site_url.split('/') if part]
        r = [part for part in route_full_path.split('/') if part]
        if len(r) > len(s):
            return False
        for i in range(len(r)):
            if s[i] != r[i]:
                return False
        return True

    def _get_closest_parent_route(self, namespace, hostname, path):
        site_url = f"{hostname}{path}"
        closest_parent_route = None
        parent_route_max_len = 0
        for route, val in self._routes_at(namespace).items():
            spec = val.get('spec')
            host = spec.get('host')
            path = spec.get('path', '')
            route_full_path = f"{host}{path}"
            if self._is_a_parent_route(site_url, route_full_path) and len(route_full_path) > parent_route_max_len:
                parent_route_max_len = len(route_full_path)
                closest_parent_route = {'name': route, 'spec': spec}
        return closest_parent_route

    def _is_cloudflared_route(self, hostname):
        # TODO: Put this as configmap
        return hostname in  [
            'www.epfl.ch',
            'dcsl.epfl.ch',
            'ukraine.epfl.ch'
        ]

    def create_route(self, namespace, site_name, route_name, hostname, path, service_name, ownerReferences):
        parent_route = self._get_closest_parent_route(namespace, hostname, path)
        if parent_route and service_name == parent_route.get('spec', {}).get('to', {}).get('name'):
            logging.info(
                f" ↳ [{namespace}/{site_name}] The closest parent route '{parent_route.get('name')}' already points to "
                f"the same service '{service_name}' for the site url '{hostname}{path}' → route spec: {parent_route.get('spec')}"
            )
            return

        logging.info(f" ↳ [{namespace}/{site_name}] Create Route {route_name}")

        route_label = 'public-cf' if self._is_cloudflared_route(hostname) else 'public'

        spec = {
            "to": {
                "kind": "Service",
                "name": service_name
            },
            "tls": {
                "termination": "edge",
                "insecureEdgeTerminationPolicy": "Redirect",
                "destinationCACertificate": ""
            },
            "host": hostname,
            "path": path,
            "port": {
                "targetPort": "80"
            },
            "alternateBackends": []
        }
        self._routes_at(namespace)[route_name] = {'spec': spec}

        body = {
            "apiVersion": "route.openshift.io/v1",
            "kind": "Route",
            "metadata": {
                "name": route_name,
                "namespace": namespace,
                "ownerReferences": [ownerReferences],
                "annotations": {
                    "haproxy.router.openshift.io/balance": "roundrobin",
                    "haproxy.router.openshift.io/disable_cookies": "true"
                },
                "labels": {
                    "app": "wp-nginx",
                    "route": route_label
                },
            },
            "spec": spec
        }

        try:
            KubernetesAPI.custom.create_namespaced_custom_object(
                group="route.openshift.io",
                version="v1",
                namespace=namespace,
                plural="routes",
                body=body
            )

        except ApiException as e:
            logging.error(f" ↳ [{namespace}/{site_name}] Error creating route '{route_name}': {e}")
            raise e


class SiteReconcilerWork:
    def __init__(self, wp):
        self.wp = wp
        self._php_work = ''
        self._plugins_to_activate = []
        self._plugins_to_deactivate = []

    def activate_plugin(self, plugin_name):
        self._plugins_to_activate.append(plugin_name)

    def deactivate_plugin(self, plugin_name):
        self._plugins_to_deactivate.append(plugin_name)

    def add_language(self, lang):
        self.flush()
        self._do_run_wp(['pll', 'lang', 'create', f'{lang["name"]}', f'{lang["slug"]}', f'{lang["locale"]}',
                         f'--rtl={lang["rtl"]}', f'--order={lang["term_group"]}', f'--flag={lang["flag"]}'])

    def delete_language(self, slug):
        self.flush()
        self._do_run_wp(['pll', 'lang', 'delete', f'{slug}'])

    def apply_sql(self, sql_filename):
        self.flush()
        self._do_run_wp(['db', 'query'], stdin=open(sql_filename))

    def set_wp_option(self, name, value):
        self._php_work = self._php_work + f"update_option({phpize(name)},{phpize(value)}); \n"

    def delete_transient(self, name):
        self.flush()
        self._do_run_wp(['transient', 'delete', name])

    def flush(self):
        if self._plugins_to_activate:
            self._do_run_wp(['plugin', 'activate'] + self._plugins_to_activate)
        self._plugins_to_activate = []

        if self._plugins_to_deactivate:
            self._do_run_wp(['plugin', 'deactivate'] + self._plugins_to_deactivate)
        self._plugins_to_deactivate = []

        if self._php_work:
            self._do_run_wp(['eval', self._php_work])
        self._php_work = ''


    def _do_run_wp(self, cmdline, **kwargs):
        cmdline = ['wp', f'--ingress={self.wp.ingress_name}'] + cmdline
        if 'DEBUG' in os.environ:
            cmdline.insert(0, 'echo')
        return subprocess.run(cmdline, check=True, **kwargs)


class PluginReconciler:
    @classmethod
    def get (cls, plugin_name, k8s_namespace, work):
        for subcls in cls.__subclasses__():
            if subcls.name == plugin_name:
                return subcls(work=work, k8s_namespace=k8s_namespace)

        return cls(work=work, plugin_name=plugin_name,
                   k8s_namespace=k8s_namespace)

    def __init__ (self, work, k8s_namespace, plugin_name=None):
        self.work = work
        self.k8s_namespace = k8s_namespace
        if plugin_name:
            self.name = plugin_name

    def activate (self):
        logging.info(f'_activate_plugin {self.name}')
        self.work.activate_plugin(self.name)

    def deactivate (self):
        logging.info(f'_deactivate_plugin {self.name}')
        self.work.deactivate_plugin(self.name)

    def configure (self, plugin_def):
        logging.info(f'_configure_plugin {self.name} {plugin_def} ')
        for option in plugin_def.get('wp_options', []):
            self._set_wp_option(option)

    def _set_wp_option (self, option):
        value = (option['value'] if 'value' in option
                 else self._get_wp_option_indirect(option['valueFrom']))

        if option.get('valueEncoding', None) == "JSON":
            value = json.loads(value)

        self.work.set_wp_option(option['name'], value)

    def _get_wp_option_indirect (self, valueFrom):
        secret = KubernetesAPI.core.read_namespaced_secret(valueFrom['secretKeyRef']['name'], self.k8s_namespace)
        return base64.b64decode(secret.data[valueFrom['secretKeyRef']['key']]).decode("utf-8")


class PolylangPluginReconciler (PluginReconciler):
    name = "polylang"

    def configure (self, plugin_def):
        super().configure(plugin_def)
        languages = plugin_def.get('polylang', {}).get('languages', [])
        for lang in languages:
            self.work.add_language(lang)

        self.work.delete_transient("pll_activation_redirect")


class RedirectionPluginReconciler (PluginReconciler):
    name = "redirection"

    def configure (self, plugin_def):
        super().configure(plugin_def)
        self.work.apply_sql("redirection.sql")


class WordpressIngressReconciler:
    def __init__ (self, me):
        self._me = me

    @property
    def name (self):
        return self._me.name

    @property
    def namespace (self):
        return self._me.namespace

    @property
    def hostname (self):
        return self._me.hostname

    @property
    def db (self):
        return self._me.database

    @property
    def user (self):
        return self._me.user

    @property
    def secret (self):
        return self._me.secret

    @property
    def uploads_dirname (self):
        return self.name   # ⚠ Do *NOT* rely on that being the case forever!

    @property
    def protection_script (self):
        return self._me.protection_script

    @property
    def _nginx_configuration_snippet (self):
        if self.protection_script:
            fastcgi_param_protection_script = f"""fastcgi_param DOWNLOADS_PROTECTION_SCRIPT    {self.protection_script};"""
        else:
            fastcgi_param_protection_script = ""

        path_slash = ensure_final_slash(self._me.path)

        return f"""
fastcgi_param WP_DEBUG           true;
fastcgi_param WP_ROOT_URI        {path_slash};
fastcgi_param WP_UPLOADS_DIRNAME {self.uploads_dirname};
fastcgi_param WP_DB_HOST         {self.db.mariadb.service.name};
fastcgi_param WP_DB_NAME         {self.db.dbname};
fastcgi_param WP_DB_USER         {self.user.username};
fastcgi_param WP_DB_PASSWORD     {self.secret.mariadb_password};
{fastcgi_param_protection_script}
"""

    def reconcile (self):
        """TODO: doesn't actually handle anything but initial creation. (Yet)"""
        annotations = {
            "nginx.ingress.kubernetes.io/configuration-snippet":
            self._nginx_configuration_snippet
        }

        if not self.protection_script:
            annotations["wordpress.epfl.ch/nginx-uploads-dirname"] = self.uploads_dirname

        body = client.V1Ingress(
            api_version="networking.k8s.io/v1",
            kind="Ingress",
            metadata=client.V1ObjectMeta(
                name=self._me.name,
                namespace=self._me.namespace,
                owner_references=[self._me.owner_reference],
                annotations=annotations
            ),
            spec=client.V1IngressSpec(
                ingress_class_name="wordpress",
                rules=[client.V1IngressRule(
                    host=self._me.hostname,
                    http=client.V1HTTPIngressRuleValue(
                        paths=[client.V1HTTPIngressPath(
                            path=self._me.path,
                            path_type="Prefix",
                            backend=client.V1IngressBackend(
                                service=client.V1IngressServiceBackend(
                                    name="wp-nginx",
                                    port=client.V1ServiceBackendPort(
                                        number=80,
                                    )
                                )
                            )
                        )]
                    )
                )]
            )
        )

        try:
            KubernetesAPI.networking.create_namespaced_ingress(
                namespace=self.namespace,
                body=body
            )
        except ApiException as e:
            if e.status != 409:
                raise e
            logging.info(f" ↳ [{self.namespace}/{self.name}] Ingress {self.name} already exists")


class WordPressSiteOperator:

  @classmethod
  def go(cls):
      placer = MariaDBPlacer()
      route_controller = RouteController()

      @kopf.on.create('wordpresssites')
      def on_create_wordpresssite(body, name, namespace, meta, **kwargs):
          wps_uid = meta.get('uid')
          WordPressSiteOperator(name, namespace, placer, route_controller, wps_uid).create_site(body)

      @kopf.on.field('wordpress.epfl.ch', 'v2', 'wordpresssites', field='spec')
      @kopf.on.field('wordpress.epfl.ch', 'v2', 'wordpresssites', field='status.wordpresssite.plugins')
      @kopf.on.field('wordpress.epfl.ch', 'v2', 'wordpresssites', field='status.wordpresssite.languages')
      @kopf.on.field('wordpress.epfl.ch', 'v2', 'wordpresssites', field='status.wordpresssite.unitid')
      def on_update_wordpresssite(spec, name, namespace, meta, status, **kwargs):
          wps_uid = meta.get('uid')
          WordPressSiteOperator(name, namespace, placer, route_controller, wps_uid).reconcile_site(spec, status)

  def __init__(self, name, namespace, placer, route_controller, wps_uid):
      self.name = name
      self.namespace = namespace
      self.placer = placer
      self.route_controller = route_controller
      self.wpn_uid = wps_uid
      self.prefix = {
          "db": "wp-db-",
          "user": "wp-db-user-",
          "grant": "wp-db-grant-",
          "password": "wp-db-password-",
          "route": "wp-route-"
      }
      self.ownerReferences = {
          "apiVersion": "wordpress.epfl.ch/v2",
          "kind": "WordpressSite",
          "name": self.name,
          "uid": self.wpn_uid
      }

  def create_site(self, body):
      logging.info(f"Create WordPressSite {self.name=} in {self.namespace=}")

      spec = body["spec"]
      hostname = spec.get('hostname')
      path = spec.get('path')
      wordpress = spec.get("wordpress")
      unit_id = spec.get("owner", {}).get("epfl", {}).get("unitId")
      title = wordpress["title"]
      tagline = wordpress["tagline"]
      restore = spec.get("restore")

      self.mariadb_name = self.placer.place_and_create_database(self.namespace, self.prefix, self.name, self.ownerReferences)
      self.database_name = f"{self.prefix['db']}{self.name}"

      self._waitMariaDBObjectReady("databases", self.database_name)

      self.create_secret()
      self.create_user()
      self.create_grant()

      mariadb_password_base64 = str(KubernetesAPI.core.read_namespaced_secret(self.secret_name, self.namespace).data['password'])
      mariadb_password = base64.b64decode(mariadb_password_base64).decode('ascii')

      self.install_wordpress_via_php(title, tagline, unit_id,
                                     mariadb_password, hostname, path)

      self.create_ingress(body)

      if restore:
          self.restore_site(restore, hostname, path)

      self.reconcile_site(spec, {})

      route_name = f"{self.prefix['route']}{self.name}"
      service_name = 'wp-nginx'
      self.route_controller.create_route(self.namespace, self.name, route_name, hostname, path, service_name, self.ownerReferences)

      logging.info(f"End of create WordPressSite {self.name=} in {self.namespace=}")

  def restore_site(self, restore, hostname, path):
      # TODO create wp-fleet image + cronjob + add it into tekton

      #V 0- create a mariadb-restore as code ansible --> we need in test also the wp-fleet-prod -->
      # TODO ticket ITOP-SDDC

      # TODO faire condition pour le onOf entre mariaDBLookup et dbName
      if restore["wpDbBackupRef"]["mariaDBLookup"]:
          # - Get the mariadb from the source_information in the CR
          mariadb_source_name = restore["wpDbBackupRef"]["mariaDBLookup"]["mariadbNameSource"]
          db_source_name = restore["wpDbBackupRef"]["mariaDBLookup"]["databaseNameSource"]

          # - From the s3, restore the db source on the mariadb-restore
          self.create_database_for_restore(db_source_name)
          self._waitMariaDBObjectReady("databases", db_source_name)

          # - Read the root secret for mariadb-restore
          secret = KubernetesAPI.core.read_namespaced_secret(restore["wpDbBackupRef"]["mariaDBLookup"]["mariadbSecretName"],
                                                             self.namespace)
          decoded_secret = base64.b64decode(secret.data["root-password"]).decode("utf-8")

          # - When the DB is created, restore data from s3
          self.restore_from_s3 (restore["s3"]["bucket"], mariadb_source_name, db_source_name, os.getenv("MARIADB-RESTORE"),
                                restore["s3"]["endpoint"], restore["s3"]["secretKeyName"])

          # 5- Use mysqldump to dump the db from the restored DB into mariadb-restore
          logging.info(f"Running dump of {db_source_name} and import of {self.database_name}")

          dump_cmd = ["mariadb-dump", "-h", os.getenv("MARIADB-RESTORE"), "-u", "root", f"-p{decoded_secret}", "--databases", db_source_name]
          sed_url = ["sed", "-e", rf"s|{restore['urlSource']}|https://{hostname}{path}|g"]
          sed_dbname = ["sed", "-e", rf"s|{db_source_name}|{self.database_name}|g"]
          restore_cmd = ["mariadb-import", "-u", "root", "-h", self.mariadb_name, f"-p{decoded_secret}", self.database_name]

          mariadb_dump = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE)
          dump_replaced_url = subprocess.Popen(sed_url, stdin=mariadb_dump.stdout, stdout=subprocess.PIPE)
          dump_replaced_dbname = subprocess.Popen(sed_dbname, stdin=dump_replaced_url.stdout, stdout=subprocess.PIPE)
          restore_db = subprocess.Popen(restore_cmd, stdin=dump_replaced_dbname.stdout, stdout=subprocess.PIPE)
          mariadb_dump.stdout.close()
          dump_replaced_url.stdout.close()
          dump_replaced_dbname.stdout.close()
          outs, errs = restore_db.communicate()

          # TODO : how to manage DEBUG mode ?

          if restore_db.returncode != 0 and 'DEBUG' not in os.environ :
              raise subprocess.CalledProcessError(restore_db.returncode, restore_cmd, outs, errs)
          else:
              logging.info(f"Dump and import done.")

          # TODO delete these objects at the end (user grant and database restore)

      # 6- in the pipeline faire un sed for the search and replace for the url and the DB name
      # 7- restore this modified dump into the new database of the new site
      # 8- media??


  def create_database_for_restore(self, name):
    body = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "Database",
        "metadata": {
            "name": name,
            "namespace": self.namespace
        },
        "spec": {
            "mariaDbRef": {
                "name": os.getenv("MARIADB-RESTORE")
            },
            "characterSet": "utf8mb4",
            "collate": "utf8mb4_unicode_ci"
        }
    }

    try:
        KubernetesAPI.custom.create_namespaced_custom_object(
            group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=self.namespace,
            plural="databases",
            body=body
        )
    except ApiException as e:
        if e.status != 409:
            raise e
        logging.info(f" ↳ [{self.namespace}/{name}] Database {name} already exists in {os.getenv('MARIADB-RESTORE')}")


  def restore_from_s3 (self, bucket_name, mariadb_name_src, db_name_src, mariadb_name_dst, endpoint, s3_secret_name):
    logging.info(f"   ↳ [{self.namespace}/{self.name}] Initiating restore on {mariadb_name_dst} for {mariadb_name_src}/{db_name_src}")

    # Initiate the restore process in MariaDB
    restore_spec = {
        "apiVersion": "k8s.mariadb.com/v1alpha1",
        "kind": "Restore",
        "metadata": {
            "name": f"m-{db_name_src[-50:]}-{round(time.time())}",
            "namespace": self.namespace,
            "ownerReferences": self.ownerReferences
        },
        "spec": {
            "mariaDbRef": {
                "name": mariadb_name_dst
            },
            "resources": {
                "requests": {
                    "cpu": "100m",
                    "memory": "256Mi"
                }
            },
            "s3": {
                "bucket": bucket_name,
                "prefix": f"MariaDB-{mariadb_name_src}",
                "endpoint": endpoint,
                "accessKeyIdSecretKeyRef": {
                    "name": s3_secret_name,
                    "key": "keyId"
                },
                "secretAccessKeySecretKeyRef": {
                    "name": s3_secret_name,
                    "key": "accessSecret"
                },
                "tls": {
                    "enabled": True
                }
            },
            "targetRecoveryTime": self.now,
            "args": [
                "--verbose",
                f"--database={db_name_src}"
            ]
        }
    }

    logging.info(f"   ↳ [{self.namespace}/{self.name}] Creating restore object in Kubernetes")
    return KubernetesAPI.custom.create_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        namespace=self.namespace,
        plural="restores",
        body=restore_spec
    )

  def install_wordpress_via_php(self, title, tagline, unit_id, secret, hostname, path):
      logging.info(f" ↳ [install_wordpress_via_php] Configuring (ensure-wordpress-and-theme.php) with {self.name=}, {path=}, {title=}, {tagline=}")

      cmdline = [Config.php, "ensure-wordpress-and-theme.php",
                 f"--name={self.name}", f"--path={path}",
                 f"--wp-dir={Config.wp_dir}",
                 f"--wp-host={hostname}",
                 f"--db-host={self.mariadb_name}",
                 f"--db-name={self.prefix['db']}{self.name}",
                 f"--db-user={self.prefix['user']}{self.name}",
                 f"--db-password={secret}",
                 f"--title={title}",
                 f"--tagline={tagline}",
                 f"--unit-id={unit_id}",
                 f"--secret-dir={Config.secret_dir}"]

      cmdline_text = ' '.join(shlex.quote(arg) for arg in cmdline)
      logging.info(f" Running: {cmdline_text}")
      if 'DEBUG' in os.environ:
          cmdline.insert(0, "echo")
      result = subprocess.run(cmdline, capture_output=True, text=True)

      logging.info(result.stdout)

      if "WordPress successfully installed" not in result.stdout and 'DEBUG' not in os.environ :
          raise subprocess.CalledProcessError(result.returncode, cmdline_text)
      else:
          logging.info(f" ↳ [install_wordpress_via_php] End of configuring")

  def reconcile_site(self, spec, status):
      logging.info(f"Reconcile WordPressSite {self.name} in {self.namespace}")

      logging.info("Plugins")
      self.reconcile_plugins(spec, status)
      self.reconcile_languages(spec, status)
      self.reconcile_unitId(spec)

      self._patch_wordpresssite_status()

      logging.info(f"Reconcile WordPressSite {self.name=} in {self.namespace=} end")

  def reconcile_plugins(self, spec, status):
      logging.info(f"Reconcile WordPressSite plugins {self.name=} in {self.namespace=}")
      work = SiteReconcilerWork(self)

      wordpress = spec.get("wordpress")
      plugins_wanted = set(wordpress.get("plugins", {}))

      status_spec = status.get("wordpresssite", {})
      plugins_got = set(status_spec.get("plugins", {}))

      plugins_to_activate = plugins_wanted - plugins_got
      logging.info(f'plugins_to_activate: {plugins_to_activate}')
      for name in plugins_to_activate:
          p = PluginReconciler.get(plugin_name=name, work=work, k8s_namespace=self.namespace)
          p.activate()
      for name in plugins_to_activate:
          p = PluginReconciler.get(plugin_name=name, work=work, k8s_namespace=self.namespace)
          p.configure(wordpress['plugins'][name])

      plugins_to_deactivate = plugins_got - plugins_wanted
      logging.info(f'plugins_to_deactivate: {plugins_to_deactivate}')
      for name in plugins_to_deactivate:
          p = PluginReconciler.get(plugin_name=name, work=work, k8s_namespace=self.namespace)
          p.deactivate()

      work.flush()
      logging.info(f"End of reconcile WordPressSite plugins {self.name=} in {self.namespace=}")

  def reconcile_languages(self, spec, status):
    logging.info(f"Reconcile WordPressSite languages {self.name=} in {self.namespace=}")
    work = SiteReconcilerWork(self)

    wordpress = spec.get("wordpress")
    plugins = wordpress.get("plugins", {})
    polylang = plugins.get("polylang", {}).get("polylang", {})
    languages_wanted = polylang.get("languages", [])
    locale_wanted = {lang['locale'] for lang in languages_wanted}

    status_spec = status.get("wordpresssite", {})
    languages_got = status_spec.get("languages", [])
    locale_got = {lang['locale'] for lang in languages_got}

    languages_to_deactivate = locale_got - locale_wanted
    logging.info(f'languages_to_deactivate: {languages_to_deactivate}')
    for locale in languages_to_deactivate:
        language = next((lang for lang in languages_got if lang["locale"] == locale), None)
        if language:
            work.delete_language(language['slug'])

    languages_to_activate = locale_wanted - locale_got
    logging.info(f'languages_to_activate: {languages_to_activate}')
    for locale in languages_to_activate:
        language = next((lang for lang in languages_wanted if lang["locale"] == locale), None)
        if language:
            work.add_language(language)

    work.flush()
    logging.info(f"End of reconcile WordPressSite languages {self.name=} in {self.namespace=}")

  def reconcile_unitId(self, spec):
      logging.info(f"Reconcile WordPressSite unit_id {self.name=} in {self.namespace=}")
      work = SiteReconcilerWork(self)
      unit = spec.get("owner", {}).get("epfl", {}).get("unitId", {})
      work.set_wp_option('plugin:epfl_accred:unit_id', unit)
      work.flush()
      logging.info(f"Reconcile WordPressSite unit_id {self.name=} in {self.namespace=}")

  def _patch_wordpresssite_status (self):
      """
      Patch the Wordpresssite CR status with:
          plugins: The active plugins on the site
      """
      try:
          KubernetesAPI.custom_jsonpatch.patch_namespaced_custom_object_status(
              group="wordpress.epfl.ch",
              version="v2",
              plural="wordpresssites",
              namespace=self.namespace,
              name=self.name,
              body=[
                  {
                      "op": "add",
                      "path": "/status/wordpresssite",
                      "value": self._status_wordpresssite_struct()
                  }
              ])
      except ApiException:
          logging.exception("when calling CustomObjectsApi->patch_namespaced_custom_object_status")
          raise

  def _status_wordpresssite_struct(self):
      if 'DEBUG' in os.environ:
          out = {}
      else:
          cmdline = ['wp', f'--ingress={self.ingress_name}', 'eval', '''echo(json_encode(apply_filters('wp_operator_status',[]), JSON_PRETTY_PRINT));''']
          result = self._do_run_wp(cmdline, capture_output=True, text=True)
          out = json.loads(result.stdout)
          if out == []:
              out = {}
      return {
          'lastCronJobRuntime': datetime.datetime.now().isoformat(),
          **out
      }

  def _do_run_wp(self, cmdline, **kwargs):
      if 'DEBUG' in os.environ:
          cmdline.insert(0, 'echo')
      return subprocess.run(cmdline, check=True, **kwargs)

  @property
  def secret_name(self):
      return self.prefix["password"] + self.name

  @property
  def ingress_name(self):
      return self.name

  def create_secret(self):
      secret = secrets.token_urlsafe(32)
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create Secret name={self.secret_name}")
      body = client.V1Secret(
          type="Opaque",
          metadata=client.V1ObjectMeta(
              name=self.secret_name,
              namespace=self.namespace,
              owner_references=[self.ownerReferences]
          ),
          string_data={"password": secret}
      )

      try:
          KubernetesAPI.core.create_namespaced_secret(namespace=self.namespace, body=body)
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] Secret {self.secret_name} already exists")

  def create_user(self):
      user_name = f"{self.prefix['user']}{self.name}"
      password_name = f"{self.prefix['password']}{self.name}"
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create User name={user_name}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "User",
          "metadata": {
              "name": user_name,
              "namespace": self.namespace,
              "ownerReferences": [self.ownerReferences]
          },
          "spec": {
              "mariaDbRef": {
                  "name": self.mariadb_name
              },
              "passwordSecretKeyRef": {
                  "name": password_name,
                  "key": "password"
              },
              "host": "%",
              "cleanupPolicy": "Delete"
          }
      }

      try:
          KubernetesAPI.custom.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=self.namespace,
              plural="users",
              body=body
          )
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] User {user_name} already exists")

      self._waitMariaDBObjectReady("users", user_name)

  def create_grant(self):
      grant_name = f"{self.prefix['grant']}{self.name}"
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create Grant: {grant_name}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "Grant",
          "metadata": {
              "name": grant_name,
              "namespace": self.namespace,
              "ownerReferences": [self.ownerReferences]
          },
          "spec": {
              "mariaDbRef": {
                  "name": self.mariadb_name
              },
              "privileges": [
                  "ALL PRIVILEGES"
              ],
              "database": f"{self.prefix['db']}{self.name}",
              "table" : "*",
              "username": f"{self.prefix['user']}{self.name}",
              "grantOption": False,
              "host": "%"
          }
      }

      try:
          KubernetesAPI.custom.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=self.namespace,
              plural="grants",
              body=body
          )
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] Grant {grant_name} already exists")

      self._waitMariaDBObjectReady("grants", grant_name)

  def _waitMariaDBObjectReady(self, customObjectType, customObjectName):
      # Wait until the customobject creation completes (either in error or successfully)

      message = ''
      iteration = 0;
      while(True):
          newUser = KubernetesAPI.custom.get_namespaced_custom_object(group="k8s.mariadb.com",
                                                                 version="v1alpha1",
                                                                 namespace=self.namespace,
                                                                 plural=customObjectType,
                                                                 name=customObjectName)
          for condition in newUser.get("status", {}).get("conditions", []):
              if condition.get("type") == "Ready":
                  message = condition.get("message")
                  if message == "Created":
                      return
                  else:
                      pass

          if iteration < 12:
              time.sleep(5)
              iteration = iteration + 1
          else:
              raise kopf.PermanentError(f"create {customObjectName} timed out or failed, last condition message: {message}")

  def create_ingress (self, body):
      logging.info(f"Creating ingress for {self.name}")
      WordpressIngressReconciler(WordpressSite(body)).reconcile()


class NamespaceFromEnv:
    @classmethod
    def guess (cls):
        if 'KUBERNETES_NAMESPACE' in os.environ:
            return os.environ['KUBERNETES_NAMESPACE']
        else:
            # Poor man's `click`
            for i in range(1, len(sys.argv)):
                if (i < len(sys.argv)) and (sys.argv[i] in ('--namespace', '-n')):
                    return sys.argv[i + 1]
                else:
                    matched = re.match('--namespace=(.*)$', sys.argv[i])
                    if matched:
                        return matched[1]

        raise ValueError('This is a namespaced-*only* operator. Please set KUBERNETES_NAMESPACE or pass --namespace.')

    guessed = None
    @classmethod
    def get (cls):
        if cls.guessed is None:
            cls.guessed = cls.guess()

        return cls.guessed

    @classmethod
    def setup (cls):
        namespace = cls.get()
        logging.info(f'WP-Operator v2.3.0 | codename: Ailuropoda')
        logging.info(f'Running in namespace {namespace}')
        os.environ['KUBERNETES_NAMESPACE'] = namespace
        try:
            dashdash_position = sys.argv.index('--')
        except ValueError:
            dashdash_position = len(sys.argv)
        sys.argv[dashdash_position:dashdash_position] = [f'--namespace={namespace}']


def ensure_final_slash (path):
    if not path.endswith("/"):
        path = f"{path}/"
    return path


if __name__ == '__main__':
    Config.load_from_command_line()
    NamespaceFromEnv.setup()
    WordPressSiteOperator.go()

    def do_run_kopf ():
        sys.exit(kopf.cli.main())
    NamespaceLeaderElection.go(namespace=NamespaceFromEnv.get(),
                               onstarted_leading=do_run_kopf)
