# Neo4j MCP Server on Databricks Apps

Deploy the official Neo4j MCP Server as a Databricks App, exposing Neo4j graph tools to Databricks agents and the Playground.

## Quick Start

**Prerequisites:** [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) installed and authenticated, a Neo4j instance.

```bash
# 1. Authenticate with Databricks
databricks auth login --host https://<your-databricks-workspace>

# 2. Configure Neo4j credentials
cp .env.sample .env
# Edit .env with your Neo4j URI, username, and password

# 3. Upload secrets to Databricks
./setup_secrets.sh [--profile <databricks-profile>]

# 4. Deploy the app
./deploy.py --app-name mcp-neo4j [--profile <databricks-profile>]
```

The app name **must** start with `mcp-` for Databricks to treat it as an MCP server.

After deploying, open the Databricks **Playground**, add your MCP server from **Tools > Add Tool > MCP Servers**, and start querying.

To sync file changes without a full redeploy:

```bash
./deploy.py --app-name mcp-neo4j --sync [--profile <databricks-profile>]
```

---

## Introduction

This guide demonstrates how to deploy the **Official Neo4j MCP Server** using **Databricks Apps**.

The setup allows you to use the official Neo4j MCP Tools to interact with a remote Neo4j instance directly from Databricks. By exposing Neo4j-based MCP Tools, you can integrate with LLM agents, the Databricks Playground, or other workflows.

## Architecture Overview

```
Databricks Agent / Playground
  -> Databricks App (Official MCP Server)
    -> Proxy forwarding requests to neo4j-mcp-server package
      -> Neo4j Database (e.g., demo.neo4jlabs.com / companies dataset)
```

**Key points:**
- The official `neo4j-mcp-server` Python package exposes tools to interact with Neo4j.
- A proxy is the entry point for the Databricks App, controlling requests to the MCP Server.
- The Neo4j connection is secured using SSL.
- Credentials are stored as Databricks secrets.

**Advantages:**
- No code / low infrastructure (Databricks App)
- Fast prototyping with local testing
- Automatic permission inheritance
- Schema-level exposure (multiple functions as multiple tools)
- Works in Playground immediately

**Limitations:**
- Python only

## Implementation

### Step 1 - Configure Secrets

Copy the sample env file and fill in your Neo4j credentials:

```bash
cp .env.sample .env
```

The `.env` file requires:
```
NEO4J_URI=neo4j+s://<your-neo4j>:7687
NEO4J_USERNAME=
NEO4J_PASSWORD=
```

Upload the secrets to Databricks:

```bash
./setup_secrets.sh [--profile <databricks-profile>]
```

### Step 2 - The MCP Server App

The app structure:

```
app/
  app.py                      # Uvicorn entry point / proxy
  app.yaml                    # Maps Databricks secrets to env vars
  requirements.txt            # Python dependencies
  neo4j_mcp_server_process.py # Launches and manages the MCP server process
```

- `app.yaml` binds Databricks Secrets to environment variables.
- `neo4j_mcp_server_process.py` launches the official MCP server as a subprocess.
- `app.py` is a uvicorn app that proxies requests to the MCP server process, adding authentication headers.

You can test the server locally using the provided client:

```bash
python client.py
```

### Step 3 - Deploy

Deploy using the deploy script, which uses Databricks Asset Bundles to create the app and bind secrets automatically:

```bash
./deploy.py --app-name mcp-<app_name> [--profile <databricks-profile>]
```

Check your Workspace to review the app and synced files. The App is associated with a Service Principal -- ensure it has grants to read secrets.

## Test and Use

### Playground

In the Playground, select your MCP Server from **Tools > Add Tool > MCP Servers**. Add a system prompt such as:

```
Purpose: Assist users in getting companies/organizations info.

Limitations:
- Focus on companies.
- Be conversational but do not answer unrelated queries.
- Handle queries for multiple companies.
- If there is no company information, inform the user.

Data Sources:
- Use the mcp tools you have been provided when requested with questions about companies.

Sample Questions:
- "What are the competitors of 'BigFix'?"
- "Show me the top 3 software companies by revenue"
```

If the model says it cannot use the MCP Server, try switching to another model such as Claude.

### External Use

Find the public URL for your app under **Compute > Apps** in your Databricks workspace.

To integrate the app externally, obtain a Databricks token:

```bash
databricks auth token -p <your-profile>
```

See [client_workspace.py](client_workspace.py) for a Python client example using Workspace authentication.

You can also publish your App to the Databricks Marketplace.

## Other Guides

- [Custom MCP Server](CUSTOM_MCP_SERVER.md) -- Build a custom MCP server with your own Neo4j query logic
- [UC Function Tools](UC_FUNCTION_TOOL.md) -- Expose Neo4j queries as Unity Catalog functions
