#!/usr/bin/env bash
# Run eval/scenarios.yaml against Orchestrate agents and score the answers.
# `make wxo-eval` calls this. The runner needs the ADK's Python and the scorer
# needs the project's environment, so it runs two scripts.
#
#   AGENTS=banking_support   comma-separated agent names
#   SCENARIOS=A,B,C,D        comma-separated scenario IDs, or "all"
#   PERSONA=customer         the persona "all" runs: customer or staff
#   RUNS=1                   runs per scenario
#   SAME_THREAD=             1 sends the scenarios in order in one thread per run
#   REFERRAL_FLOW=           1 runs E then J in one thread and presses Confirm on
#                            the fraud_referral flow's form. Ignores SCENARIOS.
#   SUPERVISOR_CHECK=        1 also runs supervisor_check.py on the saved results
#   TRACES_DIR=eval/results/traces   where supervisor_check.py caches traces
set -euo pipefail
cd "$(dirname "$0")/../.."

AGENTS="${AGENTS:-banking_support}"
SCENARIOS="${SCENARIOS:-A,B,C,D}"
PERSONA="${PERSONA:-customer}"
RUNS="${RUNS:-1}"
SAME_THREAD="${SAME_THREAD:-}"
REFERRAL_FLOW="${REFERRAL_FLOW:-}"
SUPERVISOR_CHECK="${SUPERVISOR_CHECK:-}"
TRACES_DIR="${TRACES_DIR:-eval/results/traces}"

ADK_PY="$(uv tool dir)/ibm-watsonx-orchestrate/bin/python"
runs_dir="$(mktemp -d)"
trap 'rm -rf "$runs_dir"' EXIT

args=(--agents "$AGENTS" --scenarios "$SCENARIOS" --persona "$PERSONA" --runs "$RUNS")
if [[ "$SAME_THREAD" == 1 ]]; then
  args+=(--same-thread)
fi
if [[ "$REFERRAL_FLOW" == 1 ]]; then
  args+=(--referral-flow)
fi

"$ADK_PY" -I eval/eval-scripts/run_agent.py "$runs_dir" "${args[@]}"
status=0
uv run python eval/eval-scripts/score.py "$runs_dir" || status=$?

# score.py exits 1 when a run fails, after it saves the results.
if [[ "$SUPERVISOR_CHECK" == 1 && "$status" -le 1 ]]; then
  results="$(ls -t eval/results/wxo-eval-*.json | head -1)"
  ADK_PY="$ADK_PY" uv run python eval/eval-scripts/supervisor_check.py \
    "$results" "$TRACES_DIR" || status=$?
fi
exit "$status"
