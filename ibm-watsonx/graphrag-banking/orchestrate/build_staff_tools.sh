#!/usr/bin/env bash
# Assemble the Orchestrate package for the staff tools and import it.
# staff_tools.py stays the single source of truth: this script copies it next
# to the wrapper on every run, so the package never drifts.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=src/graphrag_banking
# The folder name must differ from the tool file name: the ADK imports the
# file as <folder>.<file> while checking it locally.
PKG=orchestrate/build/staff_package

rm -rf "$PKG"
mkdir -p "$PKG"
touch "$PKG/__init__.py"
cp orchestrate/tools/staff_banking_tools.py "$PKG/"
# Orchestrate runs the tool file as a top-level module, so the files import
# each other by plain module name. staff_tools.py is renamed so it can't clash
# with another module called "staff_tools".
cp "$SRC/staff_tools.py" "$PKG/staff_queries.py"
# staff_tools.py imports only the standard library and neo4j. A package import
# would fail inside Orchestrate, so stop here if one appears.
! grep -qE '^(from|import) graphrag_banking' "$PKG/staff_queries.py" \
  || { echo "staff_tools.py imports graphrag_banking; rewrite it here" >&2; exit 1; }

# uv.lock is the source of truth for versions. Export it and keep only the
# package the tools import. Orchestrate installs its own dependencies.
REQS=orchestrate/build/staff_requirements.txt
uv export --format requirements-txt --no-hashes --no-dev --no-header --no-annotate \
  | grep -E '^neo4j==' > "$REQS"
[[ $(wc -l < "$REQS") -eq 1 ]] \
  || { echo "Expected one neo4j pin in $REQS, got:" >&2; cat "$REQS" >&2; exit 1; }

orchestrate tools import -k python \
  -p "$PKG" \
  -f "$PKG/staff_banking_tools.py" \
  -r "$REQS" \
  -a banker_creds

echo "Imported the 6 staff tools."
