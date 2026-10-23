.PHONY: sync check reset ingest rebuild demo-reset chat baseline eval lint test \
	wxo-env wxo-connection wxo-tools wxo-agent wxo-baseline wxo-policy \
	wxo-staff-connection wxo-staff-tools wxo-staff-agents wxo-supervisor \
	wxo-setup wxo-staff-setup wxo-check wxo-list wxo-deploy wxo-eval

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

# The banker_creds connection the staff tools read their settings from.
wxo-staff-connection:
	./orchestrate/create_staff_connection.sh

# The staff tools for the relationship manager demo. Needs the banker_creds
# connection from wxo-staff-connection.
wxo-staff-tools:
	./orchestrate/build_staff_tools.sh

# The two staff specialists. Needs the staff tools from wxo-staff-tools.
wxo-staff-agents:
	orchestrate agents import -f orchestrate/credit_analyst_agent.yaml
	orchestrate agents import -f orchestrate/fraud_investigator_agent.yaml

# The supervisor. Import it last, because it lists banking_policy,
# credit_analyst, and fraud_investigator as collaborators.
wxo-supervisor:
	orchestrate agents import -f orchestrate/bank_supervisor.yaml

wxo-setup: wxo-connection wxo-tools wxo-agent wxo-baseline

# Builds the staff demo in order. Needs the banking_policies knowledge base
# from wxo-setup.
wxo-staff-setup: wxo-staff-connection wxo-staff-tools wxo-policy wxo-staff-agents wxo-supervisor

# Check that wxo-setup created every demo object and wired them together.
wxo-check:
	uv run python orchestrate/check_setup.py

# List the demo's connections, tools, knowledge base, and agents saved in the
# active Orchestrate environment.
wxo-list:
	uv run python orchestrate/list_demo.py

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
