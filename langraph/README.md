# LangGraph + Neo4j Integration

## Overview

**LangGraph** is a stateful, graph-based agent framework from LangChain Inc. that enables building production-ready multi-agent systems with durable execution and human-in-the-loop capabilities.

**Key Features:**
- Stateful graph-based agent orchestration
- Memory (short-term + long-term)
- Observability via LangSmith
- Production deployment with LangGraph Cloud
- Used by Klarna, Replit, Elastic

**Official Resources:**
- Website: https://www.langchain.com/langgraph
- Documentation: https://langchain-ai.github.io/langgraph/
- MCP Integration: https://docs.langchain.com/oss/python/langchain/mcp

## Extension Points

### 1. MCP Integration (Primary)

LangGraph supports MCP via the `langchain-mcp-adapters` package:

**Installation:**
```bash
pip install langchain-mcp-adapters
```

**MCP Client Setup:**
```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "neo4j": {
        "transport": "streamable_http",  # or "sse" or "stdio"
        "url": "http://localhost:8000/mcp",
        "headers": {
            "Authorization": "Bearer YOUR_TOKEN",
        },
    }
})
```

### 2. Neo4j Vector and Graph Integrations

LangGraph inherits LangChain's Neo4j integrations:

- **Neo4jVector**: Vector similarity search
- **Neo4jGraph**: Graph database queries and retrieval
- **GraphCypherQAChain**: Natural language to Cypher
- **Memory Stores**: Using Neo4j as persistent memory backend

### 3. Custom Tools

Define custom Python functions as LangGraph tools for graph operations.

## MCP Authentication

**Supported Mechanisms:**

✅ **API Keys** - Via custom headers
```python
headers={"Authorization": "Bearer YOUR_TOKEN"}
```

➖ **Client Credentials** - Can be passed via custom headers (not built-in)

❌ **M2M OIDC** - No specific OIDC support (OAuth tokens can be passed as bearer tokens)

**Other Mechanisms:**
- **LangSmith Authentication**: For LangGraph Cloud deployments
- **Custom Headers**: Primary method for remote MCP servers
- **Environment Variables**: For stdio servers
- **Interceptors**: For injecting user context into tool calls

**Configuration Pattern with Interceptors:**
```python
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

async def inject_user_context(request: MCPToolCallRequest, handler):
    """Inject user credentials into MCP tool calls."""
    modified_request = request.override(
        args={**request.args, "api_key": runtime.context.api_key}
    )
    return await handler(modified_request)

client = MultiServerMCPClient(
    {...},
    tool_interceptors=[inject_user_context],
)
```

**Key Limitations:**
- Headers only supported for SSE and HTTP transports
- No built-in OAuth flow management
- Authentication is passed through, not managed
- stdio servers use environment variables only

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#8-langchain--langgraph)

## Industry Research Agent Example

### Scenario

Build a multi-agent system for investment research that:
1. Queries the Company News Knowledge Graph for organizational data
2. Performs vector search over news articles
3. Analyzes investor relationships
4. Synthesizes research reports

### Dataset Setup

**Company News Knowledge Graph (Read-Only Access):**
```python
NEO4J_URI = "neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_USERNAME = "companies"
NEO4J_PASSWORD = "companies"
NEO4J_DATABASE = "companies"
```

**Data Model:**
- Organizations with locations, industries
- Leadership (People → Organization)
- News articles with vector embeddings
- 250k entities from Diffbot Knowledge Graph

### Implementation

