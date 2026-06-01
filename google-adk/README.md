# Google ADK + Neo4j MCP Integration

## Overview

**Google ADK** (Agent Development Kit) is a powerful framework for building generative AI agents. This integration repository demonstrates how to build context-aware, enterprise-grade agents by connecting Google ADK to Neo4j using two distinct patterns:


**1. Operational Database Access (via MCP):** Allows the agent to query, introspect, and interact with your primary Neo4j knowledge graph using the [Neo4j MCP server](https://neo4j.com/docs/mcp/current/).  
**2. Persistent Agent Memory (via ADK MemoryService):** Equips the agent with stateful, long-term memory using `neo4j-agent-memory`, automatically extracting and storing conversational facts and entities into a dedicated Neo4j memory graph.   
**3. Managed Agent Memory (via NAMS):** Offloads memory infrastructure entirely using the cloud-managed [Neo4j Agent Memory Service (NAMS)](https://memory.neo4jlabs.com/docs), accessible via REST API or directly as an MCP tool.  

## Key Features  


**Standardized Tooling:** Connect Google ADK agents to Neo4j securely via the Model Context Protocol (MCP).  
**Graph Introspection:** Allow agents to autonomously discover graph schemas and execute Cypher queries.  
**Stateful Conversations:** Utilize Neo4j as a persistent memory layer to cure LLM "context amnesia."  
**Multi-Stage Extraction:** Automatically extract entities, facts, and user preferences from conversations into a structured knowledge graph.  


---

## Installation

To run the full architecture (MCP + Memory), install the following dependencies:

```bash
pip install google-adk neo4j-mcp-server neo4j-agent-memory[google-adk,vertex-ai] spacy  
python -m spacy download en_core_web_sm
```

## Configuration & Authentication  
This architecture typically utilizes two Neo4j databases: your target data graph and your agent memory graph. 
  
**1. Target Database (MCP Server)**  
Here we have used "http" authentication modes:  
• **HTTP Headers (HTTP mode):** Pass credentials via HTTP headers (e.g., Authorization: Basic <base64_encoded_credentials>).  

for other authentication methods refer [here](https://neo4j.com/docs/mcp/current/authentication/)
  
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
    )
)
```

**2. Initializing the Agent with Persistent Memory**  
To give the agent long-term context, initialize the Neo4j MemoryClient and provide the agent with the PreloadMemoryTool.  

```python
from google.adk.agents.llm_agent import LlmAgent
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
agent = LlmAgent(
    model="gemini-flash-latest",
    name="neo4j_explorer",
    instruction="You are a helpful graph database assistant.",
    tools=[mcp_tools, PreloadMemoryTool()] # Combine MCP capabilities with Memory recall
)
```

**3. Executing with Stateful Memory Tracking**
Inject the Neo4jMemoryService into the Google ADK Runner. This ensures that every conversation is automatically synced to your Neo4j memory graph in the background.  

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.genai import types
from neo4j_agent_memory.integrations.google_adk import Neo4jMemoryService

session_service = InMemorySessionService()
session = await session_service.create_session(state={}, app_name="app", user_id="user_1")

# Initialize the ADK-compliant Memory Service
neo4j_memory_service = Neo4jMemoryService(
    memory_client=memory_client,
    user_id="user_1",
)

# Attach the memory service to the Runner
runner = Runner(
    app_name="app",
    agent=agent,
    artifact_service=InMemoryArtifactService(),
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
fresh_session = await session_service.get_session(session_id=session.id, app_name="app", user_id="user_1")
await neo4j_memory_service.add_session_to_memory(fresh_session)
```
  
## Example  

| Notebook | Description |
|----------|-------------|
| [google_adk.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/google-adk/google_adk.ipynb) | Walkthrough of using Google ADK with Neo4j MCP: agent setup, Cypher query execution, and utilising persistent graph memory for agent |
  
## Resources  
• [Neo4j MCP Server Documentation](https://neo4j.com/docs/mcp/current/)
• [Google ADK Official Documentation](https://docs.cloud.google.com/agent-builder/agent-development-kit/overview)
• [Neo4j Agent Memory](https://neo4j.com/labs/agent-memory/)
