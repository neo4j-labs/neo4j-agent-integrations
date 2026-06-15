# DataRobot + Neo4j Integration

## Overview

**DataRobot** is an enterprise AI platform for building, deploying, and operating agentic workflows and models. This integration shows how to package a **Neo4j-backed research agent** as a DataRobot custom model that speaks the OpenAI-compatible `chat()` interface DataRobot expects for agentic workflows.

**What this example demonstrates:**
- A DataRobot custom-model `chat()` entrypoint that runs locally and in DataRobot
- Direct Neo4j query tools over the public Companies demo graph
- OpenAI tool-calling to turn those graph tools into a research agent
- Packaging helpers for manual upload into a DataRobot custom model

## Architecture

```text
User / Playground / API client
            |
            v
DataRobot Agentic Workflow (custom model: chat())
            |
            +--> OpenAI tool-calling loop
            |       |
            |       +--> Neo4j query tools
            |               |
            v               v
      Synthesised answer   Neo4j Companies demo graph
```

## Files

```text
datarobot/
├── .env.example
├── README.md
├── requirements.txt
├── run_local.py
├── datarobot_agent.ipynb
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── custom.py
│   ├── helpers.py
│   ├── model-metadata.yaml
│   └── requirements.txt
└── infra/
    ├── __init__.py
    └── agent.py
```

## Local setup

```bash
cd datarobot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in:
- `OPENAI_API_KEY`
- `DATAROBOT_ENDPOINT`
- `DATAROBOT_API_TOKEN`

Neo4j defaults already target the public demo database:

```bash
NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687
NEO4J_USERNAME=companies
NEO4J_PASSWORD=companies
NEO4J_DATABASE=companies
```

## Run locally

The local runner calls the same `agent.custom.chat()` function that DataRobot will call after deployment.

```bash
python run_local.py "Give me a competitive snapshot of Google including recent news and relationships."
```

To inspect the full OpenAI-compatible response envelope:

```bash
python run_local.py --json
```

## Agent tools

The agent exposes these Neo4j-backed tools to the LLM:
- `search_companies`
- `list_industries`
- `companies_in_industry`
- `query_company`
- `analyze_relationships`
- `people_at_company`
- `search_news`
- `articles_in_month`
- `get_article`
- `companies_in_article`

This aligns with the repository's `EXAMPLE_AGENT.md` research-agent pattern.

## DataRobot packaging and validation

Create a ZIP package containing the agent files:

```bash
python infra/agent.py package
```

Validate DataRobot credentials/network reachability from your shell:

```bash
python infra/agent.py validate
```

Package and validate in one go:

```bash
python infra/agent.py package-and-validate
```

## Runtime parameters

The DataRobot custom model expects these runtime parameters from `agent/model-metadata.yaml`:

| Parameter | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key used for tool-calling and embeddings |
| `OPENAI_MODEL` | Chat model, default `gpt-4o-mini` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model for semantic news search |
| `NEO4J_URI` | Neo4j connection string |
| `NEO4J_USERNAME` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `NEO4J_DATABASE` | Neo4j database name |
| `AGENT_MAX_TOOL_STEPS` | Max tool loop iterations |

## Notes

- Secrets are loaded from runtime parameters first and `.env` for local development only.
- `infra/agent.py` packages the custom-model payload and validates API access. In this environment, remote validation may still be blocked by an intercepting corporate proxy even when the token is correct.
- This integration keeps the LLM path simple by using OpenAI directly. If the client later wants the DataRobot LLM Gateway path, the same Neo4j tool layer can be reused behind a different chat client.
