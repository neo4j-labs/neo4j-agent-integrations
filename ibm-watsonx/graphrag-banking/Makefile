.PHONY: sync check reset ingest rebuild chat baseline eval lint test

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
