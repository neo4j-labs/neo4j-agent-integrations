"""
graphrag_bridge_server.py — Neo4j GraphRAG Retriever Bridge for Salesforce Agentforce

Implements GraphRAG (Graph-Retrieval Augmented Generation) by combining:
  1. Vector similarity search  — find semantically similar article chunks
  2. Graph neighborhood traversal — expand each chunk to its full context:
       - Parent Article (title, date, sentiment)
       - Related Organizations mentioned in the same article
       - Chunk siblings (adjacent chunks for reading-window continuity)
       - Industry / Location context of mentioned companies

This produces richer, more accurate retrieval than vanilla vector RAG because:
  - Complex multi-hop questions (e.g. "What did Apple's competitors announce?")
    return context from RELATED companies, not just Apple chunks.
  - Entity co-occurrence graph surfaces non-obvious connections.
  - Adjacent chunks avoid split-context hallucinations.

Integration with Salesforce Agentforce — two paths:

  Path 1: External Service Action (Track B)
    FastAPI auto-generates OAS 3.0. Import /openapi.json into Salesforce
    External Services. The /graphrag/search endpoint becomes an agent action.

  Path 2: Data Cloud + Neo4j Connector (Beta)
    Use the official Neo4j → Data Cloud connector to sync Article + Chunk data
    (including vector embeddings) into Data Cloud. Build a Data Cloud search
    index over the synced embeddings. Agentforce queries via Data Cloud RAG.
    NOTE: Path 1 gives real-time graph traversal; Path 2 gives pre-indexed
    retrieval but loses live graph neighborhood context.

Package: neo4j-graphrag 1.13.0 (Feb 3 2026)
         neo4j 6.0+ (Jan 12 2026)
         fastapi 0.129+

Demo Database:
  URI:      neo4j+s://demo.neo4jlabs.com:7687
  Username: companies
  Password: companies
  Database: companies

Schema relevant to GraphRAG:
  (:Article)-[:HAS_CHUNK]->(:Chunk)         <- Chunk.embedding vector indexed as 'news'
  (:Article)-[:MENTIONS]->(:Organization)
  (:Organization)-[:IN_INDUSTRY]->(:Industry)
  (:Organization)-[:LOCATED_IN]->(:Location)
  (:Chunk)-[:NEXT]->(:Chunk)                <- optional sibling chain (if exists)
"""

import os
import hmac
import secrets
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

