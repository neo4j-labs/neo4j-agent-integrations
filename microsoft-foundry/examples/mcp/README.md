# Foundry Portal: Neo4j as an MCP Tool

Use this when you want the fastest Foundry experience: add Neo4j as an MCP tool. You can deploy the shared Neo4j MCP server for database-level graph tools, or use a Neo4j Aura Agent published as an MCP endpoint for a domain-specific graph agent.

## 1. Deploy the Shared MCP Server

```bash
cd microsoft-foundry/infra/neo4j-mcp-server
azd up
export NEO4J_MCP_ENDPOINT="$(azd env get-value mcpEndpoint)"
./test-mcp.sh "$NEO4J_MCP_ENDPOINT"
```

## 2. Add It in Foundry

In the Foundry portal:

1. Open your Foundry project.
2. Create or open an agent.
3. Add a tool of type **Model Context Protocol (MCP)**.
4. Set the server URL to `https://<container-app-fqdn>/mcp`.
5. Use key/header authentication.
6. Header name: `Authorization`.
7. Header value: `Basic <base64(username:password)>`.
8. Allow only `get-schema` and `read-cypher` for demos.

For the demo database:

```bash
printf '%s:%s' companies companies | base64
```

## Smoke Test by Script

The script creates the same project connection and a temporary agent through the Foundry APIs. It is useful for CI or validating the portal setup.

```bash
export NEO4J_MCP_ENDPOINT="https://<container-app-fqdn>/mcp"
export FOUNDRY_LOCATION="northcentralus"
export FOUNDRY_RESOURCE_GROUP="<foundry-resource-group>"
export FOUNDRY_ACCOUNT_NAME="<foundry-ai-services-account>"
export FOUNDRY_PROJECT_NAME="<foundry-project>"
export FOUNDRY_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"

cd microsoft-foundry/examples/mcp
./foundry-mcp-smoke-test.sh
```

You can also copy `.env.sample` to `.env` in this folder and run the script without exporting each value.

Expected result: Foundry calls `read-cypher` and returns five organization names from the Neo4j `companies` demo graph.

## Coming Soon

- Portal screenshots for the Foundry tool setup.
- Bearer token and APIM/OAuth gateway variants for enterprise auth.
- Aura Agent MCP variant for domain-specific graph agents.
