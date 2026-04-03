# 1. Databricks Custom MCP server (Neo4j via Databricks App)

## Introduction

This guide demonstrates how to create a **Custom Neo4j MCP Server** using **Databricks Apps**.

This setup allows you to define **MCP Tools** that perform queries on a remote Neo4j instance, directly from Databricks apps and without using a dedicated Neo4j MCP server.  

By following this guide, you can expose Neo4j based MCP Tools and interact with them using the Databricks Agent capabilities, enabling integration with LLM agents or other workflows.

The example shows a simple MCP Server implementation that returns the competitors for a given company name.

---

## Preliminary Notes

This integration pattern fits really well when you need to create MCP Servers that exploits Neo4j queries alongside Rest APIs and/or Databricks SQL Warehouse queries.
If you need Neo4j MCP Server with full capabilities (chat memory, etc...) we advice you to see to the OFFICIAL_MCP_SERVER example.

---

## Architecture Overview

-> Databricks Agent / Playground

-> Databricks App defined upon Custom MCP Server Tools

-> Neo4j Driver connection

-> Neo4j Database (e.g., demo.neo4jlabs.com / companies dataset)

## Key points:

- The Custom Python MCP Server encapsulate the query logic and handle the connection to Neo4j.
- The Databricks App is synced with the server.
- The LLM or agent interacts with the MCP Tools.
- The Neo4j connection is secured using SSL.

## Advantages

- Low Code & Low infrastructure (Databricks App).
- Fast Prototyping (Local Tests).
- Allows for Complex MCP definition.
- Automatic permission inheritance.
- Credentials hided behind Databricks secrets.
- Schema-level exposure (multiple functions → multiple tools).
- Works in Playground immediately.

## Limitations

- Python only.
- Neo4j MCP Server capabilities are limited.

## Prerequisites

- Databricks Subscription with Compute capabilities.
- Databricks CLI installed on your PC.

## Implementation

### Step 1 - Setup the environment

The first thing to do is to define the Databricks secrets for the Neo4j credentials. It is possible to define an env file and a script to automate the process.

.env
``` 
NEO4J_BOLT_URL=bolt+ssc://<your-neo4j>:7687
NEO4J_USERNAME=
NEO4J_PASSWORD=
```

setup_secrets.sh
``` sh
#!/bin/bash

set -e

SCOPE="neo4j-agent"

auth=$(databricks current-user me)
if [[ $auth != *'"active":true'* ]]; then
  echo "❌ Databricks CLI unauthenticated."
  echo ""
  echo "You must login first:"
  echo "databricks auth login --host https://<your-databricks-workspace>"
  echo ""
  exit 1
fi

echo "✅ Databricks CLI authenticated"

# ---- load .env ----
if [ ! -f .env ]; then
  echo "❌ File .env not found. Please create one with the necessary environment variables."
  exit 1
fi

set -o allexport
source .env
set +o allexport

# ---- create scope ----
echo "Creating scope (if not exists)..."
databricks secrets create-scope $SCOPE >/dev/null 2>&1 || echo "Scope already exists, skipping creation."

# ---- upload secrets ----
echo "Uploading secrets..."

databricks secrets put-secret $SCOPE bolt-url \
  --string-value "$NEO4J_BOLT_URL"

databricks secrets put-secret $SCOPE username \
  --string-value "$NEO4J_USERNAME"

databricks secrets put-secret $SCOPE password \
  --string-value "$NEO4J_PASSWORD"

echo "✅ Secrets uploaded successfully"
```

After running the script in the terminal, the secrets will be stored in the Databricks environment.

### Step 2 - Implement the MCP Server

In this guide, the MCP Server is kept as simple as possible but you can easly extend it.

#### Project Structure

```
custom_mcp_server
└───app
   │   app.py
   │   app.yaml
   │   requirements.txt
```

First we define a YAML file that will instruct the Databricks App to bind Databricks Secrets to Environment Variables.

app.env
``` yaml
env:
  - name: NEO4J_URI
    valueFrom: bolt-url

  - name: NEO4J_USER
    valueFrom: username

  - name: NEO4J_PASS
    valueFrom: password
```
Second we define the Python requirements file.

requirements.txt
``` txt
uvicorn==0.41.0
neo4j==6.1.0
mcp==1.26.0
fastapi==0.135.1
```
Finally we implement the Python MCP Server

