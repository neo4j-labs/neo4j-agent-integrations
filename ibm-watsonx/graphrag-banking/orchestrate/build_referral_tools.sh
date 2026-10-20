#!/usr/bin/env bash
# Assemble the Orchestrate package for the fraud referral tools, import it,
# then import the fraud_referral flow that calls them.
# referral_tools.py stays the single source of truth: this script copies it
# next to the wrapper on every run, so the package never drifts.
set -euo pipefail
cd "$(dirname "$0")/.."

# The review form goes to this tenant user. The flow looks the user up by
# email when it runs, so the address must belong to a real tenant login.
: "${FRAUD_REVIEWER_EMAIL:?Set FRAUD_REVIEWER_EMAIL to the tenant login for Sam Price}"

SRC=src/graphrag_banking
# The folder name must differ from the tool file name: the ADK imports the
# file as <folder>.<file> while checking it locally.
PKG=orchestrate/build/referral_package

rm -rf "$PKG"
mkdir -p "$PKG"
touch "$PKG/__init__.py"
cp orchestrate/tools/referral_banking_tools.py "$PKG/"
# Orchestrate runs the tool file as a top-level module, so the files import
# each other by plain module name. referral_tools.py is renamed so it can't
# clash with another module called "referral_tools".
cp "$SRC/referral_tools.py" "$PKG/referral_queries.py"
# referral_tools.py imports only the standard library and neo4j at module
# level. Its main() imports graphrag_banking inside the function, which never
# runs in Orchestrate. A module-level package import would fail there, so stop
# here if one appears.
! grep -qE '^(from|import) graphrag_banking' "$PKG/referral_queries.py" \
  || { echo "referral_tools.py imports graphrag_banking; rewrite it here" >&2; exit 1; }

# uv.lock is the source of truth for versions. Export it and keep only the
# package the tools import. Orchestrate installs its own dependencies.
REQS=orchestrate/build/referral_requirements.txt
uv export --format requirements-txt --no-hashes --no-dev --no-header --no-annotate \
  | grep -E '^neo4j==' > "$REQS"
[[ $(wc -l < "$REQS") -eq 1 ]] \
  || { echo "Expected one neo4j pin in $REQS, got:" >&2; cat "$REQS" >&2; exit 1; }

orchestrate tools import -k python \
  -p "$PKG" \
  -f "$PKG/referral_banking_tools.py" \
  -r "$REQS" \
  -a banker_creds

echo "Imported the 2 referral tools."

# The flow calls the tools by name, so it is imported after them.
orchestrate tools import -k flow -f orchestrate/flows/fraud_referral_flow.py

echo "Imported the fraud_referral flow."
