#!/usr/bin/env bash
# Create the beat 1 baseline: a built-in knowledge base of the policy documents,
# and an agent that answers from it.
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=orchestrate/build/baseline
rm -rf "$OUT"
mkdir -p "$OUT/policies"

# The knowledge base does not accept .md files, so upload them as .txt.
for doc in data/policies/*.md; do
  cp "$doc" "$OUT/policies/$(basename "${doc%.md}").txt"
done

{
  echo "spec_version: v1"
  echo "kind: knowledge_base"
  echo "name: banking_policies"
  echo "description: The bank's fee, hold, overdraft, wire, and compliance policies."
  echo "documents:"
  for doc in "$OUT"/policies/*.txt; do
    echo "  - policies/$(basename "$doc")"
  done
} > "$OUT/banking_policies.yaml"

orchestrate knowledge-bases import -f "$OUT/banking_policies.yaml"
orchestrate knowledge-bases status -n banking_policies
orchestrate agents import -f orchestrate/baseline_agent.yaml