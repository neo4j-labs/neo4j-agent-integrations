# Flue + Neo4j Integration

## Overview

**Flue** is a TypeScript framework for building agents as functions. This integration shows two ways to give a Flue agent read-only access to Neo4j:

- Custom tools backed by the Neo4j JavaScript driver
- Flue's native MCP client connected to the official Neo4j MCP server

Both examples use the public Company News Knowledge Graph and the same Neo4j credentials.

## Examples

| File | Description |
|---|---|
| [`src/agents/industry-research-agent.ts`](src/agents/industry-research-agent.ts) | Agent with two fixed Neo4j tools for company profiles and news |
| [`src/tools/neo4j.ts`](src/tools/neo4j.ts) | Neo4j driver, parameterized Cypher, and Flue tool definitions |
| [`src/agents/neo4j-mcp-research-agent.ts`](src/agents/neo4j-mcp-research-agent.ts) | Agent using Neo4j through Flue's native MCP support |
| [`src/connections/neo4j-mcp.ts`](src/connections/neo4j-mcp.ts) | Neo4j MCP URL, Basic authentication, and read-only tool allowlist |

## Prerequisites

- Node.js 22.19 or newer
- An Anthropic API key
- For the MCP example, `uv` to run the Neo4j MCP server locally, or an existing Neo4j MCP HTTP endpoint

## Setup

```bash
cd flue
npm install
cp .env.example .env
```

Add your Anthropic API key to `.env`:

```dotenv
ANTHROPIC_API_KEY="your-anthropic-api-key"

NEO4J_URI="neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_USERNAME="companies"
NEO4J_PASSWORD="companies"
NEO4J_DATABASE="companies"

# Optional; used only by the MCP agent
NEO4J_MCP_URL="http://localhost:8000/mcp"
```

The included Neo4j values point to a public, read-only demo database.

## Direct Neo4j Tools

The direct agent exposes two fixed tools:

- `query_company_profile` returns an organization's summary, industries, and leadership.
- `search_company_news` returns its most recently dated stored articles.

Run it with:

```bash
npm run agent -- \
  --id google-research \
  --message "Research Google and summarize its recent news."
```

Reuse the same `--id` to continue the conversation.

The tools use parameterized Cypher and validate model-supplied arguments with Valibot. The model cannot provide arbitrary Cypher, credentials, or a database name.

## Neo4j MCP Agent

Flue connects to MCP servers over HTTP. A local MCP server works when it exposes an HTTP endpoint; Flue does not spawn a local stdio server from `command` and `args`.

Start the official Neo4j MCP server in HTTP mode:

```bash
NEO4J_URI="neo4j+s://demo.neo4jlabs.com:7687" \
NEO4J_DATABASE="companies" \
NEO4J_TRANSPORT_MODE="http" \
NEO4J_MCP_HTTP_HOST="127.0.0.1" \
NEO4J_MCP_HTTP_PORT="8000" \
NEO4J_READ_ONLY="true" \
NEO4J_TELEMETRY="false" \
uvx neo4j-mcp-server
```

The HTTP server receives `NEO4J_USERNAME` and `NEO4J_PASSWORD` from the Flue MCP request using Basic authentication.

Verify the connection without calling a model:

```bash
npm run check:mcp
```

Then run the MCP agent:

```bash
npm run mcp-agent -- \
  --id google-mcp-research \
  --message "Use the graph to research Google and its latest stored news."
```

Set `NEO4J_MCP_URL` when the MCP server is hosted somewhere other than `http://localhost:8000/mcp`.

The MCP connection exposes only:

- `mcp__neo4j__get-schema`
- `mcp__neo4j__read-cypher`

The server should also run with `NEO4J_READ_ONLY=true` and credentials restricted to read access.

## How the Integration Works

Custom tools are mounted with `useTool`:

```ts
export function IndustryResearchAgent() {
  useModel('anthropic/claude-sonnet-5');
  useTool(queryCompanyProfile);
  useTool(searchCompanyNews);

  return 'Research companies using the Neo4j tools.';
}
```

The MCP agent mounts a reusable connection with `useMcpConnection`:

```ts
export function Neo4jMcpResearchAgent() {
  useModel('anthropic/claude-sonnet-5');
  useMcpConnection(neo4jMcp);

  return 'Use the Neo4j MCP tools to answer questions about the graph.';
}
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | API key for the configured model | Required |
| `NEO4J_URI` | Neo4j connection URI | Public companies demo |
| `NEO4J_USERNAME` | Neo4j username used by both integrations | `companies` |
| `NEO4J_PASSWORD` | Neo4j password used by both integrations | `companies` |
| `NEO4J_DATABASE` | Neo4j database | `companies` |
| `NEO4J_MCP_URL` | Optional Neo4j MCP HTTP endpoint | `http://localhost:8000/mcp` |

## Validation

```bash
npm run typecheck
npm test
```

With the MCP server running:

```bash
npm run check:mcp
```

## Current Scope

- The direct agent provides two exact-name, read-only queries.
- The MCP agent allows broader read-only Cypher generated from the discovered schema.
- The demo graph is historical; "recent" means the newest article stored in the graph.
- Vector search, deployment, and multi-agent orchestration are not included.

## Resources

- [Flue Agents](https://flueframework.com/docs/guide/building-agents/)
- [Flue Tools](https://flueframework.com/docs/guide/tools/)
- [Flue MCP](https://flueframework.com/docs/guide/mcp/)
- [Neo4j JavaScript Driver](https://neo4j.com/docs/javascript-manual/current/)
- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Neo4j MCP Documentation](https://neo4j.com/docs/mcp/current/)
