# OpenAI Agents SDK + Neo4j Integration

## Overview

**OpenAI Agents SDK** provides production-grade agents with built-in evaluations and monitoring. Native MCP support with hosted MCP infrastructure.

**Key Features:**
- Memory (threads)
- Built-in evaluations
- Monitoring and observability
- Native MCP support
- Hosted MCP infrastructure
- ChatGPT Apps SDK built on MCP

**Official Resources:**
- Documentation: https://platform.openai.com/docs/guides/agents
- MCP Guide: https://openai.github.io/openai-agents-python/mcp/
- Python SDK: https://github.com/openai/openai-python

## Extension Points

### 1. Hosted MCP (Recommended)

```python
from openai_agents import HostedMCPTool

tool = HostedMCPTool(
    tool_config={
        "type": "mcp",
        "server_label": "neo4j_research",
        "connector_id": "connector_neo4j",
        "authorization": os.environ["NEO4J_MCP_AUTHORIZATION"],
        "require_approval": "never"
    }
)
```

### 2. Self-Hosted MCP

```python
from openai_agents import MCPServerStreamableHttp

async with MCPServerStreamableHttp(
    name="Neo4j Research",
    params={
        "url": "https://your-neo4j-mcp-server.com/mcp",
        "headers": {"Authorization": f"Bearer {YOUR_TOKEN}"}
    }
) as server:
    tools = await server.list_tools()
```

### 3. Direct Integration

```python
from openai import OpenAI
from neo4j import GraphDatabase

client = OpenAI()
driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

def query_company(company_name: str) -> dict:
    query = """
        MATCH (o:Organization {name: $company})
        RETURN o.name as name,
               [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
               [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries
        LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        database_="companies"
    )
    return records[0].data() if records else {}

# Use with function calling
assistant = client.beta.assistants.create(
    model="gpt-4-turbo",
    tools=[{
        "type": "function",
        "function": {
            "name": "query_company",
            "description": "Query company information from Neo4j",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"}
                },
                "required": ["company_name"]
            }
        }
    }]
)
```

## MCP Authentication

✅ **API Keys** - Headers for MCP server connections

✅ **Connector OAuth** - For hosted MCP

✅ **OAuth flows** - For hosted MCP via connectors

**Example:**
```python
headers = {"Authorization": "Bearer YOUR_TOKEN"}
```

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#3-openai-chatgpt-agents-sdk-codex)

## Industry Research Agent Example

```python
from openai import OpenAI
import json

client = OpenAI()

# Define tools
tools = [{
    "type": "function",
    "function": {
        "name": "query_company",
        "description": "Query company information from Neo4j",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"}
            }
        }
    }
}, {
    "type": "function",
    "function": {
        "name": "search_news",
        "description": "Search news articles about a company",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            }
        }
    }
}]

# Create assistant
assistant = client.beta.assistants.create(
    name="Investment Researcher",
    instructions="""You research companies using Neo4j data.
    Use query_company to get organizational details.
    Use search_news to find recent articles.
    Synthesize into investment research reports.""",
    model="gpt-4-turbo",
    tools=tools
)

# Create thread and run
thread = client.beta.threads.create()
message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content="Research Google and provide an investment report"
)

run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant.id
)

# Handle tool calls
while run.status in ["queued", "in_progress", "requires_action"]:
    if run.status == "requires_action":
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []

        for tool_call in tool_calls:
            if tool_call.function.name == "query_company":
                args = json.loads(tool_call.function.arguments)
                output = query_company(args["company_name"])
                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(output)
                })
            elif tool_call.function.name == "search_news":
                args = json.loads(tool_call.function.arguments)
                output = search_news(args["company_name"])
                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(output)
                })

        run = client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread.id,
            run_id=run.id,
            tool_outputs=tool_outputs
        )

    run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

# Get results
messages = client.beta.threads.messages.list(thread_id=thread.id)
print(messages.data[0].content[0].text.value)
```

## Resources

- **OpenAI Agents**: https://platform.openai.com/docs/guides/agents
- **MCP Guide**: https://openai.github.io/openai-agents-python/mcp/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Native MCP support
- ✅ Hosted MCP infrastructure
- ✅ Built-in evaluations
- **Effort Score**: 4.8/10
- **Impact Score**: 6.3/10
