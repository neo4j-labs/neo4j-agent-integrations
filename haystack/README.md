# Haystack + Neo4j MCP Integration

## What this example is

This folder shows a simple way to let a Haystack agent talk to a Neo4j graph database through the Neo4j MCP server.

In plain terms:
- Haystack is the "assistant brain" that decides what to do.
- Neo4j MCP server is the "safe gateway" to the graph.
- The agent calls named tools like `get-schema` and `read-cypher` instead of opening a raw database connection itself.

Main notebook: `neo4j_mcp_haystack.ipynb`

## Why use MCP here

Instead of writing custom retriever code, this setup uses MCP tools directly.

Benefits:
- Less custom code to maintain.
- Clear tool boundary between agent and database.
- Easy to run in read-only mode.

## What the notebook does

1. Installs Haystack, `mcp-haystack`, and Neo4j MCP packages.
2. Starts Neo4j MCP server in HTTP mode.
3. Sends Neo4j credentials in request headers (not fixed into server env vars).
4. Verifies available tools before using an LLM.
5. Builds a Haystack `Agent` with MCP tools.
6. Runs example user questions.
7. Adds a custom Haystack tool (`get_investments`) alongside MCP tools.
8. Shuts down cleanly.

## Security and safety choices in this example

- Uses `NEO4J_READ_ONLY=true` so write tools are not exposed.
- Uses a tool allow-list in Haystack: only `get-schema` and `read-cypher`.
- Encourages schema-first behavior so the model does not guess labels or properties.

## Quick start

1. Open `neo4j_mcp_haystack.ipynb`.
2. Set your `OPENAI_API_KEY` in environment or `.env`.
3. Run cells top to bottom.
4. Ask graph questions through the provided helper function.

The notebook is already configured for the public Neo4j demo database:
- URI: `neo4j+s://demo.neo4jlabs.com`
- Database: `companies`
- Username/Password: `companies` / `companies`

## Resources

- Haystack: https://haystack.deepset.ai/
- Haystack docs: https://docs.haystack.deepset.ai/
- Neo4j MCP docs: https://neo4j.com/docs/mcp/current/
- Neo4j + Haystack developer page: https://neo4j.com/developer/genai-ecosystem/haystack/

## Current status

- MCP-based Haystack integration: available in notebook.
- Read-only graph querying pattern: implemented.
- Custom tool + MCP tool mix: implemented.
