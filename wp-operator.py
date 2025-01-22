# Kopf documentation : https://kopf.readthedocs.io/
#
# Run with `python3 wp-operator.py run -- --db-host mariadb-min.wordpress-test.svc`
#
import argparse
import kopf
import kopf.cli
import logging
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.exceptions import ApiException
from kubernetes.leaderelection import leaderelection
from kubernetes.leaderelection.resourcelock.configmaplock import ConfigMapLock
from kubernetes.leaderelection import electionconfig
import base64
import os
import subprocess
import sys
import yaml
import re
from datetime import datetime, timezone
import threading
import time
import shlex
import secrets
import uuid

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
        parser.add_argument('--db-host', help='Hostname of the database to connect to with PHP.',
                            default="mariadb-min")
        parser.add_argument('--secret-dir', help='Secret file\'s directory.',
                            default="secretFiles")
        parser.add_argument('--restore-secrets-file', help='Path to a .ini file that contains AWS credentials to read backups from',
                            default="/keybase/team/epfl_wp_prod/aws-cli-credentials")
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
        cls.db_host = cmdline.db_host
        cls.secret_dir = cmdline.secret_dir
        cls.restore_secrets_file = cmdline.restore_secrets_file

    @classmethod
    def script_dir(cls):
        for arg in cls.saved_argv:
            if "wp-operator.py" in arg:
                script_full_path = os.path.join(os.getcwd(), arg)
                return os.path.dirname(script_full_path)
        return "."  # Take a guess

    @classmethod
    def file_in_script_dir(cls, basename):
        return os.path.join(cls.script_dir(), basename)

    @classmethod
    def splice_our_argv(cls):
        if "--" in sys.argv:
            # E.g.   python3 ./wp-operator.py run -n wordpress-toto -- --php=/usr/local/bin/php --wp-dir=yadda/yadda
            end_of_kopf = sys.argv.index("--")
            ret = sys.argv[end_of_kopf + 1:]
            sys.argv[end_of_kopf:] = []
            return ret
        else:
            return None


@kopf.on.delete('wordpresssites')
def on_delete_wordpresssite(spec, name, namespace, patch, **kwargs):
    WordPressSiteOperator(name, namespace, patch).delete_site(spec)

@kopf.on.startup()
def on_kopf_startup (settings, **_):
    settings.scanning.disabled = True
    WordPressCRDOperator.ensure_wp_crd_exists()

@kopf.on.create('wordpresssites')
def on_create_wordpresssite(spec, name, namespace, patch, **kwargs):
    WordPressSiteOperator(name, namespace, patch).create_site(spec)


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


