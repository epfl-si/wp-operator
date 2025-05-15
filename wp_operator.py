# Kopf documentation : https://kopf.readthedocs.io/
#
# The operator consume the following environment variables:
# S3_BACKUP_BUCKET: OpenShift 4' S3 bucket name used to paste the backup file for initial restores
# S3_BACKUP_KEYID: S3 keyid
# S3_BACKUP_ACCESSSECRET: S3 accessSecret
# S3_BACKUP_SECRETNAME: OpenShift 4 secret name containing keyId and accessSecret.
# The operator need 'S3_BACKUP_SECRETNAME' so he can pass the secret to the MariaDB operator for initial restores.
# Run with `python3 wp_operator.py run --`
#
import argparse
import base64
import logging
import os
import re
import secrets
import sys
import threading
import time
import uuid
import yaml

import kopf
import kopf.cli
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.leaderelection import electionconfig
from kubernetes.leaderelection import leaderelection
from kubernetes.leaderelection.resourcelock.configmaplock import ConfigMapLock
from urllib3 import disable_warnings
# Remove warning: InsecureRequestWarning (Unverified HTTPS request is being made to host 'api.okd-test.fsd.team'.
# Adding certificate verification is strongly advised. See: https://urllib3.readthedocs.io/en/latest/advanced-usage.html#tls-warnings)
from urllib3.exceptions import InsecureRequestWarning

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
                            default="../volumes/wp/6/")   # TODO: this only makes sense in dev.
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

class classproperty:
    def __init__(self, func):
        self.fget = func
    def __get__(self, instance, owner):
        return self.fget(owner)


class KubernetesAPI:
  __singleton = None

  @classmethod
  def __get(cls):
      if cls.__singleton is None:
          cls.__singleton = cls()

      return cls.__singleton

  def __init__(self):
      config.load_config()

      self._custom = client.CustomObjectsApi()
      self._core = client.CoreV1Api()
      self._extensions = client.ApiextensionsV1Api()
      self._dynamic = DynamicClient(client.ApiClient())
      self._networking = client.NetworkingV1Api()

  @classproperty
  def custom(cls):
    return cls.__get()._custom

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
        def on_event_mariadb(event, spec, name, namespace, patch, **kwargs):
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
        if parent_route and service_name == parent_route.get('spec').get('to').get('name'):
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


