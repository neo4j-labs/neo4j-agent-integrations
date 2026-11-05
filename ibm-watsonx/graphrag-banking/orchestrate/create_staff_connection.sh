#!/usr/bin/env bash
# Create the banker_creds connection the staff tools read their settings from.
# Values come from .env. The same values are set for draft and live. Draft
# serves the preview chat, and live serves the deployed agent. Safe to re-run:
# it updates the values in place.
# DEMO_BANKER_ID fixes the signed-in banker until the member connection lands.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
# shellcheck disable=SC1091
source .env
set +a

APP_ID=banker_creds
KEYS=(NEO4J_URI NEO4J_USERNAME NEO4J_PASSWORD NEO4J_DATABASE DEMO_BANKER_ID
      DEMO_AS_OF)

args=()
for key in "${KEYS[@]}"; do
  [[ -n "${!key:-}" ]] || { echo "$key is not set in .env" >&2; exit 1; }
  args+=(-e "$key=${!key}")
done

if ! orchestrate connections list 2>/dev/null | grep "\b$APP_ID\b" >/dev/null; then
  orchestrate connections add --app-id "$APP_ID"
fi

for env in draft live; do
  orchestrate connections configure --app-id "$APP_ID" --environment "$env" \
    --kind key_value --type team
  orchestrate connections set-credentials --app-id "$APP_ID" --environment "$env" "${args[@]}"
done

echo "Connection $APP_ID is set for draft and live."
