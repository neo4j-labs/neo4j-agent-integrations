#!/usr/bin/env bash
# Import the curated Python tool. Dependencies in requirements.txt are
# installed server-side; the first call after import may return
# "We are configuring your tool in the background" - wait and retry.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env

orchestrate tools import -k python \
  -f tools/get_investments.py \
  -r tools/requirements.txt \
  -a "$CONNECTION_APP_ID"

orchestrate tools list