```python
from langgraph.graph import StateGraph, MessagesState
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph, Neo4jVector

# Initialize Neo4j connections
graph = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE
)

# Initialize MCP client for Neo4j MCP server
mcp_client = MultiServerMCPClient({
    "neo4j": {
        "transport": "streamable_http",
        "url": "https://your-neo4j-mcp-server.com/mcp",
        "headers": {
            "Authorization": f"Bearer {YOUR_MCP_TOKEN}",
        },
    }
})

# Convert MCP tools to LangChain tools
neo4j_tools = mcp_client.as_tools()

# Define agent state
class ResearchState(MessagesState):
    company_data: dict
    news_analysis: list
    research_report: str

# Define research workflow nodes
def query_company_data(state: ResearchState):
    """Query organization data from Neo4j."""
    # Use MCP tools or direct Neo4j queries
    result = graph.query("""
        MATCH (o:Organization {name: $company_name})
        OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc:Location)
        OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind:Industry)
        OPTIONAL MATCH (p:Person)-[:WORKS_FOR]->(o)
        RETURN o, collect(DISTINCT loc.name) as locations,
               collect(DISTINCT ind.name) as industries,
               collect({name: p.name, title: p.title}) as leadership
        LIMIT 1
    """, params={"company_name": state.company_name})
    return {"company_data": result}

def analyze_news(state: ResearchState):
    """Perform vector search over news articles."""
    vector_store = Neo4jVector.from_existing_index(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE,
        index_name="article_chunks",
        embedding=your_embedding_model
    )

    docs = vector_store.similarity_search(
        f"Recent news about {state.company_data['name']}",
        k=5
    )
    return {"news_analysis": docs}

def generate_report(state: ResearchState):
    """Synthesize research report using LLM."""
    llm = ChatOpenAI(model="gpt-4")

    prompt = f"""
    Based on the following data, generate an investment research report:

    Company Data: {state.company_data}
    Recent News: {state.news_analysis}
    """

    report = llm.invoke(prompt)
    return {"research_report": report.content}

# Build the graph
workflow = StateGraph(ResearchState)
workflow.add_node("query_company", query_company_data)
workflow.add_node("analyze_news", analyze_news)
workflow.add_node("generate_report", generate_report)

workflow.set_entry_point("query_company")
workflow.add_edge("query_company", "analyze_news")
workflow.add_edge("analyze_news", "generate_report")

# Compile the graph
app = workflow.compile()

# Run the research agent
result = app.invoke({
    "company_name": "Google",
    "messages": []
})
```

### Multi-Agent Pattern

For a more sophisticated setup with multiple specialized agents:

```python
# Database Agent - handles all Neo4j queries
database_agent = create_react_agent(
    llm=ChatOpenAI(model="gpt-4"),
    tools=neo4j_tools,  # From MCP
    state_modifier="You are a database expert. Query Neo4j for information."
)

# Research Analyst Agent - synthesizes information
analyst_agent = create_react_agent(
    llm=ChatOpenAI(model="gpt-4"),
    tools=[],
    state_modifier="You are an investment analyst. Synthesize data into insights."
)

# Supervisor Agent - orchestrates workflow
supervisor_agent = create_react_agent(
    llm=ChatOpenAI(model="gpt-4"),
    tools=[database_agent, analyst_agent],
    state_modifier="You coordinate research tasks between agents."
)
```

## Challenges and Gaps

### Current Limitations

1. **MCP Authentication Management**
   - No built-in OAuth flow handling
   - Manual token management required
   - Need custom interceptors for dynamic credentials

2. **State Persistence**
   - While LangGraph has checkpointing, integrating Neo4j as the state backend requires custom implementation
   - No out-of-the-box Neo4j checkpointer

3. **Observability**
   - LangSmith is the primary observability tool
   - Neo4j query tracing requires custom instrumentation

4. **Error Handling**
   - MCP connection errors need custom retry logic
   - No automatic fallback mechanisms

### Workarounds

**For OAuth Token Refresh:**
```python
import time
from functools import wraps

def with_token_refresh(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check token expiration and refresh
        if token_expired():
            await refresh_oauth_token()
        return await func(*args, **kwargs)
    return wrapper
```

**For Neo4j State Persistence:**
```python
from langgraph.checkpoint.base import BaseCheckpointSaver

class Neo4jCheckpointSaver(BaseCheckpointSaver):
    """Custom checkpointer using Neo4j as backend."""
    # Implement save_checkpoint, load_checkpoint methods
    pass
```

## Additional Integration Opportunities

### 1. Context Graph / Agent Memory

Use Neo4j as the memory layer for LangGraph agents:
- Store conversation history as graph structures
- Track entity relationships across conversations
- Enable semantic memory retrieval

### 2. LangGraph Studio Integration

Develop custom visualizations for Neo4j queries in LangGraph Studio.

### 3. Retrieval Strategy Optimization

Implement hybrid retrieval combining:
- Vector similarity (articles)
- Graph traversal (relationships)
- Cypher queries (structured data)

### 4. Production Deployment Patterns

- Deploy Neo4j MCP server on Cloud Run / Lambda
- Use LangGraph Cloud for agent deployment
- Implement monitoring and alerting

## Code Examples

See the `examples/` directory for:
- `basic_mcp_integration.py` - Simple MCP setup
- `research_agent.py` - Full industry research agent
- `multi_agent_system.py` - Multi-agent orchestration
- `memory_integration.py` - Neo4j as memory backend

## Resources

- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **MCP Adapters**: https://github.com/langchain-ai/langchain-mcp-adapters
- **Neo4j LangChain**: https://python.langchain.com/docs/integrations/providers/neo4j
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ MCP integration available via langchain-mcp-adapters
- ✅ Neo4j vector and graph integrations mature
- ⚠️ OAuth management requires custom implementation
- ⚠️ Neo4j state persistence needs custom checkpointer
- 🔄 Active development and community support
