#!/bin/bash
mkdir "secretFiles"

jsonSecret=$(kubectl get secrets -n wordpress-test wp-plugin-secrets -o json | jq -r '.data')
for key in $(echo "$jsonSecret" | jq -r 'keys[]'); do
  # Get the value for the current key
  value=$(echo "$jsonSecret" | jq -r --arg key "$key" '.[$key]')

  # Save the value to a file named after the key
  echo "$value" | base64 --decode > "./secretFiles/$key"
done


