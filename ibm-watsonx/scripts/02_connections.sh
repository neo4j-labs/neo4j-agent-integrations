#!/usr/bin/env bash
# Create the key_value connection holding Neo4j credentials.
# Both draft (tool discovery) and live (runtime) environments are configured.
set -euo pipefail
source "$(dirname "$0")/../.env"

orchestrate connections add --app-id "$CONNECTION_APP_ID" || true

for env in draft live; do
  orchestrate connections configure --app-id "$CONNECTION_APP_ID" \
    --environment "$env" --kind key_value --type team

  orchestrate connections set-credentials --app-id "$CONNECTION_APP_ID" \
    --environment "$env" \
    -e "NEO4J_URI=$NEO4J_URI" \
    -e "NEO4J_USERNAME=$NEO4J_USERNAME" \
    -e "NEO4J_PASSWORD=$NEO4J_PASSWORD" \
    -e "NEO4J_DATABASE=$NEO4J_DATABASE" \
    -e "NEO4J_READ_ONLY=$NEO4J_READ_ONLY"
done

orchestrate connections list
