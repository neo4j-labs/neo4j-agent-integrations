# Creating the Agent in the Console

The connection, MCP toolkit and Python tool are all created by the CLI
(`make all`). Only the agent itself is created in the console, because of the
CLI limitation described in [known-issues.md](known-issues.md#1-cli-import-of-a-native-agent-with-a-toolkit-fails).

Field values below come from [`agents/neo4j_explorer.yaml`](../agents/neo4j_explorer.yaml).

## Steps

1. Open the Orchestrate console and go to **Build -> Agent Builder**.
2. Choose **Create agent -> Create from scratch**.
   (Templates and LangGraph import are also offered here.)
3. Set the fields:

   | Field | Value |
   |---|---|
   | Name | `neo4j_explorer` |
   | Description | Answers questions about companies, people, and investments using a Neo4j knowledge graph. |
   | Model | `bedrock/openai.gpt-oss-120b-1:0` |
   | Style | Default |

4. Paste the `instructions` block from the YAML file into **Instructions**.
5. Open **Toolset -> Add tool + local instance** and add:
   - the tools from the `neo4j_local_mcp` toolkit (`get-schema`, `read-cypher`)
   - the `get_investments` tool
6. Save, then test in the preview chat (draft).
7. **Deploy** to promote the agent to live. Live execution uses the *live*
   credentials of the `neo4j_local_creds` connection, so verify at least one
   query after deploying.

## Adding the MCP server through the console instead

If you prefer not to use `make mcp-toolkit`, the same server can be registered
from the UI: **Toolset -> Add tool + -> Add from file or MCP server ->
Add local MCP server**.

| Field | Value |
|---|---|
| Server name | `neo4j_local_mcp` |
| Description | Neo4j companies knowledge graph: schema inspection and read-only Cypher |
| Install command | `uvx mcp-neo4j-cypher` (package `mcp-neo4j-cypher`) |
| Connection | `neo4j_local_creds` |
