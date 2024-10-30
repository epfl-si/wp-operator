# Kopf documentation : https://kopf.readthedocs.io/
#
# Run with `python3 wpn-kopf.py run -- --db-host mariadb-min.wordpress-test.svc --wp-php-ensure manage-plugins.php --wp-dir=/home/you/dev/wp-dev/volumes/wp/6/`
#
import argparse
import kopf
import kopf.cli
import logging
from kubernetes import client, config
from kubernetes.dynamic import DynamicClient
from kubernetes.client.exceptions import ApiException
import base64
import os
import subprocess
import sys
import yaml
import re
from datetime import datetime, timezone
import time

class Config:
    secret_name = "nginx-conf-site-tree"
    saved_argv = [arg for arg in sys.argv]

    @classmethod
    def parser(cls):
        parser = argparse.ArgumentParser(
            prog='wpn-kopf',
            description='The WordPress Next Operator',
            epilog='Happy operating!')

        parser.add_argument('--wp-dir', help='The path to the WordPress sources to load and call.',
                            default="../volumes/wp/6/")   # TODO: this only makes sense in dev.
        parser.add_argument('--wp-host', help='The hostname of the WordPresses to create.',
                            default="wpn.fsd.team")       # TODO: read that from the CR instead.
        parser.add_argument('--php', help='The path to the PHP command-line (CLI) executable.',
                            default="php")
        parser.add_argument('--wp-php-ensure', help='The path to the PHP script that ensures the postconditions.',
                            default=cls.file_in_script_dir("ensure-wordpress-and-theme.php"))
        parser.add_argument('--db-host', help='Hostname of the database to connect to with PHP.',
                            default="mariadb-min")
        return parser

    @classmethod
    def load_from_command_line(cls):
        argv = cls.splice_our_argv()
        if argv is None:
            # Passing no flags to .parser() is legit, since all of them have default values.
            argv = []

        cmdline = cls.parser().parse_args(argv)
        cls.php = cmdline.php
        cls.wp_php_ensure = cmdline.wp_php_ensure
        cls.wp_dir = os.path.join(cmdline.wp_dir, '')
        cls.wp_host = cmdline.wp_host
        cls.db_host = cmdline.db_host

    @classmethod
    def script_dir(cls):
        for arg in cls.saved_argv:
            if "wpn-kopf.py" in arg:
                script_full_path = os.path.join(os.getcwd(), arg)
                return os.path.dirname(script_full_path)
        return "."  # Take a guess

    @classmethod
    def file_in_script_dir(cls, basename):
        return os.path.join(cls.script_dir(), basename)

    @classmethod
    def splice_our_argv(cls):
        if "--" in sys.argv:
            # E.g.   python3 ./wpn-kopf.py run -n wordpress-toto -- --php=/usr/local/bin/php --wp-dir=yadda/yadda
            end_of_kopf = sys.argv.index("--")
            ret = sys.argv[end_of_kopf + 1:]
            sys.argv[end_of_kopf:] = []
            return ret
        else:
            return None


@kopf.on.delete('wordpresssites')
def on_delete_wordpresssite(spec, name, namespace, logger, **kwargs):
    JeSaisPasJeVerraiPlusTard().delete_fn(spec, name, namespace, logger)

@kopf.on.startup()
def on_kopf_startup (**kwargs):
    JeSaisPasJeVerraiPlusTard.startup_fn()

@kopf.on.create('wordpresssites')
def on_create_wordpresssite(spec, name, namespace, logger, **kwargs):
    JeSaisPasJeVerraiPlusTard().create_fn(spec, name, namespace, logger)


