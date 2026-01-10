# LangChain + Neo4j Integration

## Overview

**LangChain** is a comprehensive framework for building LLM applications with extensive tool/chain ecosystem and modular components.

**Key Features:**
- Extensive tool ecosystem
- Memory integrations
- Retrieval (RAG)
- Neo4j vector and graph integrations (mature)
- Modular components
- MCP support via adapters

**Official Resources:**
- Website: https://www.langchain.com
- Documentation: https://python.langchain.com/docs/
- Neo4j Integration: https://python.langchain.com/docs/integrations/providers/neo4j
- MCP Adapters: https://github.com/langchain-ai/langchain-mcp-adapters

## Extension Points

### 1. Native Neo4j Integrations

```python
from langchain_neo4j import Neo4jGraph, Neo4jVector, GraphCypherQAChain
from langchain_openai import OpenAIEmbeddings

# Graph queries
graph = Neo4jGraph(
    url="bolt://demo.neo4jlabs.com:7687",
    username="companies",
    password="companies",
    database="companies"
)

# Vector search
vector_store = Neo4jVector.from_existing_index(
    OpenAIEmbeddings(),
    url="bolt://demo.neo4jlabs.com:7687",
    username="companies",
    password="companies",
    index_name="article_embeddings"
)

# Cypher QA chain
cypher_chain = GraphCypherQAChain.from_llm(
    llm=ChatOpenAI(model="gpt-4"),
    graph=graph
)
```

### 2. MCP Integration

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "neo4j": {
        "transport": "streamable_http",
        "url": "http://localhost:8000/mcp",
        "headers": {"Authorization": "Bearer YOUR_TOKEN"}
    }
})

tools = client.as_tools()
```

## MCP Authentication

✅ **API Keys** - Via custom headers

➖ **Client Credentials** - Via custom headers (not built-in)

❌ **M2M OIDC** - No specific support

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#8-langchain--langgraph)

## Industry Research Agent Example

```python
from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph
from langchain.tools import tool

# Neo4j setup
graph = Neo4jGraph(
    url="bolt://demo.neo4jlabs.com:7687",
    username="companies",
    password="companies",
    database="companies"
)

@tool
def query_company(company_name: str) -> dict:
    """Query company information from Neo4j."""
    result = graph.query("""
        MATCH (o:Organization {name: $name})
        OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc:Location)
        OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind:Industry)
        RETURN o.name as name,
               collect(DISTINCT loc.name) as locations,
               collect(DISTINCT ind.name) as industries
        LIMIT 1
    """, params={"name": company_name})
    return result[0] if result else {}

@tool
def search_news(company_name: str) -> list:
    """Search news articles about a company."""
    result = graph.query("""
        MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
        RETURN a.title, a.date
        ORDER BY a.date DESC
        LIMIT 5
    """, params={"company": company_name})
    return result

# Create agent
llm = ChatOpenAI(model="gpt-4")
tools = [query_company, search_news]

agent = create_react_agent(llm, tools, prompt_template)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Execute
result = agent_executor.invoke({
    "input": "Research Google's organizational structure and recent news"
})
```

## Resources

- **LangChain Docs**: https://python.langchain.com/docs/
- **Neo4j Integration**: https://python.langchain.com/docs/integrations/providers/neo4j
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Mature Neo4j integrations
- ✅ MCP via adapters
- ⚠️ Auth requires custom implementation
- **Effort Score**: 3.9/10
- **Impact Score**: 5.8/10
