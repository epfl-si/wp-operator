#!/bin/bash

_SECRETS_PATH="${_SECRETS_PATH:=secretFiles}"
_K8S_NAMESPACE="${_K8S_NAMESPACE:=wordpress-test}"
_K8S_SECRET_NAME="${_K8S_SECRET_NAME:=wp-plugin-secrets}"

# Execute the commands of this script in its directory
cd "$(dirname "$0")"; cd "$(/bin/pwd)"
mkdir -p $_SECRETS_PATH

# Create a .gitignore to avoid divulding created secrets
if [ ! -f .gitignore ]; then
  echo $_SECRETS_PATH > .gitignore
else
  cat .gitignore | grep -q "$_SECRETS_PATH" || echo $_SECRETS_PATH >> .gitignore
fi

# Be sure to be able to access the cluster
if [[ `kubectl get secrets -A` -ne 1 ]] &>/dev/null; then
  echo "Error accessing Kubernetes cluster. Be sure to have a KUBECONFIG exported."
  exit 1
fi

# For development purposes, get plugin secrets from kubectl and save them decoded in the secretFiles directory
# This is not in prod because Kubernetes take care of it
jsonSecret=$(kubectl get secrets -n ${_K8S_NAMESPACE} ${_K8S_SECRET_NAME} -o json | jq -r '.data')
for key in $(echo "$jsonSecret" | jq -r 'keys[]'); do
  echo "...saving secrets $key"
  # Get the value for the current key
  value=$(echo "$jsonSecret" | jq -r --arg key "$key" '.[$key]')

  # Save the value to a file named after the key
  echo "$value" | base64 --decode > "./$_SECRETS_PATH/$key"
done