import neo4j
from neo4j_graphrag.retrievers import (
    VectorCypherRetriever,
    HybridCypherRetriever,
    VectorRetriever,
)
from neo4j_graphrag.embeddings.openai import OpenAIEmbeddings
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.generation import GraphRAG

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NEO4J_URI      = os.environ.get("NEO4J_URI",      "neo4j+s://demo.neo4jlabs.com:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "companies")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "companies")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "companies")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL       = os.environ.get("LLM_MODEL",       "gpt-4o-mini")

# API key for authenticating requests from Salesforce Named Credential
API_KEY        = os.environ.get("BRIDGE_API_KEY", secrets.token_urlsafe(32))
VECTOR_INDEX   = "news"       # Neo4j vector index on Chunk.embedding
FULLTEXT_INDEX = "entity"     # Neo4j fulltext index on Organization names

# ---------------------------------------------------------------------------
# Neo4j driver (single instance, reused across requests)
# ---------------------------------------------------------------------------

driver = neo4j.GraphDatabase.driver(
    NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)
embedder = OpenAIEmbeddings(model=EMBEDDING_MODEL)

# ---------------------------------------------------------------------------
# GraphRAG Retrieval Queries
# ---------------------------------------------------------------------------
# These Cypher fragments execute AFTER the initial vector/hybrid index search.
# The variable `node` is the matched Chunk node; `score` is its similarity score.
#
# Why graph traversal beats plain vector RAG:
#   Plain RAG returns: chunk text only
#   GraphRAG returns:  chunk text + parent article metadata + all organizations
#                      mentioned in that article + their industry/location context
#
# For complex questions like "What partnerships did Apple's cloud competitors
# announce in Q4 2024?", the graph traversal surfaces:
#   - Microsoft Azure, Google Cloud ([:MENTIONS] from same articles)
#   - Their industry context ([:IN_INDUSTRY] -> "Cloud Computing")
#   - Sentiment signal from article metadata

# Retrieval query 1: Full document graph context
# For each matched Chunk, return the full article + all companies mentioned
FULL_CONTEXT_RETRIEVAL_QUERY = """
// Traverse from matched chunk → parent article → all mentioned organizations
MATCH (node)<-[:HAS_CHUNK]-(article:Article)
OPTIONAL MATCH (article)-[:MENTIONS]->(org:Organization)
WITH node, score, article,
     collect(DISTINCT {
         name: org.name,
         id:   org.id,
         industries: [(org)-[:IN_INDUSTRY]->(i:Industry) | i.name],
         locations:  [(org)-[:LOCATED_IN]->(l:Location)  | l.name]
     }) AS mentioned_orgs
RETURN
    node.text                       AS chunk_text,
    score                           AS similarity_score,
    article.id                      AS article_id,
    article.title                   AS article_title,
    toString(article.date)          AS article_date,
    article.sentiment               AS article_sentiment,
    article.siteName                AS article_source,
    mentioned_orgs                  AS mentioned_organizations
ORDER BY score DESC
"""

# Retrieval query 2: Reading-window context (chunk + adjacent chunks)
# Returns the matched chunk plus its immediate neighbours for continuity.
# Prevents splitting a sentence across chunk boundaries.
WINDOW_CONTEXT_RETRIEVAL_QUERY = """
MATCH (node)<-[:HAS_CHUNK]-(article:Article)
// Collect the matched chunk and up to 1 chunk on each side
OPTIONAL MATCH (prev:Chunk)-[:NEXT]->(node)
OPTIONAL MATCH (node)-[:NEXT]->(nxt:Chunk)
WITH node, score, article, prev, nxt
RETURN
    coalesce(prev.text, '') + ' ' + node.text + ' ' + coalesce(nxt.text, '')
        AS chunk_text,
    score                   AS similarity_score,
    article.id              AS article_id,
    article.title           AS article_title,
    toString(article.date)  AS article_date,
    article.sentiment       AS article_sentiment
ORDER BY score DESC
"""

# Retrieval query 3: Entity-neighbourhood context
# For a company-focused question, find articles whose chunks match the query
# AND that mention the target company, then expand to co-mentioned companies.
# Used by the /graphrag/entity_search endpoint.
ENTITY_NEIGHBORHOOD_RETRIEVAL_QUERY = """
MATCH (node)<-[:HAS_CHUNK]-(article:Article)-[:MENTIONS]->(target:Organization)
WHERE target.name = $entity_name
MATCH (article)-[:MENTIONS]->(coOrg:Organization)
WHERE coOrg <> target
WITH node, score, article, target,
     collect(DISTINCT coOrg.name)[..5] AS co_mentioned
RETURN
    node.text              AS chunk_text,
    score                  AS similarity_score,
    article.id             AS article_id,
    article.title          AS article_title,
    toString(article.date) AS article_date,
    article.sentiment      AS article_sentiment,
    target.name            AS entity_name,
    co_mentioned           AS co_mentioned_companies
ORDER BY score DESC
"""

# ---------------------------------------------------------------------------
# Retriever instances (lazily initialised)
# ---------------------------------------------------------------------------

_vector_cypher_retriever: Optional[VectorCypherRetriever]  = None
_hybrid_cypher_retriever: Optional[HybridCypherRetriever]  = None
_plain_vector_retriever:  Optional[VectorRetriever]        = None


def get_vector_cypher_retriever() -> VectorCypherRetriever:
    global _vector_cypher_retriever
    if _vector_cypher_retriever is None:
        _vector_cypher_retriever = VectorCypherRetriever(
            driver=driver,
            index_name=VECTOR_INDEX,
            embedder=embedder,
            retrieval_query=FULL_CONTEXT_RETRIEVAL_QUERY,
            neo4j_database=NEO4J_DATABASE,
        )
    return _vector_cypher_retriever


def get_hybrid_cypher_retriever() -> HybridCypherRetriever:
    global _hybrid_cypher_retriever
    if _hybrid_cypher_retriever is None:
        _hybrid_cypher_retriever = HybridCypherRetriever(
            driver=driver,
            vector_index_name=VECTOR_INDEX,
            fulltext_index_name=FULLTEXT_INDEX,
            embedder=embedder,
            retrieval_query=FULL_CONTEXT_RETRIEVAL_QUERY,
            neo4j_database=NEO4J_DATABASE,
        )
    return _hybrid_cypher_retriever


def get_plain_vector_retriever() -> VectorRetriever:
    global _plain_vector_retriever
    if _plain_vector_retriever is None:
        _plain_vector_retriever = VectorRetriever(
            driver=driver,
            index_name=VECTOR_INDEX,
            embedder=embedder,
            neo4j_database=NEO4J_DATABASE,
        )
    return _plain_vector_retriever


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Neo4j GraphRAG Bridge",
    description=(
        "GraphRAG retriever bridge for Salesforce Agentforce. "
        "Combines Neo4j vector search with graph neighbourhood traversal "
        "to return richer, more accurate context than vanilla RAG. "
        "Import /openapi.json as a Salesforce External Service."
    ),
    version="1.0.0",
)

