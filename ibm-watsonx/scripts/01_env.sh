#!/usr/bin/env bash
# Register and activate the Orchestrate environment.
set -euo pipefail
source "$(dirname "$0")/../.env"

orchestrate env add -n "$WO_ENV_NAME" -u "$WO_INSTANCE_URL" --activate
orchestrate env list
