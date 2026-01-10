# LlamaIndex + Neo4j Integration

## Overview

**LlamaIndex** is a data framework for LLM apps with strong retrieval capabilities and mature Neo4j vector/graph store integrations.

**Official Resources:**
- Website: https://www.llamaindex.ai
- Documentation: https://docs.llamaindex.ai/
- Neo4j Integration: https://docs.llamaindex.ai/en/stable/examples/property_graph/property_graph_neo4j/

## Extension Points

### Native Neo4j Integration

```python
from llama_index.core import VectorStoreIndex, KnowledgeGraphIndex
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.vector_stores.neo4j import Neo4jVectorStore

# Graph store
graph_store = Neo4jGraphStore(
    url="neo4j+s://demo.neo4jlabs.com:7687",
    username="companies",
    password="companies",
    database="companies"
)

# Vector store
vector_store = Neo4jVectorStore(
    url="neo4j+s://demo.neo4jlabs.com:7687",
    username="companies",
    password="companies",
    database="companies",
    index_name="news"
)

# Knowledge Graph Index
kg_index = KnowledgeGraphIndex.from_documents(
    documents,
    graph_store=graph_store,
    storage_context=storage_context
)

# Vector Index
vector_index = VectorStoreIndex.from_vector_store(vector_store)

# Query
query_engine = kg_index.as_query_engine()
response = query_engine.query("What companies are in the technology industry?")
```

## MCP Authentication

⚠️ **Bespoke integrations** - No native MCP support

## Resources

- **LlamaIndex**: https://docs.llamaindex.ai/
- **Neo4j Property Graph**: https://docs.llamaindex.ai/en/stable/examples/property_graph/property_graph_neo4j/
- **Neo4j API Reference**: https://docs.llamaindex.ai/en/stable/api_reference/storage/graph_stores/neo4j/
- **Neo4j Developer Guide**: https://neo4j.com/developer/genai-ecosystem/llamaindex/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Mature Neo4j integrations
- ✅ Vector and graph stores
- ⚠️ No native MCP
- **Effort Score**: 4/10
- **Impact Score**: 3/10