# API Key auth via Salesforce Named Credential header
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=True)


def verify_api_key(key: str = Security(api_key_header)) -> str:
    if not hmac.compare_digest(key.encode(), API_KEY.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return key


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class GraphRAGSearchRequest(BaseModel):
    query: str = Field(
        ...,
        description="Natural language search query",
        example="What partnerships did Apple announce with cloud providers?",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of results to return (max 10 for ARE token budget)",
    )
    mode: str = Field(
        default="hybrid_cypher",
        description=(
            "Retrieval mode: "
            "'hybrid_cypher' (vector + fulltext + graph traversal, best quality), "
            "'vector_cypher' (vector + graph traversal), "
            "'vector_only' (plain vector, fastest, least context)"
        ),
    )


class EntityGraphRAGRequest(BaseModel):
    entity_name: str = Field(
        ...,
        description="Company or organization name to focus retrieval on",
        example="Apple",
    )
    query: str = Field(
        ...,
        description="Natural language question about the entity",
        example="What cloud partnerships were announced?",
    )
    top_k: int = Field(default=5, ge=1, le=10)


class ChunkResult(BaseModel):
    chunk_text: str
    similarity_score: float
    article_id: str
    article_title: str
    article_date: str
    article_sentiment: Optional[float] = None
    article_source: Optional[str] = None
    mentioned_organizations: Optional[list] = None
    co_mentioned_companies: Optional[list] = None


class GraphRAGSearchResponse(BaseModel):
    query: str
    mode: str
    results: list[ChunkResult]
    result_count: int
    retrieval_note: str


class GenerativeRAGRequest(BaseModel):
    query: str = Field(
        ...,
        description="Question to answer using GraphRAG",
        example="Summarize Apple's key partnerships in 2024",
    )
    top_k: int = Field(default=5, ge=1, le=10)


class GenerativeRAGResponse(BaseModel):
    query: str
    answer: str
    retrieval_note: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    """Health check — verifies Neo4j connectivity."""
    try:
        records, _, _ = driver.execute_query(
            "MATCH (c:Chunk) RETURN count(c) AS chunk_count LIMIT 1",
            database_=NEO4J_DATABASE,
        )
        return {
            "status": "healthy",
            "neo4j_uri": NEO4J_URI,
            "chunk_count": records[0]["chunk_count"] if records else 0,
            "vector_index": VECTOR_INDEX,
            "fulltext_index": FULLTEXT_INDEX,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.post(
    "/graphrag/search",
    response_model=GraphRAGSearchResponse,
    tags=["GraphRAG Retrieval"],
    summary="GraphRAG semantic search with graph context",
    description=(
        "Retrieves relevant article chunks using vector/hybrid search, then "
        "expands each result through the knowledge graph to return full article "
        "context plus all organisations mentioned in matching articles. "
        "Use this as the PRIMARY retrieval action for research questions. "
        "Returns richer context than plain vector search for multi-entity questions."
    ),
    operation_id="graphragSearch",
)
def graphrag_search(
    req: GraphRAGSearchRequest,
    _: str = Depends(verify_api_key),
) -> GraphRAGSearchResponse:
    """
    Core GraphRAG retrieval endpoint.

    Combines vector/hybrid similarity search with Cypher graph traversal:
      1. Embed the query → find top-k similar Chunk nodes
      2. For each Chunk: traverse to parent Article + all [:MENTIONS] Organizations
      3. Return enriched results with company context

    ARE token budget note: top_k=5 with full context ~1500 tokens, within the
    2000-token ARE truncation limit.
    """
    if req.mode == "hybrid_cypher":
        retriever = get_hybrid_cypher_retriever()
    elif req.mode == "vector_cypher":
        retriever = get_vector_cypher_retriever()
    elif req.mode == "vector_only":
        retriever = get_plain_vector_retriever()
        result = retriever.search(query_text=req.query, top_k=req.top_k)
        items = [
            ChunkResult(
                chunk_text=str(item.content),
                similarity_score=item.metadata.get("score", 0.0),
                article_id="",
                article_title="",
                article_date="",
            )
            for item in result.items
        ]
        return GraphRAGSearchResponse(
            query=req.query,
            mode=req.mode,
            results=items,
            result_count=len(items),
            retrieval_note="Plain vector retrieval — no graph context.",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {req.mode}")

    result = retriever.search(query_text=req.query, top_k=req.top_k)

    items = []
    for item in result.items:
        content = item.content if isinstance(item.content, dict) else {}
        items.append(ChunkResult(
            chunk_text=content.get("chunk_text", str(item.content)),
            similarity_score=content.get("similarity_score", item.metadata.get("score", 0.0)),
            article_id=content.get("article_id", ""),
            article_title=content.get("article_title", ""),
            article_date=content.get("article_date", ""),
            article_sentiment=content.get("article_sentiment"),
            article_source=content.get("article_source"),
            mentioned_organizations=content.get("mentioned_organizations", []),
        ))

    return GraphRAGSearchResponse(
        query=req.query,
        mode=req.mode,
        results=items,
        result_count=len(items),
        retrieval_note=(
            "Graph-enriched retrieval: each chunk includes parent article metadata "
            "and all organizations mentioned in that article."
        ),
    )


@app.post(
    "/graphrag/entity_search",
    response_model=GraphRAGSearchResponse,
    tags=["GraphRAG Retrieval"],
    summary="Entity-focused GraphRAG search with co-mention graph",
    description=(
        "Retrieves article chunks semantically similar to the query AND that "
        "mention a specific company. Expands to co-mentioned companies via the "
        "entity co-occurrence graph. Use for competitive intelligence questions "
        "like 'What did Apple's partners announce?'."
    ),
    operation_id="graphragEntitySearch",
)
def graphrag_entity_search(
    req: EntityGraphRAGRequest,
    _: str = Depends(verify_api_key),
) -> GraphRAGSearchResponse:
    """
    Entity-focused GraphRAG retrieval.

    Uses VectorCypherRetriever with ENTITY_NEIGHBORHOOD_RETRIEVAL_QUERY:
      1. Embed query → find top-k similar Chunks
      2. Filter to only chunks in articles mentioning entity_name
      3. Expand to co-mentioned companies (the co-occurrence graph)

    This answers questions like "What cloud partnerships did Apple announce?"
    by surfacing Microsoft, Google, AWS from the same articles — context that
    vanilla RAG misses entirely.
    """
    # Inject entity_name as a query parameter into the Cypher traversal
    # The retrieval_query can reference Cypher query parameters ($entity_name)
    retriever = VectorCypherRetriever(
        driver=driver,
        index_name=VECTOR_INDEX,
        embedder=embedder,
        retrieval_query=ENTITY_NEIGHBORHOOD_RETRIEVAL_QUERY,
        neo4j_database=NEO4J_DATABASE,
    )

    result = retriever.search(
        query_text=req.query,
        top_k=req.top_k,
        query_params={"entity_name": req.entity_name},
    )

    items = []
    for item in result.items:
        content = item.content if isinstance(item.content, dict) else {}
        items.append(ChunkResult(
            chunk_text=content.get("chunk_text", str(item.content)),
            similarity_score=content.get("similarity_score", item.metadata.get("score", 0.0)),
            article_id=content.get("article_id", ""),
            article_title=content.get("article_title", ""),
            article_date=content.get("article_date", ""),
            article_sentiment=content.get("article_sentiment"),
            co_mentioned_companies=content.get("co_mentioned_companies", []),
        ))

    return GraphRAGSearchResponse(
        query=req.query,
        mode="entity_neighborhood",
        results=items,
        result_count=len(items),
        retrieval_note=(
            f"Entity-neighbourhood retrieval for '{req.entity_name}': "
            "results include co-mentioned companies from the article co-occurrence graph."
        ),
    )


@app.post(
    "/graphrag/generate",
    response_model=GenerativeRAGResponse,
    tags=["GraphRAG Generation"],
    summary="End-to-end GraphRAG: retrieve + generate answer",
    description=(
        "Full RAG pipeline: retrieves graph-enriched context from Neo4j, then "
        "uses an LLM to synthesize a grounded answer. Requires OPENAI_API_KEY. "
        "Use this for one-shot Q&A. For multi-step research, use /graphrag/search "
        "to retrieve context and let Agentforce's ARE synthesize."
    ),
    operation_id="graphragGenerate",
)
def graphrag_generate(
    req: GenerativeRAGRequest,
    _: str = Depends(verify_api_key),
) -> GenerativeRAGResponse:
    """
    End-to-end GraphRAG pipeline using neo4j-graphrag GraphRAG class.

    Retrieves top-k graph-enriched chunks, then passes them to an LLM for
    grounded answer generation. This runs the full RAG loop server-side.

    Note for ARE integration: prefer /graphrag/search to get raw context and
    let ARE synthesize — this endpoint is for standalone usage or testing.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured. Use /graphrag/search for retrieval only.",
        )

    llm = OpenAILLM(model_name=LLM_MODEL)
    retriever = get_hybrid_cypher_retriever()

    rag = GraphRAG(retriever=retriever, llm=llm)
    response = rag.search(query_text=req.query, retriever_config={"top_k": req.top_k})

    return GenerativeRAGResponse(
        query=req.query,
        answer=response.answer,
        retrieval_note=(
            "Answer generated from graph-enriched context: "
            f"hybrid search + graph traversal, top_{req.top_k} chunks."
        ),
    )


# ---------------------------------------------------------------------------
# Data Cloud Integration Notes (non-endpoint documentation)
# ---------------------------------------------------------------------------
# Path 2: Neo4j → Salesforce Data Cloud Connector (Beta)
#
# The official Neo4j connector for Salesforce Data 360 can sync Neo4j data
# into Data Cloud. Setup:
#   1. Salesforce Setup → Data Cloud Setup → Other Connectors → New → Neo4j
#   2. Provide: URL (https://), database, port (7473), username, password, SSL cert
#   3. Create a Data Stream selecting which Neo4j nodes/properties to sync
#   4. Map to a Data Model Object (DMO) in Data Cloud
#   5. Build a Search Index over the DMO (including Chunk.embedding property)
#   6. Create a Retriever in Einstein Studio pointing to the Search Index
#   7. Add Retriever to an Agentforce Data Library
#   8. Link the Data Library to an agent Topic
#
# IMPORTANT TRADE-OFF:
#   Path 1 (this server): Live graph queries, full traversal, real-time data
#   Path 2 (Data Cloud connector): Pre-indexed, batch sync (lag), no traversal
#
#   For the companies knowledge graph, PATH 1 IS RECOMMENDED because:
#   - Article co-occurrence graph traversal is not possible from Data Cloud
#   - Near-real-time data freshness matters for news-based research
#   - GraphRAG neighbourhood expansion is only possible with live Cypher
#
#   Hybrid: Use Data Cloud for static content (product docs, knowledge base)
#           Use this server for live graph-enriched news + relationship queries

# ---------------------------------------------------------------------------
# Agentforce External Service Setup
# ---------------------------------------------------------------------------
# 1. Deploy this server: uvicorn graphrag_bridge_server:app --port 8081
# 2. Get spec: curl http://localhost:8081/openapi.json > graphrag_openapi.json
# 3. Import to Salesforce:
#      Setup → Integrations → External Services → New
#      Upload graphrag_openapi.json
#      Named Credential: Neo4j_GraphRAG_API (URL + X-Api-Key header)
# 4. Create Agent Actions from operations: graphragSearch, graphragEntitySearch
# 5. Create a Topic: "News Research"
#      Description: "Handles questions about recent news, articles, and market
#      developments. Uses GraphRAG to retrieve article context with full entity
#      co-occurrence graph. Does NOT handle company profile lookups."
#      Actions: graphragSearch (primary), graphragEntitySearch (for company focus)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print(f"Neo4j GraphRAG Bridge starting...")
    print(f"  Neo4j URI:    {NEO4J_URI}")
    print(f"  Database:     {NEO4J_DATABASE}")
    print(f"  Vector index: {VECTOR_INDEX}")
    print(f"  Fulltext idx: {FULLTEXT_INDEX}")
    print(f"  Embedding:    {EMBEDDING_MODEL}")
    print(f"  LLM model:    {LLM_MODEL}")
    print(f"  API key set:  {'yes' if API_KEY else 'NO - set BRIDGE_API_KEY'}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8081)
