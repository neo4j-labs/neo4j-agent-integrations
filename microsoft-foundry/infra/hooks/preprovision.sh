#!/usr/bin/env bash
set -euo pipefail

# Skip in non-interactive contexts (CI, piped stdin).
[ -t 0 ] && [ -t 1 ] || exit 0

# If CREATE_FOUNDRY_PROJECT is already set in this azd env, don't re-prompt.
existing="$(azd env get-value CREATE_FOUNDRY_PROJECT 2>/dev/null || true)"
case "$existing" in
  true|false) exit 0 ;;
esac

cat <<'INFO'

Microsoft Foundry provisioning
  Provisions a Foundry account, project, and a gpt-4o-mini model
  deployment in the same resource group, plus an Azure AI Developer
  role assignment for you so `az login` is all the auth examples need.
  Skip this if you already have a Foundry project to use instead.

INFO

read -r -p "Provision Microsoft Foundry too? [Y/n] " response
response_lc="$(printf '%s' "$response" | tr '[:upper:]' '[:lower:]')"
case "$response_lc" in
  n|no) azd env set CREATE_FOUNDRY_PROJECT false ;;
  *)    azd env set CREATE_FOUNDRY_PROJECT true ;;
esac