app.py
``` py
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from fastapi import FastAPI
from fastapi.responses import FileResponse
from neo4j import GraphDatabase, RoutingControl, bearer_auth
import uvicorn

# Get the Env Variables - Secrets
try:
    URI = os.getenv("NEO4J_URI") 
    NEO4J_USER = os.getenv("NEO4J_USER") 
    NEO4J_PASS = os.getenv("NEO4J_PASS") 
except Exception as e:
    print(f"Warning: Secrets not found ({e}). Check that the application has been configured to access the necessary secrets, that the resource keys are correctly set and that the app.yaml is properly configured to map the resource keys into environment variables.")
    # Fallback for local tests
    URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASS = os.getenv("NEO4J_PASS", "password")

mcp = FastMCP("Custom MCP Server on Databricks App using Neo4j against companies database")
AUTH = (NEO4J_USER, NEO4J_PASS)

# mcp tool using Neo4j driver to find competitors for a given company
@mcp.tool()
def find_competitors(company_name: str, limit: int) -> list[dict]:
    """Find competitors for a given company"""

    cypher_query = f"""
        MATCH (c:Organization {{name: $company_name}})-[:HAS_COMPETITOR]->(competitor:Organization)
        RETURN competitor.name as name, competitor.revenue as revenue
        LIMIT $limit
        """

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        records, _, _ = driver.execute_query(
            cypher_query, 
            parameters_={"company_name": company_name, "limit": limit},
            database_="companies", 
            routing_=RoutingControl.READ,
        )
        return records

# define more tools as needed
# @mcp.tool()
# def get_employees_count(...

mcp_app = mcp.streamable_http_app()

app = FastAPI(
    lifespan=lambda _: mcp.session_manager.run(),
)

# Add a landing page if needed
@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(Path(__file__).parent / "index.html")

app.mount("/", mcp_app)

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True, # Useful in Test, remove in Production
    )
```

We can also test the server locally using a client as follows.

client.py
``` py
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import asyncio

async def main():
    app_url = "http://localhost:8000/mcp/"
    async with streamable_http_client(app_url) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.call_tool("find_competitors", {"company_name": "BigFix", "limit": 5})
            print(tool_result)  
            
if __name__ == "__main__":
    asyncio.run(main())
```

### Step 3 - Create the Databricks App

Now we can create the Databricks App that will use our custom Python MCP Server.

Open a terminal in the root of your custom-mcp-server folder and run the command to create the Databricks app.

**It is important that the app name starts with "mcp-", otherwise Databricks will not be able to treat it as an MCP**
```
databricks apps create mcp-<app_name>
```
Then we sync our code with the Databricks app and we deploy/start the app.

```
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks sync . "/Users/$DATABRICKS_USERNAME/mcp-<app-name>"
databricks apps deploy mcp-<app_name> --source-code-path "/Workspace/Users/$DATABRICKS_USERNAME/mcp-custom-server"
```

Check your Workspace to review the app name and the synced files.

The App is associated with a Service Principal, be sure that it has the grants to read secrets.

### Step 4 - Pass secrets to the App

Go to Compute -> Apps (Tab)

Check the Logs to ensure that the app is serving correctly and that the Python requirements have been installed, then click on Edit (screenshot)

![Logs & Edit](screenshots/app1.png)

In the third tab, link your Secrets to unique Resource Keys as follows.

![Secrets & Resource Keys](screenshots/app2.png)

Then scroll down to save the configuration and restart the App.

## Test & Use

### Playground

In the `Playground` select the custom MCP Server from `Tools -> Add Tool -> MCP Servers (Tab)`, add a System Prompt like the following and start asking your first question: `What are the competitors of BigFix?`

```
Purpose: Assist users in getting companies/organizations info.

Limitations:
- Focus on companies.
- Be conversational but do not answer any unrelated queries that are not related to companies.
- Handle queries for multiple companies.
- If there is no company information, do not attempt to retrieve otherwise – inform the user with an appropriate error message.

Parameters:
- Company name
- Max results

Data Sources:
- Use the find_competitors API tool when requested with questions about company's competitors.

Actions:
1. Retrieve company info
2. Retrieve competitors

Error Handling:
- Provide clear error messages if Neo4j Connection calls fail.

Sample Questions:
- "What are the competitors of 'BigFix'?"
```

The LLM will use the MCP Server to retrieve the information from Neo4j and it will prompt the natural language response.
If the Model states that it cannot use the MCP Server try to switch to another model as Claude Opus 4.6

![Playground Results](screenshots/playground1.png)

Note: it is possible to use many Tools coming from different source at the same time (External MCPs, UC Functions, etc...) , giving you the possibility to create more complex agents.

Now that we tested the Agent capabilities, we are ready to use it.

### External use of the Databricks App

From Compute -> Apps you will find the public url associated with your app, alternatively, select your App, in the Status you will find the public url as well.

Now, to integrate the app in your code project, or share it with your team, you need a databricks token and a Client (e.g. Cloude).

```
databricks auth token -p <your-profile>
```

Here an example of a simple Python client with Workspace authentication.

client.py
``` py
from databricks.sdk import WorkspaceClient
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession
import asyncio

client = WorkspaceClient()

async def main():
    headers = client.config.authenticate()
    app_url = "https://your.app.url.databricksapps.com/mcp/"
    async with streamable_http_client(app_url,  headers=headers) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.call_tool("find_competitors", {"company_name": "BigFix", "limit": 5})
            print(tool_result)  
            
if __name__ == "__main__":
    asyncio.run(main())
```

You can also publish your App into the Databricks Marketplace.