class JeSaisPasJeVerraiPlusTard:

  # Ensuring that the "WordpressSites" CRD exists. If not, create it from the "WordPressSite-crd.yaml" file.
  @classmethod
  def ensure_wp_crd_exists(cls):
      config.load_kube_config()
      dyn_client = DynamicClient(client.ApiClient())
      api_instance = client.ApiextensionsV1Api()
      crd_name = "wordpresssites.wordpress.epfl.ch"

      try:
          crd_list = api_instance.list_custom_resource_definition()
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
      except ApiException as e:
          logging.error(f"Error verifying CRD file: {e}")
      return False

  # Function that runs when the operator starts
  @classmethod
  def startup_fn(cls):
      print("Operator started and initialized")
      # TODO: check the presence of namespaces or cluster-wide flag here.

      cls.ensure_wp_crd_exists()

  def install_wordpress_via_php(self, name, path, title, tagline):
      logging.info(f" ↳ [install_wordpress_via_php] Configuring (ensure-wordpress-and-theme.php) with {name=}, {path=}, {title=}, {tagline=}")
      # https://stackoverflow.com/a/89243
      result = subprocess.run([Config.php, Config.wp_php_ensure,
                               f"--name={name}", f"--path={path}",
                               f"--wp-dir={Config.wp_dir}",
                               f"--wp-host={Config.wp_host}",
                               f"--db-host={Config.db_host}",
                               f"--db-name=wp-db-{name}",
                               f"--db-user=wp-db-user-{name}",
                               f"--db-password=secret",
                               f"--title={title}", f"--tagline={tagline}"], capture_output=True, text=True)
      print(result.stdout)
      if "WordPress successfully installed" not in result.stdout:
          raise subprocess.CalledProcessError(0, "PHP script failed")
      else:
          logging.info(f" ↳ [install_wordpress_via_php] End of configuring")

  def manage_plugins_php(self, name, plugins):
      logging.info(f" ↳ [manage_plugins_php] Configuring (manage-plugins.php) with {name=} and {plugins=}")
      # https://stackoverflow.com/a/89243
      result = subprocess.run([Config.php, Config.wp_php_ensure,
                               f"--name={name}",
                               f"--wp-dir={Config.wp_dir}",
                               f"--wp-host={Config.wp_host}",
                               f"--db-host={Config.db_host}",
                               f"--db-name=wp-db-{name}",
                               f"--db-user=wp-db-user-{name}",
                               f"--db-password=secret",
                               f"--plugins={plugins}"], capture_output=True, text=True)
      print(result.stdout)
      if "WordPress plugins successfully installed" not in result.stdout:
          raise subprocess.CalledProcessError(0, "PHP script failed")
      else:
          logging.info(f" ↳ [manage_plugins_php] End of configuring")

  def create_database(self, custom_api, namespace, name):
      logging.info(f" ↳ [{namespace}/{name}] Create Database wp-db-{name}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "Database",
          "metadata": {
              "name": f"wp-db-{name}",
              "namespace": namespace
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
          custom_api.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=namespace,
              plural="databases",
              body=body
          )
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{namespace}/{name}] Database wp-db-{name} already exists")

  def create_secret(self, api_instance, namespace, name, prefix, secret):
      logging.info(f" ↳ [{namespace}/{name}] Create Secret name={prefix + name}")
      secret_name = prefix + name
      body = client.V1Secret(
          type="Opaque",
          metadata=client.V1ObjectMeta(name=secret_name, namespace=namespace),
          string_data={"password": secret}
      )

      try:
          api_instance.create_namespaced_secret(namespace=namespace, body=body)
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{namespace}/{name}] Secret {secret_name} already exists")

  def delete_secret(self, api_instance, namespace, name, prefix):
      secret_name = prefix + name
      try:
          logging.info(f" ↳ [{namespace}/{name}] Delete Secret {secret_name}")

          api_instance.delete_namespaced_secret(namespace=namespace, name=secret_name)
      except ApiException as e:
          if e.status != 404:
              raise e
          logging.info(f" ↳ [{namespace}/{name}] Secret {secret_name} already deleted")

  def create_user(self, custom_api, namespace, name):
      user_name = f"wp-db-user-{name}"
      password_name = f"wp-db-password-{name}"
      logging.info(f" ↳ [{namespace}/{name}] Create User name={user_name}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "User",
          "metadata": {
              "name": user_name,
              "namespace": namespace
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
          custom_api.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=namespace,
              plural="users",
              body=body
          )
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{namespace}/{name}] User {user_name} already exists")


  def create_grant(self, custom_api, namespace, name):
      grant_name = f"wordpress-{name}"
      logging.info(f" ↳ [{namespace}/{name}] Create Grant {name=}")
      body = {
          "apiVersion": "k8s.mariadb.com/v1alpha1",
          "kind": "Grant",
          "metadata": {
              "name": grant_name,
              "namespace": namespace
          },
          "spec": {
              "mariaDbRef": {
                  "name": "mariadb-min"
              },
              "privileges": [
                  "ALL PRIVILEGES"
              ],
              "database": f"wp-db-{name}",
              "table" : "*",
              "username": f"wp-db-user-{name}",
              "grantOption": False,
              "host": "%"
          }
      }

      try:
          custom_api.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=namespace,
              plural="grants",
              body=body
          )
      except ApiException as e:
          if e.status != 409:
              raise e
          logging.info(f" ↳ [{namespace}/{name}] Grant {grant_name} already exists")

  def delete_custom_object_mariadb(self, custom_api, namespace, name, prefix, plural):
      mariadb_name = prefix + name
      logging.info(f" ↳ [{namespace}/{name}] Delete MariaDB object {mariadb_name}")
      try:
          custom_api.delete_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              plural=plural,
              namespace=namespace,
              name=mariadb_name
          )
      except ApiException as e:
          if e.status != 404:
              raise e
          logging.info(f" ↳ [{namespace}/{name}] MariaDB object {mariadb_name} already deleted")

  def get_os3_credentials(self, namespace, name, profile_name):
      logging.info(f"   ↳ [{namespace}/{name}] Get Restic and S3 secrets")

      file_path = "/keybase/team/epfl_wp_prod/aws-cli-credentials"

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

  def restore_wordpress_from_os3(self, custom_api, namespace, name, path, prefix, environment, ansible_host):
      logging.info(f" ↳ [{namespace}/{name}] Restoring WordPress from OS3")

      target = f"/tmp/backup/{name}"
      profile_name = "backup-wwp"
      backup_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'

      # Retrieve S3 credentials
      credentials = self.get_os3_credentials(namespace, name, profile_name)

      try:
          # Execute the Restic command to restore the backup
          restic_restore = subprocess.run([f"restic -r s3:https://s3.epfl.ch/{credentials['BUCKET_NAME']}/backup/wordpresses/www{path.replace('/','__').replace('-','_')}/sql restore latest --target {target}"], env=credentials, shell=True, capture_output=True, text=True)
          logging.info(f"   ↳ [{namespace}/{name}] SQL backup restored from S3")

          # Open file to write the modified SQL
          backup_file_path = f"/tmp/backup/{name}/backup.{backup_time}.sql"

          with open(backup_file_path, "w") as backup_file:
              logging.info(f"   ↳ [{namespace}/{name}] Replacing www.epfl.ch with wpn.fsd.team in SQL backup")
              sed_command = ["sed", "s/www\.epfl\.ch/wpn.fsd.team/g", f"{target}/db-backup.sql"]

              subprocess.run(sed_command, stdout=backup_file, check=True)

          copy_backup = subprocess.run([f"aws --endpoint-url=https://s3.epfl.ch --profile={profile_name} s3 cp {backup_file_path} s3://{credentials['BUCKET_NAME']}/backup/k8s/{name}/"], env=credentials, shell=True, capture_output=True, text=True)
          logging.info(f"   ↳ [{namespace}/{name}] SQL backup copied to S3")

          # Initiate the restore process in MariaDB
          restore_spec = {
              "apiVersion": "k8s.mariadb.com/v1alpha1",
              "kind": "Restore",
              "metadata": {
                  "name": f"restore-{name}-{round(time.time())}",
                  "namespace": namespace
              },
              "spec": {
                  "mariaDbRef": {
                      "name": "mariadb-min"
                  },
                  "s3": {
                      "bucket": credentials["BUCKET_NAME"],
                      "prefix": f"backup/k8s/{name}",
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
                      f"--database={prefix}{name}"
                  ]
              }
          }

          logging.info(f"   ↳ [{namespace}/{name}] Creating restore object in Kubernetes")
          custom_api.create_namespaced_custom_object(
              group="k8s.mariadb.com",
              version="v1alpha1",
              namespace=namespace,
              plural="restores",
              body=restore_spec
          )
          logging.info(f"   ↳ [{namespace}/{name}] Restore initiated on MariaDB")

          logging.info(f"   ↳ [{namespace}/{name}] Restoring media from OS3")

          pvc_name = "wordpress-test-wp-uploads-pvc-f401a87f-d2e9-4b20-85cc-61aa7cfc9d30"
          copy_media = subprocess.run([f"ssh -t root@itswbhst0020.xaas.epfl.ch 'cp -r /mnt/data-prod-ro/wordpress/{environment}/www.epfl.ch/htdocs{path}/wp-content/uploads/ /mnt/data/nfs-storageclass/{pvc_name}/wp-uploads/{name}/; chown -R 33:33 /mnt/data/nfs-storageclass/{pvc_name}/wp-uploads/{name}/uploads'"], shell=True, capture_output=True, text=True)

          logging.info(f"   ↳ [{namespace}/{name}] Restored media from OS3")
      except subprocess.CalledProcessError as e:
          logging.error(f"Subprocess error in backup restoration: {e}")
      except FileNotFoundError as e:
          logging.error(f"File error in backup restoration: {e}")
      except Exception as e:
          logging.error(f"Unexpected error: {e}")


  def create_fn(self, spec, name, namespace, logger):
      logging.info(f"Create WordPressSite {name=} in {namespace=}")
      path = spec.get('path')
      wordpress = spec.get("wordpress")
      epfl = spec.get("epfl")
      import_from_os3 = epfl.get("importFromOS3")
      title = wordpress["title"]
      tagline = wordpress["tagline"]
      config.load_kube_config()
      networking_v1_api = client.NetworkingV1Api()
      custom_api = client.CustomObjectsApi()
      api_instance = client.CoreV1Api()

      secret = "secret" # Password, for the moment hard coded.

      self.create_database(custom_api, namespace, name)
      self.create_secret(api_instance, namespace, name, 'wp-db-password-', secret)
      self.create_user(custom_api, namespace, name)
      self.create_grant(custom_api, namespace, name)

      if (not import_from_os3):
          self.install_wordpress_via_php(name, path, title, tagline)
      else:
          environment = import_from_os3["environment"]
          ansible_host = import_from_os3["ansibleHost"]
          self.restore_wordpress_from_os3(custom_api, namespace, name, path, "wp-db-", environment, ansible_host)
          self.manage_plugins_php(name, "test,test,test")

      logging.info(f"End of create WordPressSite {name=} in {namespace=}")


  def delete_fn(self, spec, name, namespace, logger):
      logging.info(f"Delete WordPressSite {name=} in {namespace=}")
      config.load_kube_config()
      networking_v1_api = client.NetworkingV1Api()
      custom_api = client.CustomObjectsApi()
      api_instance = client.CoreV1Api()

      # Deleting database
      self.delete_custom_object_mariadb(custom_api, namespace, name, "wp-db-", "databases")
      self.delete_secret(api_instance, namespace, name, 'wp-db-password-')
      # Deleting user
      self.delete_custom_object_mariadb(custom_api, namespace, name, "wp-db-user-", "users")
      # Deleting grant
      self.delete_custom_object_mariadb(custom_api, namespace, name, "wordpress-", "grants")

if __name__ == '__main__':
    Config.load_from_command_line()
    sys.exit(kopf.cli.main())
