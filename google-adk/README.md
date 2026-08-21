# Google ADK + Neo4j MCP Integration

## Overview

**Google ADK** (Agent Development Kit) is a powerful framework for building generative AI agents. This integration repository demonstrates how to build context-aware, enterprise-grade agents by connecting Google ADK to Neo4j using four distinct patterns:


**1. Operational Database Access (via MCP):** Allows the agent to query, introspect, and interact with your primary Neo4j knowledge graph using the [Neo4j MCP server](https://neo4j.com/docs/mcp/current/).  
**2. Persistent Agent Memory (via ADK MemoryService):** Equips the agent with stateful, long-term memory using `neo4j-agent-memory`, automatically extracting and storing conversational facts and entities into a dedicated Neo4j memory graph.  
**3. Managed Agent Memory (via NAMS):** Offloads memory infrastructure entirely using the cloud-managed [Neo4j Agent Memory Service (NAMS)](https://memory.neo4jlabs.com/docs), accessible via REST API or directly as an MCP tool.  
**4. Semantic Retrieval (via neo4j-graphrag):** Gives the agent vector, full-text, and hybrid search over unstructured content in the graph using [`neo4j-graphrag`](https://neo4j.com/docs/neo4j-graphrag-python/current/), with retrievers exposed as ADK tools.  

Examples target **ADK 2.0**, which introduces graph-based workflows alongside the conversational agent model.

## Key Features  


**Standardized Tooling:** Connect Google ADK agents to Neo4j securely via the Model Context Protocol (MCP).  
**Graph Introspection:** Allow agents to autonomously discover graph schemas and execute Cypher queries.  
**Deterministic Workflows:** Use ADK 2.0 `Workflow` graphs to put generated Cypher through validation and routing that the model cannot skip.  
**GraphRAG Retrieval:** Combine vector similarity with graph traversal so retrieved text arrives with the surrounding relationships, dates, and verifiable source IDs.  
**Stateful Conversations:** Utilize Neo4j as a persistent memory layer to cure LLM "context amnesia."  
**Multi-Stage Extraction:** Automatically extract entities, facts, and user preferences from conversations into a structured knowledge graph.  


---

## Installation

To run the full architecture (MCP + Memory), install the following dependencies:

```bash
pip install "google-adk>=2.0.0" neo4j-mcp-server "neo4j-agent-memory[google-adk,vertex-ai]" spacy
python -m spacy download en_core_web_sm
```

For the GraphRAG retrieval examples:

```bash
pip install "google-adk>=2.0.0" neo4j-graphrag sentence-transformers
```

## Configuration & Authentication  
This architecture typically utilizes two Neo4j databases: your target data graph and your agent memory graph. 
  
**1. Target Database (MCP Server)**  
Here we have used "http" transport mode:  
• **HTTP Headers (HTTP mode):** Pass credentials via HTTP headers (e.g., Authorization: Basic <base64_encoded_credentials>), or `Authorization: Bearer <token>` for Aura/Enterprise instances behind SSO.  

Configure the server with environment variables:

```bash
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_DATABASE=neo4j
NEO4J_TRANSPORT_MODE=http
NEO4J_MCP_HTTP_HOST=127.0.0.1
NEO4J_MCP_HTTP_PORT=8443
NEO4J_READ_ONLY=true          # write-cypher is not advertised to clients
```

> **Note:** In HTTP mode the server is stateless and rejects `NEO4J_USERNAME` / `NEO4J_PASSWORD` at startup — credentials arrive per request in the auth header. Set them only in STDIO mode. Also note the `NEO4J_MCP_` prefix on the host and port variables; without it the server binds its default privileged port and fails to start.

For other authentication methods refer [here](https://neo4j.com/docs/mcp/current/authentication/)
  
**2. Memory Database**  
Set your memory graph credentials and Google Cloud project details for the Vertex AI embedder:
```bash
# Memory Graph
MEMORY_NEO4J_URI=neo4j+s://your-memory-instance.databases.neo4j.io
MEMORY_NEO4J_USERNAME=neo4j
MEMORY_NEO4J_PASSWORD=your-password
MEMORY_NEO4J_DATABASE=neo4j

# Google Cloud Settings (Required for Vector Embeddings)
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us-central1
```

Vertex AI embeddings need a quota project attached to your credentials, or every embedding call fails with a 403:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud services enable aiplatform.googleapis.com --project YOUR_PROJECT_ID
```

## Quick Start & Core Snippets
The following snippets illustrate the core concepts of connecting an ADK agent to Neo4j. For a complete, runnable example, see the Example Notebook below.  

**1. Connecting the MCP Toolset**  
To allow your ADK agent to query Neo4j, initialize the MCP server and bind it to an ADK McpToolset. Here, we use HTTP mode for persistent background execution.  
```python
import base64
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

# Create HTTP Basic Auth header
credentials = base64.b64encode(b"username:password").decode()

# Bind the running MCP Server to Google ADK
mcp_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="http://localhost:8443/mcp",
        headers={"Authorization": f"Basic {credentials}"}
    ),
    # Allow-list the tools the agent may see. Pairs with NEO4J_READ_ONLY
    # on the server, and shortens the tool schema sent with every prompt.
    tool_filter=["get-schema", "read-cypher"],
)
```

**2. Initializing the Agent with Persistent Memory**  
To give the agent long-term context, initialize the Neo4j MemoryClient and provide the agent with the PreloadMemoryTool. The agent is wrapped in an `App`, the ADK 2.0 container that carries plugins and runtime configuration.  

```python
from google.adk import Agent
from google.adk.apps import App
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.config.settings import Neo4jConfig, ExtractionConfig, ExtractorType

# 1. Configure the Memory Graph Connection
settings = MemorySettings(
    neo4j=Neo4jConfig(
        uri="neo4j+s://memory-instance...",
        username="neo4j",
        password="password"
    ),
    extraction=ExtractionConfig(extractor_type=ExtractorType.SPACY)
)
memory_client = MemoryClient(settings)
await memory_client.connect()

# 2. Construct the Agent
agent = Agent(
    model="gemini-3-flash",
    name="neo4j_explorer",
    instruction="You are a helpful graph database assistant.",
    tools=[mcp_tools, PreloadMemoryTool()]  # Combine MCP capabilities with Memory recall
)

# 3. Wrap it in an App. ReflectAndRetryToolPlugin feeds tool errors back to the
#    model, which lets it correct Cypher that references a wrong label or property.
app = App(
    name="neo4j_app",
    root_agent=agent,
    plugins=[ReflectAndRetryToolPlugin(max_retries=3)],
)
```

**3. Executing with Stateful Memory Tracking**
Inject the Neo4jMemoryService into the Google ADK Runner. This ensures that every conversation is automatically synced to your Neo4j memory graph in the background.  

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from neo4j_agent_memory.integrations.google_adk import Neo4jMemoryService

session_service = InMemorySessionService()
session = await session_service.create_session(state={}, app_name=app.name, user_id="user_1")

# Initialize the ADK-compliant Memory Service
neo4j_memory_service = Neo4jMemoryService(
    memory_client=memory_client,
    user_id="user_1",
)

# Attach the memory service to the Runner. In ADK 2.0 the Runner takes the App container.
runner = Runner(
    app=app,
    session_service=session_service,
    memory_service=neo4j_memory_service
)

# Run the prompt
content = types.Content(role='user', parts=[types.Part(text="Who did Google invest in?")])
events = runner.run_async(session_id=session.id, user_id="user_1", new_message=content)

async for event in events:
    if hasattr(event, 'content') and event.content:
        for part in event.content.parts:
            if part.text:
                print(part.text)

# Save the conversational state and extracted entities back to Neo4j
fresh_session = await session_service.get_session(session_id=session.id, app_name=app.name, user_id="user_1")
await neo4j_memory_service.add_session_to_memory(fresh_session)
```

**4. Deterministic Text-to-Cypher with a Workflow**  
When a query must be validated before it runs, an ADK 2.0 `Workflow` makes the pipeline structural rather than a prompt instruction. The model writes Cypher, a function node runs `EXPLAIN` to check it without executing, and a route decides what happens next.  

```python
from google.adk import Agent, Event, Workflow

def validate(node_input: str | None = None):
    cypher = (node_input or "").strip()
    try:
        driver.execute_query(f"EXPLAIN {cypher}", database_="neo4j")
    except Exception:
        return Event(route=["INVALID"])
    return Event(route=["VALID"])

workflow = Workflow(
    name="text2cypher",
    edges=[
        ("START", cypher_writer_agent, validate),
        (validate, {"VALID": run_query, "INVALID": reject}),
    ],
)
```

> Annotate node parameters as `str | None`. A routing `Event` carries no payload, so a downstream node bound to a bare `str` receives `None` and fails input validation.

**5. GraphRAG Retrieval as an ADK Tool**  
`neo4j-graphrag` retrievers turn a question into graph results. `HybridCypherRetriever` combines vector and full-text search, then runs a `retrieval_query` that traverses outward from each match — so retrieved text arrives with its source article, date, and related entities. Wrapping the retriever in a `FunctionTool` lets the agent choose it like any other tool.  

```python
from google.adk.tools.function_tool import FunctionTool
from neo4j_graphrag.embeddings import SentenceTransformerEmbeddings
from neo4j_graphrag.retrievers import HybridCypherRetriever

# `node` and `score` are in scope: continue into the graph from each vector hit.
RETRIEVAL_QUERY = """
WITH node AS chunk, score
MATCH (article:Article)-[:HAS_CHUNK]->(chunk)
OPTIONAL MATCH (article)-[:MENTIONS]->(org:Organization)
RETURN chunk.text AS text, article.id AS article_id, article.title AS title,
       collect(DISTINCT org.name)[..5] AS companies, score
"""

retriever = HybridCypherRetriever(
    driver=driver,
    vector_index_name="news_sbert",
    fulltext_index_name="news_fulltext",
    retrieval_query=RETRIEVAL_QUERY,
    embedder=SentenceTransformerEmbeddings(),
)

def search_news(question: str) -> str:
    """Search news by meaning and return the source article and companies mentioned.

    Args:
        question: A natural-language description of what to look for.
    """
    result = retriever.search(query_text=question, top_k=5)
    return json.dumps([item.content for item in result.items])

agent = Agent(model="gemini-3-flash", name="news_analyst",
              tools=[FunctionTool(search_news)])
```

> The embedding model must match the model that built the vector index. A mismatch does not raise an error — it silently returns meaningless results. Re-embed a stored chunk and compare against its saved vector to confirm the pairing.

## Example

| Notebook | Description |
|----------|-------------|
| [google_adk.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/google-adk/google_adk.ipynb) | Walkthrough of using Google ADK with Neo4j MCP: agent setup, Cypher query execution, deterministic workflows, and utilising persistent graph memory for agent |
| [neo4j_graphrag_adk.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/google-adk/neo4j_graphrag_adk.ipynb) | Walkthrough of using `neo4j-graphrag` with Google ADK: pairing embedding models with vector indexes, vector, hybrid and graph-traversal retrievers, and exposing them as agent tools |

## Resources  
• [Neo4j MCP Server Documentation](https://neo4j.com/docs/mcp/current/)
• [Google ADK Official Documentation](https://docs.cloud.google.com/agent-builder/agent-development-kit/overview)
• [ADK 2.0 Graph Workflows](https://adk.dev/graphs/)
• [Neo4j GraphRAG for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
• [Neo4j Agent Memory](https://neo4j.com/labs/agent-memory/)
• [Neo4j Agent Memory Service (NAMS)](https://memory.neo4jlabs.com/docs)
