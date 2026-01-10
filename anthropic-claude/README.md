# Claude API (Anthropic) + Neo4j Integration

## Overview

**Claude API** from Anthropic provides native MCP support, tool use, context caching, and extended context (200K tokens). Anthropic pioneered the MCP standard.

**Official Resources:**
- Website: https://www.anthropic.com
- Documentation: https://docs.anthropic.com
- MCP Guide: https://docs.anthropic.com/en/docs/build-with-claude/mcp
- Tool Use: https://docs.anthropic.com/en/docs/build-with-claude/tool-use

## Extension Points

### 1. Tool Use with Neo4j

```python
import anthropic
from neo4j import GraphDatabase

client = anthropic.Anthropic(api_key="your-api-key")
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

tools = [{
    "name": "query_company",
    "description": "Query company information from Neo4j",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"}
        },
        "required": ["company_name"]
    }
}]

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    tools=tools,
    messages=[{
        "role": "user",
        "content": "Research Google and provide an investment report"
    }]
)

# Handle tool use
if message.stop_reason == "tool_use":
    tool_use = next(block for block in message.content if block.type == "tool_use")
    tool_result = query_company(tool_use.input["company_name"])

    # Continue conversation with tool result
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        tools=tools,
        messages=[
            {"role": "user", "content": "Research Google"},
            {"role": "assistant", "content": message.content},
            {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(tool_result)
                }]
            }
        ]
    )
```

### 2. MCP Integration

Claude Desktop and claude.ai support MCP connectors natively.

**Claude Desktop config** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "neo4j": {
      "command": "node",
      "args": ["/path/to/neo4j-mcp-server/dist/index.js"],
      "env": {
        "NEO4J_URI": "neo4j+s://demo.neo4jlabs.com:7687",
        "NEO4J_USERNAME": "companies",
        "NEO4J_PASSWORD": "companies",
        "NEO4J_DATABASE": "companies"
      }
    }
  }
}
```

### 3. Claude.ai MCP Connectors

Add MCP connectors in claude.ai:
- Projects → Add Knowledge → Connectors
- Configure Neo4j MCP server (SSE transport)

## MCP Authentication

✅ **API Keys** - Anthropic API keys (`x-api-key`)

✅ **OAuth** - For third-party providers (Google Drive, etc.)

**For MCP servers:**
- Environment variables (Claude Desktop)
- SSE with custom headers (claude.ai)

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#2-anthropic-claude-api-desktop-web-mobile)

## Industry Research Agent Example

```python
import anthropic
from neo4j import GraphDatabase
import json

client = anthropic.Anthropic()
driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

tools = [
    {
        "name": "query_company",
        "description": "Query detailed company information from Neo4j including locations, industries, and leadership",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Name of the company to query"}
            },
            "required": ["company_name"]
        }
    },
    {
        "name": "search_news",
        "description": "Search news articles mentioning a company",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["company_name"]
        }
    }
]

def process_tool_call(tool_name: str, tool_input: dict) -> str:
    if tool_name == "query_company":
        query = """
            MATCH (o:Organization {name: $company})
            RETURN o.name as name,
                   [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
                   [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries
            LIMIT 1
        """
        records, summary, keys = driver.execute_query(
            query,
            company=tool_input["company_name"],
            database_="companies"
        )
        return json.dumps(records[0].data() if records else {})

    elif tool_name == "search_news":
        query = """
            MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
            RETURN a.title as title, a.date as date
            ORDER BY a.date DESC
            LIMIT $limit
        """
        records, summary, keys = driver.execute_query(
            query,
            company=tool_input["company_name"],
            limit=tool_input.get("limit", 5),
            database_="companies"
        )
        return json.dumps([r.data() for r in records])

# Agentic loop
messages = [{
    "role": "user",
    "content": "Research Google and generate a comprehensive investment report"
}]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        tools=tools,
        messages=messages
    )

    if response.stop_reason == "end_turn":
        # Extract final text response
        final_response = next(
            (block.text for block in response.content if hasattr(block, "text")),
            None
        )
        print(final_response)
        break

    elif response.stop_reason == "tool_use":
        # Add assistant's response
        messages.append({"role": "assistant", "content": response.content})

        # Process all tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = process_tool_call(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        # Add tool results
        messages.append({"role": "user", "content": tool_results})
```

## Challenges and Gaps

1. **Token Costs** - High quality comes with higher token costs
2. **Rate Limits** - API rate limits for high-volume usage
3. **MCP Desktop** - stdio only (local), not for production deployments

## Additional Integration Opportunities

### Context Caching

Cache Neo4j schema and common queries:

```python
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=[
        {
            "type": "text",
            "text": "Neo4j schema and common patterns...",
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=messages
)
```

### Extended Context

Use 200K context window for large graph results.

## Resources

- **Claude API**: https://docs.anthropic.com
- **Tool Use**: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- **MCP**: https://docs.anthropic.com/en/docs/build-with-claude/mcp
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Native MCP support
- ✅ Pioneered MCP standard
- ✅ Advanced tool use
- ✅ 200K context, caching
- **Effort Score**: 3/10
- **Impact Score**: 6/10
