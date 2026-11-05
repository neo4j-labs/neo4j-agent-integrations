#!/usr/bin/env bash
# Assemble the Orchestrate tool package from the project's tools and import it.
# tools.py and embeddings.py stay the single source of truth: this script copies
# them next to the wrapper on every run, so the package never drifts.
set -euo pipefail
cd "$(dirname "$0")/.."

SRC=src/graphrag_banking
# The folder name must differ from the tool file name: the ADK imports the
# file as <folder>.<file> while checking it locally.
PKG=orchestrate/build/banking_package

rm -rf "$PKG"
mkdir -p "$PKG"
touch "$PKG/__init__.py"
cp orchestrate/tools/banking_tools.py "$PKG/"
cp "$SRC/embeddings.py" "$PKG/"
# Orchestrate runs the tool file as a top-level module, so the files import
# each other by plain module name. tools.py is renamed so it can't clash with
# another module called "tools".
sed 's/^from graphrag_banking\.embeddings import embed$/from embeddings import embed/' \
  "$SRC/tools.py" > "$PKG/banking_queries.py"
grep -q '^from embeddings import embed$' "$PKG/banking_queries.py" \
  || { echo "tools.py import was not rewritten; check its embeddings import" >&2; exit 1; }

# uv.lock is the source of truth for versions. Export it and keep only the
# packages the tools import. Orchestrate installs their own dependencies.
REQS=orchestrate/build/requirements.txt
uv export --format requirements-txt --no-hashes --no-dev --no-header --no-annotate \
  | grep -E '^(neo4j|openai)==' > "$REQS"
[[ $(wc -l < "$REQS") -eq 2 ]] \
  || { echo "Expected neo4j and openai pins in $REQS, got:" >&2; cat "$REQS" >&2; exit 1; }

orchestrate tools import -k python \
  -p "$PKG" \
  -f "$PKG/banking_tools.py" \
  -r "$REQS" \
  -a banking_creds

echo "Imported the 6 banking tools."