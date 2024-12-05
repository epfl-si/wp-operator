#!/bin/bash
mkdir "secretFiles"

# For development purposes, get plugin secrets from kubectl and save them decoded in the secretFiles directory
# This is not in prod because Kubernetes take care of it
jsonSecret=$(kubectl get secrets -n wordpress-test wp-plugin-secrets -o json | jq -r '.data')
for key in $(echo "$jsonSecret" | jq -r 'keys[]'); do
  # Get the value for the current key
  value=$(echo "$jsonSecret" | jq -r --arg key "$key" '.[$key]')

  # Save the value to a file named after the key
  echo "$value" | base64 --decode > "./secretFiles/$key"
done


