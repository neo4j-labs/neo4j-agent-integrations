#!/usr/bin/env bash
# Add the watsonx Orchestrate environment and activate it. Values come from
# .env. The API key is passed to `env activate`, so nothing prompts. Safe to
# re-run: it skips the add when the environment exists and logs in again,
# which renews the two-hour token.
#
# The ADK picks the auth type from the instance URL. Set WO_AUTH_TYPE in .env
# (for example ibm_iam) only when that guess is wrong. It applies at add time.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
# shellcheck disable=SC1091
source .env
set +a

for key in WO_ENV_NAME WO_INSTANCE_URL WO_API_KEY; do
  [[ -n "${!key:-}" ]] || { echo "$key is not set in .env" >&2; exit 1; }
done

if ! orchestrate env list 2>/dev/null | grep "^ *$WO_ENV_NAME " >/dev/null; then
  if [[ -n "${WO_AUTH_TYPE:-}" ]]; then
    orchestrate env add -n "$WO_ENV_NAME" -u "$WO_INSTANCE_URL" --type "$WO_AUTH_TYPE"
  else
    orchestrate env add -n "$WO_ENV_NAME" -u "$WO_INSTANCE_URL"
  fi
fi

orchestrate env activate "$WO_ENV_NAME" --api-key "$WO_API_KEY"
