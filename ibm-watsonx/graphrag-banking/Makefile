.PHONY: sync check reset ingest rebuild chat baseline eval lint test \
	wxo-connection wxo-tools wxo-agent wxo-baseline wxo-setup wxo-deploy

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

rebuild: reset ingest

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

# watsonx Orchestrate (Phase 5). Run `orchestrate env activate <env>` first.
# wxo-setup builds everything in order. Each target is safe to re-run.
wxo-connection:
	./orchestrate/create_connection.sh

wxo-tools:
	./orchestrate/build_tools.sh

wxo-agent:
	uv run python orchestrate/build_agent.py
	orchestrate agents import -f orchestrate/build/banking_support.yaml

wxo-baseline:
	./orchestrate/build_baseline.sh

wxo-setup: wxo-connection wxo-tools wxo-agent wxo-baseline

# Publish both agents from draft (preview chat) to live.
wxo-deploy:
	orchestrate agents deploy --name banking_support
	orchestrate agents deploy --name banking_baseline