class WordPressSiteOperator:

  def __init__(self, name, namespace, patch):
      self.name = name
      self.namespace = namespace
      self.prefix = {
        "db": "wp-db-",
        "user": "wp-db-user-",
        "grant": "wp-db-grant-",
        "password": "wp-db-password-",
        "route": "wp-route-"
      }
      self.patch = patch

  def install_wordpress_via_php(self, path, title, tagline, plugins, unit_id, languages, secret, hostname, restored_site = 0):
      logging.info(f" ↳ [install_wordpress_via_php] Configuring (ensure-wordpress-and-theme.php) with {self.name=}, {path=}, {title=}, {tagline=}")

      cmdline = [Config.php, "ensure-wordpress-and-theme.php",
                               f"--name={self.name}", f"--path={path}",
                               f"--wp-dir={Config.wp_dir}",
                               f"--wp-host={hostname}",
                               f"--db-host={Config.db_host}",
                               f"--db-name={self.prefix['db']}{self.name}",
                               f"--db-user={self.prefix['user']}{self.name}",
                               f"--db-password={secret}",
                               f"--title={title}",
                               f"--tagline={tagline}",
                               f"--plugins={plugins}",
                               f"--unit-id={unit_id}",
                               f"--languages={languages}",
                               f"--secret-dir={Config.secret_dir}",
                               f"--restored-site={restored_site}"]

      cmdline_text = ' '.join(shlex.quote(arg) for arg in cmdline)
      logging.info(f" Running: {cmdline_text}")
      result = subprocess.run(cmdline, capture_output=True, text=True)

      logging.info(result.stdout)

      if "WordPress and plugins successfully installed" not in result.stdout and "Plugins successfully configured" not in result.stdout:
          raise subprocess.CalledProcessError(result.returncode, cmdline_text)
      else:
          logging.info(f" ↳ [install_wordpress_via_php] End of configuring")

  def create_database(self):
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create Database {self.prefix['db']}{self.name}")
      db_name = f"{self.prefix['db']}{self.name}"
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "Database",
          "metadata": {
              "name": db_name,
              "namespace": self.namespace
          },
          "spec": {
              "mariaDbRef": {
                  "name": "mariadb-min"
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
          logging.info(f" ↳ [{self.namespace}/{self.name}] Database {self.prefix['db']}{self.name} already exists")

      self.waitCustomObjectCreation("databases", db_name)

  @property
  def secret_name(self):
      return self.prefix["password"] + self.name

  def create_secret(self):
      secret = secrets.token_urlsafe(32)
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create Secret name={self.secret_name}")
      body = client.V1Secret(
          type="Opaque",
          metadata=client.V1ObjectMeta(name=self.secret_name, namespace=self.namespace),
          string_data={"password": secret}
      )

      try:
          KubernetesAPI.core.create_namespaced_secret(namespace=self.namespace, body=body)
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] Secret {self.secret_name} already exists")

  def delete_secret(self):
      try:
          logging.info(f" ↳ [{self.namespace}/{self.name}] Delete Secret {self.secret_name}")

          KubernetesAPI.core.delete_namespaced_secret(namespace=self.namespace, name=self.secret_name)
      except ApiException as e:
          if e.status != 404:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] Secret {self.secret_name} does not exist")

  def create_user(self):
      user_name = f"{self.prefix['user']}{self.name}"
      password_name = f"{self.prefix['password']}{self.name}"
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create User name={user_name}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "User",
          "metadata": {
              "name": user_name,
              "namespace": self.namespace
          },
          "spec": {
              "mariaDbRef": {
                  "name": "mariadb-min"
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

      self.waitCustomObjectCreation("users", user_name)

  def create_grant(self):
      grant_name = f"{self.prefix['grant']}{self.name}"
      logging.info(f" ↳ [{self.namespace}/{self.name}] Create Grant: {grant_name}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "Grant",
          "metadata": {
              "name": grant_name,
              "namespace": self.namespace
          },
          "spec": {
              "mariaDbRef": {
                  "name": "mariadb-min"
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

      self.waitCustomObjectCreation("grants", grant_name)

  def waitCustomObjectCreation(self, customObjectType, customObjectName):
      # Wait until the customobject creation completes (either in error or successfully)

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
              raise kopf.PermanentError(f"create {customObjectName} failed, message: f{message}")

  def delete_custom_object_mariadb(self, prefix, plural):
      mariadb_name = prefix + self.name
      logging.info(f" ↳ [{self.namespace}/{self.name}] Delete MariaDB object {mariadb_name}")
      try:
          KubernetesAPI.custom.delete_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              plural=plural,
              namespace=self.namespace,
              name=mariadb_name
          )
      except ApiException as e:
          if e.status != 404:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] MariaDB object {mariadb_name} does not exist")

  def create_ingress(self, path, secret, hostname):
    body = client.V1Ingress(
        api_version="networking.k8s.io/v1",
        kind="Ingress",
        metadata=client.V1ObjectMeta(
            name=self.name,
            namespace=self.namespace,
            annotations={
            "nginx.ingress.kubernetes.io/configuration-snippet": f"""
include "/etc/nginx/template/wordpress_fastcgi.conf";

location = {path}/wp-admin {{
    return 301 https://{hostname}{path}/wp-admin/;
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
    rewrite .*/(wp-content/uploads/(.*)) /$2 break;
    root /wp-data/{self.name}/uploads/;
    add_header Cache-Control "129600, public";
}}

fastcgi_param WP_DEBUG           true;
fastcgi_param WP_ROOT_URI        {ensure_final_slash(path)};
fastcgi_param WP_SITE_NAME       {self.name};
fastcgi_param WP_ABSPATH         /wp/6/;
fastcgi_param WP_DB_HOST         mariadb-min;
fastcgi_param WP_DB_NAME         {self.prefix["db"]}{self.name};
fastcgi_param WP_DB_USER         {self.prefix["user"]}{self.name};
fastcgi_param WP_DB_PASSWORD     {secret};
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

  def delete_ingress(self):
      try:
        KubernetesAPI.networking.delete_namespaced_ingress(
            namespace=self.namespace,
            name=self.name
        )
      except ApiException as e:
          if e.status != 404:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] Ingress {self.name} does not exist")

  def create_route(self, path, hostname):
    route_name = self.prefix['route'] + self.name
    logging.info(f" ↳ [{self.namespace}/{self.name}] Create Route {route_name}")
    body = {
        "apiVersion": "route.openshift.io/v1",
        "kind": "Route",
        "metadata": {
            "name": route_name,
            "namespace": self.namespace,
            "labels": {
                "app": "wp-nginx",
                "route": "public"
            },
        },
        "spec": {
            "to": {
                "kind": "Service",
                "name": "wp-nginx"
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
    }

    try:
        KubernetesAPI.custom.create_namespaced_custom_object(
            group="route.openshift.io",
            version="v1",
            namespace=self.namespace,
            plural="routes",
            body=body
        )
    except ApiException as e:
        if e.status != 409:
            raise e
        logging.info(f" ↳ [{self.namespace}/{self.name}] Route {route_name} already exists")

  def delete_route(self):
      route_name = self.prefix['route'] + self.name
      logging.info(f" ↳ [{self.namespace}/{self.name}] Delete Route object {route_name}")
      try:
          KubernetesAPI.custom.delete_namespaced_custom_object(
              group="route.openshift.io",
              version="v1",
              plural="routes",
              namespace=self.namespace,
              name=route_name
          )
      except ApiException as e:
          if e.status != 404:
              raise e
          logging.info(f" ↳ [{self.namespace}/{self.name}] Route object {route_name} does not exist")

  def get_os3_credentials(self, profile_name):
      logging.info(f"   ↳ [{self.namespace}/{self.name}] Get Restic and S3 secrets")

      file_path = Config.restore_secrets_file

      with open(file_path, 'r') as file:
          content = file.read()

      profile_pattern = re.compile(rf'\[{profile_name}\](.*?)(?=\[|$)', re.DOTALL)
      profile_content = profile_pattern.search(content)

      profile_content = profile_content.group(1)

      return {
          "AWS_SECRET_ACCESS_KEY": re.search(r'aws_secret_access_key\s*=\s*(\S+)', profile_content).group(1),
          "AWS_ACCESS_KEY_ID": re.search(r'aws_access_key_id\s*=\s*(\S+)', profile_content).group(1),
          "RESTIC_PASSWORD": re.search(r'restic_password\s*=\s*(\S+)', profile_content).group(1),
          "BUCKET_NAME": re.search(r'bucket_name\s*=\s*(\S+)', profile_content).group(1),
          "AWS_SHARED_CREDENTIALS_FILE": file_path
      }

  def restore_wordpress_from_os3(self, path, environment, ansible_host, hostname, plugins, title, tagline, mariadb_password, unit_id, languages):
      logging.info(f" ↳ [{self.namespace}/{self.name}] Restoring WordPress from OS3")

      target = f"/tmp/backup/{self.name}"
      profile_name = "backup-wwp"
      backup_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'

      # Retrieve S3 credentials
      credentials = self.get_os3_credentials(profile_name)

      try:
          # Execute the Restic command to restore the backup
          restic_command = f"restic -r s3:https://s3.epfl.ch/{credentials['BUCKET_NAME']}/backup/wordpresses/{ansible_host}/sql restore latest --target {target}"
          logging.info(f"   Running: {restic_command}")
          restic_restore = subprocess.run(restic_command, env=credentials, shell=True, check=True, text=True)
          logging.info(f"   ↳ [{self.namespace}/{self.name}] SQL backup restored from S3")

          # Open file to write the modified SQL
          backup_file_path = f"/tmp/backup/{self.name}/backup.{backup_time}.sql"

          with open(backup_file_path, "w") as backup_file:
              logging.info(f"   ↳ [{self.namespace}/{self.name}] Replacing www.epfl.ch with {hostname} in SQL backup")
              sed_command = ["sed", rf"s/www\.epfl\.ch/{hostname}/g", f"{target}/db-backup.sql"]

              subprocess.run(sed_command, stdout=backup_file, check=True)

          subprocess.run([f"aws --endpoint-url=https://s3.epfl.ch --profile={profile_name} s3 cp {backup_file_path} s3://{credentials['BUCKET_NAME']}/backup/k8s/{self.name}/"], env=credentials, shell=True, check=True)
          logging.info(f"   ↳ [{self.namespace}/{self.name}] SQL backup copied to S3")

          # Initiate the restore process in MariaDB
          restore_spec = {
              "apiVersion": "k8s.mariadb.com/v1alpha1",
              "kind": "Restore",
              "metadata": {
                  "name": f"restore-{self.name}-{round(time.time())}",
                  "namespace": self.namespace
              },
              "spec": {
                  "mariaDbRef": {
                      "name": "mariadb-min"
                  },
                  "s3": {
                      "bucket": credentials["BUCKET_NAME"],
                      "prefix": f"backup/k8s/{self.name}",
                      "endpoint": "s3.epfl.ch",
                      "accessKeyIdSecretKeyRef": {
                          "name": "s3-backup-credentials",
                          "key": "keyId"
                      },
                      "secretAccessKeySecretKeyRef": {
                          "name": "s3-backup-credentials",
                          "key": "accessSecret"
                      },
                      "tls": {
                          "enabled": True
                      }
                  },
                  "targetRecoveryTime": backup_time,
                  "args": [
                      "--verbose",
                      f"--database={self.prefix['db']}{self.name}"
                  ]
              }
          }

          logging.info(f"   ↳ [{self.namespace}/{self.name}] Creating restore object in Kubernetes")
          restore = KubernetesAPI.custom.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=self.namespace,
              plural="restores",
              body=restore_spec
          )
          logging.info(f"   ↳ [{self.namespace}/{self.name}] Restore initiated on MariaDB")

          logging.info(f"   ↳ [{self.namespace}/{self.name}] Restoring media from OS3")
          self.restore_uploads_directory(
              f"{environment}/www.epfl.ch/htdocs{path}/wp-content/uploads",
              f"{self.name}/uploads"
          )

      except subprocess.CalledProcessError as e:
          logging.error(f"Subprocess error in backup restoration: {e}")
          raise e
      except FileNotFoundError as e:
          logging.error(f"File error in backup restoration: {e}")
          raise e
      except Exception as e:
          logging.error(f"Unexpected error: {e}")
          raise e

      restore_name = restore["metadata"]["name"]
      # Wait until the restore completes (either in error or successfully)
      while(True):
          restored = KubernetesAPI.custom.get_namespaced_custom_object(group="k8s.mariadb.com",
            version="v1alpha1",
            namespace=self.namespace,
            plural="restores",
            name=restore_name)
          for condition in restored.get("status", {}).get("conditions", []):
              if condition.get("type") == "Complete":
                  message = condition.get("message")
                  if message == "Success":
                      self.install_wordpress_via_php(path, title, tagline, ','.join(plugins), unit_id, languages, mariadb_password, hostname, 1)
                      return
                  elif message == "Running":
                      pass  # Fall through to the time.sleep() below
                  else:
                      raise kopf.PermanentError(f"restore {restore_name} failed, message: f{message}")
          time.sleep(10)

  def restore_uploads_directory (self, src, dst):
      if os.path.exists("/wp-data-ro-openshift3") and os.path.exists("/wp-data"):
          # For production: the operator pod has both these volumes mounted.
          mounted_dst = f"/wp-data/{dst}/"
          try:
              os.makedirs(mounted_dst)
          except FileExistsError:
              pass
          subprocess.run(["rsync", "-rlp", f"/wp-data-ro-openshift3/{src}/", mounted_dst], check=True)
      else:
          # For developmnent only - Assume we have ssh access to itswbhst0020 which is rigged for this purpose:
          pvc_name = "wordpress-test-wp-uploads-pvc-f401a87f-d2e9-4b20-85cc-61aa7cfc9d30"
          remote_dst = "/mnt/data/nfs-storageclass/{pvc_name}/wp-uploads/{dst}"
          subprocess.run([f"ssh -t root@itswbhst0020.xaas.epfl.ch 'set -e -x; rsync -av /mnt/data-prod-ro/wordpress/{src} {remote_dst}'"],
                         shell=True, text=True)
          logging.info(f"   ↳ [{self.namespace}/{self.name}] Restored media from OS3")

  def create_site(self, spec):
      logging.info(f"Create WordPressSite {self.name=} in {self.namespace=}")
      path = spec.get('path')
      hostname = spec.get('hostname')
      site_url = hostname + path
      wordpress = spec.get("wordpress")
      unit_id = spec.get("owner", {}).get("epfl", {}).get("unitId")
      import_object = spec.get("epfl", {}).get("import")
      title = wordpress["title"]
      tagline = wordpress["tagline"]
      plugins = wordpress.get("plugins", [])
      languages = wordpress["languages"]

      databases = KubernetesAPI.custom.list_namespaced_custom_object(
        group="k8s.mariadb.com",
        version="v1alpha1",
        namespace=self.namespace,
        plural="databases"
      )
      
      logging.info(databases)

      self.create_database()
      self.create_secret()
      self.create_user()
      self.create_grant()

      mariadb_password_base64 = str(KubernetesAPI.core.read_namespaced_secret(self.secret_name, self.namespace).data['password'])
      mariadb_password = base64.b64decode(mariadb_password_base64).decode('ascii')

      self.create_ingress(path, mariadb_password, hostname)
      
      # TODO: to be adapted during OS4 migration and removed at the end.
      if (path.split("/")[1] == "labs"):
          self.create_route(path, hostname)

      if (not import_object):
          self.install_wordpress_via_php(path, title, tagline, ','.join(plugins), unit_id, ','.join(languages), mariadb_password, hostname)
      else:
          import_os3_backup_source = import_object.get("openshift3BackupSource")
          environment = import_os3_backup_source["environment"]
          ansible_host = import_os3_backup_source["ansibleHost"]
          self.restore_wordpress_from_os3(path, environment, ansible_host, hostname, plugins, title, tagline, mariadb_password, unit_id, ','.join(languages))

      self.patch.status['wordpresssite'] = {
          'state': 'created',
          'url': site_url,
          'lastUpdate': datetime.utcnow().isoformat()
      }
      logging.info(f"End of create WordPressSite {self.name=} in {self.namespace=}")

  def delete_site(self, spec):
      logging.info(f"Delete WordPressSite {self.name=} in {self.namespace=}")

      # Deleting database
      self.delete_custom_object_mariadb(self.prefix['db'], "databases")
      self.delete_secret()
      # Deleting user
      self.delete_custom_object_mariadb(self.prefix['user'], "users")
      # Deleting grant
      self.delete_custom_object_mariadb(self.prefix['grant'], "grants")
      self.delete_ingress()
      self.delete_route()

class WordPressCRDOperator:
  # Ensuring that the "WordpressSites" CRD exists. If not, create it from the "WordPressSite-crd.yaml" file.
  @classmethod
  def ensure_wp_crd_exists(cls):
      dyn_client = KubernetesAPI.dynamic
      api_extensions_instance = KubernetesAPI.extensions
      crd_name = "wordpresssites.wordpress.epfl.ch"

      try:
          crd_list = api_extensions_instance.list_custom_resource_definition()
          exists = any(crd.metadata.name == crd_name for crd in crd_list.items)

          if exists:
              logging.info(f"↳ CRD '{crd_name}' already exists, doing nothing...")
              return True
          else:
              logging.info(f"↳ CRD '{crd_name}' does not exists, creating it...")
              with open("WordPressSite-crd.yaml") as file:
                  crd_file = yaml.safe_load(file)
              crd_resource = dyn_client.resources.get(api_version='apiextensions.k8s.io/v1', kind='CustomResourceDefinition')

              try:
                  crd_resource.create(body=crd_file)
                  logging.info(f"↳ CRD '{crd_name}' created")
                  return True
              except client.exceptions.ApiException as e:
                  logging.error("Error trying to create CRD :", e)
          logging.info("Operator started and initialized")
      except ApiException as e:
          logging.error(f"Error verifying CRD file: {e}")
      return False


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
    NamespaceLeaderElection.go()