class WordPressSiteOperator:
  _mandatory_plugins = {
    "accred",
    "enlighter",
    "epfl-404",
    "epfl-cache-control",
    "epfl-coming-soon",
    "EPFL-Content-Filter",
    "epfl-remote-content-shortcode",
    "EPFL-settings",
    "ewww-image-optimizer",
    "find-my-blocks",
    "flowpaper-lite-pdf-flipbook",
    "polylang",
    "redirection",
    "tequila",
    "tinymce-advanced",
    "very-simple-meta-description",
    "wp-gutenberg-epfl",
    "wp-media-folder",
    "wp-plugin-pushgateway"
  }

  _black_listed_plugins = {
      "Admin",
      "CustomCSS",
      "Emploi",
      "Inside",
      "Restauration",
      "Unmanaged",
      "Library",
      "CDHSHS",
      "WPForms",
      "Payonline",
      "Surveys",
      "DiplomaVerification",
      "PartnerUniversities",
      "epfl-menus"
  }


  @classmethod
  def go(cls):
      placer = MariaDBPlacer()
      route_controller = RouteController()

      @kopf.on.create('wordpresssites')
      def on_create_wordpresssite(spec, name, namespace, meta, **kwargs):
          wps_uid = meta.get('uid')
          WordPressSiteOperator(name, namespace, placer, route_controller, wps_uid).create_site(spec)

      @kopf.on.update('wordpresssites')
      def on_update_wordpresssite(spec, name, namespace, meta, status, **kwargs):
          wps_uid = meta.get('uid')
          # print(f'FIELD CHANGED IN SPEC: {name} \n {namespace} \n {meta} \n {wps_uid}')
          WordPressSiteOperator(name, namespace, placer, route_controller, wps_uid).reconcile_site(spec, status)

      # TODO FIXME: this handler should not be present: the kopf.on.update should be able to trigger also for subresources but it seems not to be the case
      # TODO and if status is modified, both @kopf.on.update and @kopf.on.field are triggered
      @kopf.on.field('wordpress.epfl.ch', 'v2', 'wordpresssites', field='status')
      def on_update_status_plugins(spec, name, namespace, meta, status, **kwargs):
          wps_uid = meta.get('uid')
          # print(f'FIELD CHANGED IN STATUS: {spec} \n {name} \n {namespace} \n {meta} \n {wps_uid}')
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

  def create_site(self, spec):
      logging.info(f"Create WordPressSite {self.name=} in {self.namespace=}")

      hostname = spec.get('hostname')
      path = spec.get('path')
      wordpress = spec.get("wordpress")
      unit_id = spec.get("owner", {}).get("epfl", {}).get("unitId")
      import_object = spec.get("epfl", {}).get("import")
      title = wordpress["title"]
      tagline = wordpress["tagline"]
      protection_script = wordpress.get("downloadsProtectionScript")

      plugins = wordpress.get("plugins", {})

      languages = wordpress["languages"]

      self.mariadb_name = self.placer.place_and_create_database(self.namespace, self.prefix, self.name, self.ownerReferences)
      self.database_name = f"{self.prefix['db']}{self.name}"

      self._waitMariaDBObjectReady("databases", self.database_name)

      self.create_secret()
      self.create_user()
      self.create_grant()

      mariadb_password_base64 = str(KubernetesAPI.core.read_namespaced_secret(self.secret_name, self.namespace).data['password'])
      mariadb_password = base64.b64decode(mariadb_password_base64).decode('ascii')



      self.create_ingress(path, mariadb_password, hostname, protection_script)

      route_name = f"{self.prefix['route']}{self.name}"
      service_name = 'wp-nginx'
      self.route_controller.create_route(self.namespace, self.name, route_name, hostname, path, service_name, self.ownerReferences)

      logging.info(f"End of create WordPressSite {self.name=} in {self.namespace=}")

  def reconcile_site(self, spec, status):
      logging.info(f"Reconcile WordPressSite {self.name=} in {self.namespace=}")

        # TODO the following
        # echo "DB schema\n";
        # ensure_db_schema();
        # echo "Options and common WordPress settings\n";
        # ensure_other_basic_wordpress_things($options);
        # echo "Admin user\n";
        # ensure_admin_user("admin", "admin@exemple.com", generate_random_password());
        # echo "Site title\n";
        # ensure_site_title($options);
        # echo "Tagline\n";
        # ensure_tagline($options);
        # echo "Theme\n";
        # ensure_theme($options);
        # echo "Delete default pages and posts\n";
        # delete_default_pages_and_posts();

      print("Plugins\n")
      self.reconcile_plugins(spec, status)

      logging.info(f"Reconcile WordPressSite {self.name=} in {self.namespace=} end")

  def reconcile_plugins(self, spec, status):
      logging.info(f"Reconcile WordPressSite plugins {self.name=} in {self.namespace=}")

      wordpress = spec.get("wordpress")
      plugins_wanted = set(wordpress.get("plugins", {}))

      plugins_wanted = {*plugins_wanted, *self._mandatory_plugins}

      plugins_wanted.difference_update(self._black_listed_plugins)

      status_spec = status.get("wordpresssite", {})
      plugins_got = set(status_spec.get("plugins", {}))

      plugins_to_activate = plugins_wanted - plugins_got
      plugins_to_deactivate = plugins_got - plugins_wanted

      print(f'plugins_to_deactivate: {plugins_to_deactivate}\n plugins_to_activate: {plugins_to_activate} \n plugins_wanted: {plugins_wanted} \n plugins_got: {plugins_got}')

      logging.info(f"End of reconcile WordPressSite plugins {self.name=} in {self.namespace=}")


      cmdline_text = ' '.join(shlex.quote(arg) for arg in cmdline)
      logging.info(f" Running: {cmdline_text}")
      result = subprocess.run(cmdline, capture_output=True, text=True)

      logging.info(result.stdout)

      if "WordPress and plugins successfully installed" not in result.stdout and "Plugins successfully configured" not in result.stdout:
          raise subprocess.CalledProcessError(result.returncode, cmdline_text)
      else:
          logging.info(f" ↳ [install_wordpress_via_php] End of configuring")

  @property
  def secret_name(self):
      return self.prefix["password"] + self.name

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

  def create_ingress(self, path, secret, hostname, protection_script):

    if protection_script:
        location_script = f"""fastcgi_pass unix:/run/php-fpm/php-fpm.sock;"""
        fastcgi_param_protection_script = f"""fastcgi_param DOWNLOADS_PROTECTION_SCRIPT    {protection_script};"""
    else:
        location_script = f"""rewrite .*/(wp-content/uploads/(.*)) /$2 break;
    root /wp-data/{self.name}/uploads/;
    add_header Cache-Control "129600, public";"""
        fastcgi_param_protection_script = f""" """

    path_slash = ensure_final_slash(path)
    body = client.V1Ingress(
        api_version="networking.k8s.io/v1",
        kind="Ingress",
        metadata=client.V1ObjectMeta(
            name=self.name,
            namespace=self.namespace,
            owner_references=[self.ownerReferences],
            annotations={
            "nginx.ingress.kubernetes.io/configuration-snippet": f"""
include "/etc/nginx/template/wordpress_fastcgi.conf";

location = {path_slash}wp-admin {{
    return 301 https://{hostname}{path_slash}wp-admin/;
}}

location ~ (wp-includes|wp-admin|wp-content/(plugins|mu-plugins|themes))/ {{
    rewrite .*/((wp-includes|wp-admin|wp-content/(plugins|mu-plugins|themes))/.*) /$1 break;
    root /wp/6/;
    location ~* \\.(ico|pdf|apng|avif|webp|jpg|jpeg|png|gif|svg)$ {{
        add_header Cache-Control "129600, public";
        # rewrite is not inherited https://stackoverflow.com/a/32126596
        rewrite .*/((wp-includes|wp-admin|wp-content/(plugins|mu-plugins|themes))/.*) /$1 break;
    }}
}}

location ~ (wp-content/uploads)/ {{
    {location_script}
}}

fastcgi_param WP_DEBUG           true;
fastcgi_param WP_ROOT_URI        {path_slash};
fastcgi_param WP_SITE_NAME       {self.name};
fastcgi_param WP_ABSPATH         /wp/6/;
fastcgi_param WP_DB_HOST         {self.mariadb_name};
fastcgi_param WP_DB_NAME         {self.prefix["db"]}{self.name};
fastcgi_param WP_DB_USER         {self.prefix["user"]}{self.name};
fastcgi_param WP_DB_PASSWORD     {secret};
{fastcgi_param_protection_script}
"""
            }
        ),
        spec=client.V1IngressSpec(
            ingress_class_name="wordpress",
            rules=[client.V1IngressRule(
                host=hostname,
                http=client.V1HTTPIngressRuleValue(
                    paths=[client.V1HTTPIngressPath(
                        path=path,
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


class MigrationOperator:
  def __init__ (self, namespace, name, mariadb_name, database_name, spec, import_object, ownerReferences):
      self.namespace = namespace
      self.name = name
      self.mariadb_name = mariadb_name
      self.database_name = database_name
      self.spec = spec
      self.ownerReferences = ownerReferences

      import_os3_backup_source = import_object.get("openshift3BackupSource")
      self.environment = import_os3_backup_source["environment"]
      self.ansible_host = import_os3_backup_source["ansibleHost"]

  def run (self):
      restore = self.start_mariadb_restore (*self.migrate_sql_from_os3())
      self.restore_uploads_directory()
      self.wait_for_restore(restore)

  @property
  def hostname (self):
      return self.spec.get('hostname')

  @property
  def path (self):
      return self.spec.get('path')

  @property
  def epfl_restic_env (self):
      return {
          "AWS_SECRET_ACCESS_KEY": os.getenv("EPFL_MIGRATION_ACCESSSECRET"),
          "AWS_ACCESS_KEY_ID": os.getenv("EPFL_MIGRATION_KEYID"),
          "RESTIC_PASSWORD": os.getenv("RESTIC_PASSWORD")
      }

  @property
  def destination_credentials_env (self):
      return {
          "AWS_SECRET_ACCESS_KEY": os.getenv("S3_BACKUP_ACCESSSECRET"),
          "AWS_ACCESS_KEY_ID": os.getenv("S3_BACKUP_KEYID")
      }

  def run_epfl_os3_restic(self):
      """Execute the Restic command to restore the backup"""
      restic_command = ["restic", "-r",
                        f"s3:https://s3.epfl.ch/{os.getenv('EPFL_MIGRATION_BUCKET')}/backup/wordpresses/{self.ansible_host}/sql",
                        "dump", "latest", "db-backup.sql"]
      logging.info(f"   Running: {' '.join(restic_command)}")
      return subprocess.Popen(restic_command, env=self.epfl_restic_env,
                                        stdout=subprocess.PIPE)

  def read_siteurl_from_sql_dump(self, restic_process_for_siteurl_stdout):
      try:
          for line in restic_process_for_siteurl_stdout:
              matched = re.match(r"""INSERT INTO `wp_options` VALUES \(.*[0-9]+,'siteurl','(.*?)'""", line.decode('iso-8859-15'))
              if matched:
                  return matched[1]
          raise ValueError("Could not find WordPress siteurl in Restic dump!")
      finally:
          restic_process_for_siteurl_stdout.close()

  def migrate_sql_from_os3 (self):
      logging.info(f" ↳ [{self.namespace}/{self.name}] Migrating database backup from OS3")

      try:
          restic_process_for_siteurl = self.run_epfl_os3_restic()
          siteurl_in_restic = self.read_siteurl_from_sql_dump(restic_process_for_siteurl.stdout)
          restic_process_for_siteurl.wait()

          # we can't rewind a pipe so we run restic again
          restic_process = self.run_epfl_os3_restic()
          migrated_url = f"https://{self.hostname}{self.path}"
          sed_command = ["sed", "-e", rf"s|{re.escape(siteurl_in_restic)}|{re.escape(migrated_url)}|g",
                         "-e",  rf"s|www.epfl.ch/campus/associations/list/|www.epfl.ch/campus/associations/|g",
                         ]
          logging.info(f"   Running: {' '.join(sed_command)}")
          sed_process = subprocess.Popen(sed_command,
                                         stdin=restic_process.stdout, stdout=subprocess.PIPE)
          # Don't hold on to the pipe end in the parent process (i.e. this process):
          restic_process.stdout.close()

          destination_bucket_name = os.getenv("S3_BACKUP_BUCKET")
          path_in_destination_bucket = f"backup/k8s/{self.name}"

          backup_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'
          s3_uri = f"s3://{destination_bucket_name}/{path_in_destination_bucket}/backup.{backup_time}.sql"

          aws_command = ["aws", "--endpoint-url=https://s3.epfl.ch",
                          "s3", "cp", "-", s3_uri]
          logging.info(f"   Running: {' '.join(aws_command)}")
          aws_process = subprocess.Popen(aws_command,
                                         env=self.destination_credentials_env,
                                         stdin=sed_process.stdout)
          sed_process.stdout.close()

          # We are more interested in the actual errors from
          # “down-pipe” than the `died with <Signals.SIGPIPE: 13>`
          # from “up-pipe”; therefore, check error codes in reverse
          # order.
          for (p, name, cmd) in ((aws_process, "aws", aws_command),
                                 (sed_process, "sed", sed_command),
                                 (restic_process, "restic", "restic")):
              return_code = p.wait()
              logging.info(f"   {' '.join(cmd)} exited with status {return_code}")
              if return_code != 0:
                  raise subprocess.CalledProcessError(
                      return_code,
                      " ".join(cmd))

          return (destination_bucket_name, path_in_destination_bucket)

      except subprocess.CalledProcessError as e:
          logging.error(f"Subprocess error in backup restoration: {e}")
          raise e
      except FileNotFoundError as e:
          logging.error(f"File error in backup restoration: {e}")
          raise e
      except Exception as e:
          logging.error(f"Unexpected error: {e}")
          raise e

  def start_mariadb_restore (self, destination_bucket_name, path_in_destination_bucket):
      logging.info(f"   ↳ [{self.namespace}/{self.name}] Initiating restore on MariaDB")

      # Initiate the restore process in MariaDB
      restore_spec = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "Restore",
          "metadata": {
              "name": f"m-{self.name[-50:]}-{round(time.time())}",
              "namespace": self.namespace,
              "ownerReferences": [self.ownerReferences]
          },
          "spec": {
              "mariaDbRef": {
                  "name": self.mariadb_name
              },
              "resources": {
                  "requests": {
                      "cpu": "100m",
                      "memory": "256Mi"
                  }
              },
              "s3": {
                  "bucket": destination_bucket_name,
                  "prefix": path_in_destination_bucket,
                  "endpoint": "s3.epfl.ch",
                  "accessKeyIdSecretKeyRef": {
                      "name": os.getenv("S3_BACKUP_SECRETNAME"),
                      "key": "keyId"
                  },
                  "secretAccessKeySecretKeyRef": {
                      "name": os.getenv("S3_BACKUP_SECRETNAME"),
                      "key": "accessSecret"
                  },
                  "tls": {
                      "enabled": True
                  }
              },
              "targetRecoveryTime": self.now,
              "args": [
                  "--verbose",
                  f"--database={self.database_name}"
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

  def wait_for_restore (self, restore):
      restore_name = restore["metadata"]["name"]
      # Wait until the restore completes (either in error or successfully)
      while(True):
          logging.info(f"   ↳ [{self.namespace}/{self.name}] Waiting for MariaDB restore to complete")

          restored = KubernetesAPI.custom.get_namespaced_custom_object(group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=self.namespace,
            plural="restores",
            name=restore_name)
          for condition in restored.get("status", {}).get("conditions", []):
              if condition.get("type") == "Complete":
                  message = condition.get("message")
                  if message == "Success":
                      return True
                  elif message == "Running":
                      pass  # Fall through to next `for` iteration, and ultimately the time.sleep() below
                  else:
                      raise kopf.PermanentError(f"restore {restore_name} failed, message: {message}")
          time.sleep(10)

  def restore_uploads_directory (self):
      src = f"{self.environment}/{self.hostname}/htdocs{self.path if self.path != '/' else ''}/wp-content/uploads"

      src = re.sub('campus/associations', 'campus/associations/list', src)

      dst = f"{self.name}/uploads"

      if os.path.exists("/wp-data-ro-openshift3") and os.path.exists("/wp-data"):
          # For production: the operator pod has both these volumes mounted.
          mounted_dst = f"/wp-data/{dst}/"
          try:
              os.makedirs(mounted_dst)
          except FileExistsError:
              pass
          subprocess.run(["rsync", "-rlpv", f"/wp-data-ro-openshift3/{src}/", mounted_dst], check=True)
      else:
          # For developmnent only - Assume we have ssh access to itswbhst0020 which is rigged for this purpose:
          # remote_dst = "/mnt/data_new_nas_4_prod/wordpress-data/svc0041p-wordpress-wordpress-data-pvc-b8385080-dd08-47a7-9363-c11bf55be7a7/{dst}"
          remote_dst = "/mnt/data/wordpress-data/svc0041t-wordpress-wordpress-data-pvc-239b8f80-f867-4268-9a36-ec03c91ac981/{dst}"
          subprocess.run(["ssh", "-t", "root@itswbhst0020.xaas.epfl.ch", f'set -e -x; rsync -av /mnt/data-prod-ro/wordpress/{src} {remote_dst}'],
                         text=True)
          logging.info(f"   ↳ [{self.namespace}/{self.name}] Restored media from OS3")

  @cached_property
  def now (self):
      return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'


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
        logging.info(f'WP-Operator v1.4.0 | codename: Negaprion')
        logging.info(f'Running in namespace {namespace}')
        os.environ['KUBERNETES_NAMESPACE'] = namespace
        try:
            dashdash_position = sys.argv.index('--')
        except ValueError:
            dashdash_position = len(sys.argv)
        sys.argv[dashdash_position:dashdash_position] = [f'--namespace={namespace}']


class NamespaceLeaderElection:
    def __init__(self):
        self.lock_namespace = NamespaceFromEnv.get()
        self.lock_name = f"wp-operator-lock"
        self.candidate_id = uuid.uuid4()
        self.config = electionconfig.Config(
            ConfigMapLock(
                self.lock_name,
                self.lock_namespace,
                self.candidate_id
            ),
            lease_duration = 17,
            renew_deadline = 15,
            retry_period = 5,
            onstarted_leading = self.start_kopf_in_thread,
            onstopped_leading = self.exit_immediately
        )

    def start_kopf_in_thread(self):
        logging.info(f"Instance {self.candidate_id} is the leader for namespace {self.lock_namespace}.")
        def do_run_kopf ():
            sys.exit(kopf.cli.main())

        threading.Thread(target=do_run_kopf).run()

    def exit_immediately(self):
        logging.info(f"Instance {self.candidate_id} stopped being the leader for namespace {self.lock_namespace}.")
        sys.exit(0)

    @classmethod
    def go (cls):
        config.load_config()
        leader_election = cls()

        class QuietLeaderElection(leaderelection.LeaderElection):
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


def ensure_final_slash (path):
    if not path.endswith("/"):
        path = f"{path}/"
    return path


if __name__ == '__main__':
    Config.load_from_command_line()
    NamespaceFromEnv.setup()
    WordPressSiteOperator.go()
    NamespaceLeaderElection.go()
