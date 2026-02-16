# Google ADK + Neo4j MCP Integration

## Overview

**Google ADK** (Agent Development Kit) is a framework for building AI agents that can leverage external tools and data sources. This integration enables Google ADK agents to connect to Neo4j via the [Neo4j MCP server](https://neo4j.com/docs/mcp/current/), providing access to Cypher query execution, schema introspection, and more.

## Installation

Follow the [Neo4j MCP documentation](https://neo4j.com/docs/mcp/current/) for server setup and prerequisites (Neo4j instance, APOC plugin, etc.).

**Google ADK:**

- [Google ADK Documentation](https://google.github.io/adk-docs)

## Example

| Notebook | Description |
|----------|-------------|
| [google_adk.ipynb](./google_adk.ipynb) | Walkthrough of using Google ADK with Neo4j MCP: agent setup, Cypher query execution, and schema access |

## Key Features

- Connect Google ADK agents to Neo4j via MCP
- Execute Cypher queries (read/write) from agents
- Introspect graph schema and available tools
- Leverage Neo4j as a knowledge graph for agent reasoning

## Authentication

Neo4j MCP supports two authentication modes:

- **Environment Variables (STDIO mode):**
    - Set `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` in the environment before launching the MCP server.
- **HTTP Headers (HTTP mode):**
    - Pass credentials via HTTP headers (e.g., `Authorization: Basic ...` or `Bearer ...`).

See [Neo4j MCP documentation](https://neo4j.com/docs/mcp/current/) for details and configuration examples.

## Resources

- [Neo4j MCP Documentation](https://neo4j.com/docs/mcp/current/)
- [Google ADK Documentation](https://google.github.io/adk-docs)
