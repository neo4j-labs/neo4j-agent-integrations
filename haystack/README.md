# Haystack + Neo4j Integration

## Overview

**Haystack** is an NLP framework for search and QA with component-based architecture and Neo4j document store integration.

**Official Resources:**
- Website: https://haystack.deepset.ai
- Documentation: https://docs.haystack.deepset.ai/
- Neo4j Integration: https://haystack.deepset.ai/integrations/neo4j-document-store

## Extension Points

### Neo4j Document Store

```python
from haystack.document_stores import Neo4jDocumentStore
from haystack.nodes import DensePassageRetriever
from haystack.pipelines import DocumentSearchPipeline

# Document store
document_store = Neo4jDocumentStore(
    url="bolt://demo.neo4jlabs.com:7687",
    username="companies",
    password="companies",
    database="companies"
)

# Retriever
retriever = DensePassageRetriever(
    document_store=document_store,
    query_embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    passage_embedding_model="sentence-transformers/all-MiniLM-L6-v2"
)

# Pipeline
pipeline = DocumentSearchPipeline(retriever)
results = pipeline.run(query="Companies in technology")
```

## MCP Authentication

⚠️ **Bespoke components** - No native MCP support

## Resources

- **Haystack**: https://haystack.deepset.ai/
- **Neo4j Store**: https://haystack.deepset.ai/integrations/neo4j-document-store
- **Neo4j Developer Guide**: https://neo4j.com/developer/genai-ecosystem/haystack/
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Neo4j document store
- ⚠️ No native MCP
- **Effort Score**: 5.7/10
- **Impact Score**: 1.7/10
