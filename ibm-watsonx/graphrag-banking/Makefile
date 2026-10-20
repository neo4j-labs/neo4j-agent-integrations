.PHONY: sync check reset ingest rebuild demo-reset chat baseline eval lint test \
	wxo-env wxo-connection wxo-tools wxo-agent wxo-baseline wxo-policy \
	wxo-staff-tools wxo-staff-agents wxo-setup wxo-check wxo-deploy wxo-eval

sync:
	uv sync

check:
	uv run check-connection

reset:
	uv run reset-db

# Works on a fresh clone. Run `make rebuild` instead of `make ingest` twice,
# because each build-policy-graph run writes new Chunk nodes.
ingest:
	uv run generate-data
	uv run render-policies
	uv run validate-data
	uv run load-structured
	uv run build-policy-graph
	uv run build-groups

rebuild: reset ingest

# Deletes every FraudReferral the fraud_referral flow wrote, so the loan fraud
# demo can run again from Scenario E. Leaves the rest of the graph alone.
demo-reset:
	uv run python -m graphrag_banking.referral_tools --cleanup

chat:
	uv run chat

baseline:
	uv run baseline-rag

eval:
	uv run eval-local

lint:
	uv run ruff check src

test:
	uv run pytest

# watsonx Orchestrate (Phase 5). Run `make wxo-env` first.
# wxo-setup builds everything in order. Each target is safe to re-run.
# Adds and activates the Orchestrate environment from .env. Re-run it when
# the two-hour login expires.
wxo-env:
	./orchestrate/connect_env.sh

wxo-connection:
	./orchestrate/create_connection.sh

wxo-tools:
	./orchestrate/build_tools.sh

wxo-agent:
	uv run python orchestrate/build_agent.py
	orchestrate agents import -f orchestrate/build/banking_support.yaml

wxo-baseline:
	./orchestrate/build_baseline.sh

# The general policy agent a supervisor routes to. Needs the banking_policies
# knowledge base from wxo-baseline.
wxo-policy:
	orchestrate agents import -f orchestrate/banking_policy_agent.yaml

# The staff tools for the relationship manager demo. Needs the banker_creds
# connection from orchestrate/create_staff_connection.sh.
wxo-staff-tools:
	./orchestrate/build_staff_tools.sh

# The two staff specialists. Needs the staff tools from wxo-staff-tools.
wxo-staff-agents:
	orchestrate agents import -f orchestrate/credit_analyst_agent.yaml
	orchestrate agents import -f orchestrate/fraud_investigator_agent.yaml

wxo-setup: wxo-connection wxo-tools wxo-agent wxo-baseline

# Check that wxo-setup created every demo object and wired them together.
wxo-check:
	uv run python orchestrate/check_setup.py

# Publish both agents from draft (preview chat) to live.
wxo-deploy:
	orchestrate agents deploy --name banking_support
	orchestrate agents deploy --name banking_baseline

# Score eval/scenarios.yaml against Orchestrate agents. Override, for example:
# make wxo-eval AGENTS=banking_support,banking_support_frontier RUNS=3 SCENARIOS=A,B
# SAME_THREAD=1 sends the scenarios in order in one chat thread.
AGENTS ?= banking_support
SCENARIOS ?= A,B,C,D
RUNS ?= 1
SAME_THREAD ?=
wxo-eval:
	AGENTS=$(AGENTS) SCENARIOS=$(SCENARIOS) RUNS=$(RUNS) SAME_THREAD=$(SAME_THREAD) \
		./eval/eval-scripts/wxo_eval.sh
