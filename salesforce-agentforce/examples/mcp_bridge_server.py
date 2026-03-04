"""
mcp_bridge_server.py — FastAPI REST Adapter for Neo4j MCP → AgentForce

PURPOSE
-------
When Salesforce AgentForce's native MCP client (Pilot July 2025) is not yet
available in your org, this server acts as a REST bridge:

  AgentForce External Service Action
    → Named Credential → THIS FastAPI server
      → Neo4j Python driver (direct) or Neo4j MCP server (HTTP)
        → Neo4j Database

FEATURES
--------
- All 11 reference agent tools as REST endpoints
- OpenAPI 3.0 spec auto-generated at /openapi.json (import into Salesforce!)
- API key authentication via X-Api-Key header
- Concise JSON responses optimized for AgentForce ARE (under 2000 tokens)
- Combined research endpoint to minimize Apex callouts (limit: 10/tx)
- Health check endpoint for monitoring

DEPLOYMENT
----------
  Heroku:   heroku create && git push heroku main
  Cloud Run: gcloud run deploy --image gcr.io/project/neo4j-bridge
  Local:    uvicorn mcp_bridge_server:app --host 0.0.0.0 --port 8080

ENVIRONMENT VARIABLES
---------------------
  NEO4J_URI          neo4j+s://demo.neo4jlabs.com:7687
  NEO4J_USERNAME     companies
  NEO4J_PASSWORD     companies
  NEO4J_DATABASE     companies
  API_KEY            your-secret-api-key-for-salesforce
  OPENAI_API_KEY     (optional) for vector search embeddings
"""

import os
import asyncio
import hashlib
import hmac
from typing import Optional

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from neo4j_tools import (
    driver,
    query_company,
    search_companies,
    list_industries,
    companies_in_industry,
    search_news,
    articles_in_month,
    get_article,
    companies_in_article,
    people_at_company,
    analyze_relationships,
    find_influential_companies,
    research_company_full,
    health_check,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Neo4j Knowledge Graph API for Salesforce AgentForce",
    description=(
        "REST adapter exposing Neo4j Company News Knowledge Graph as "
        "AgentForce-compatible External Service Actions. "
        "Import /openapi.json into Salesforce External Services."
    ),
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("API_KEY", "")
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def verify_api_key(key: Optional[str] = Security(api_key_header)):
    if not API_KEY:
        return  # No key configured → open access (dev mode)
    if not key or not hmac.compare_digest(key.encode(), API_KEY.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CompanyNameRequest(BaseModel):
    company_name: str = Field(..., description="Exact or partial company name")


class SearchRequest(BaseModel):
    search: str = Field(..., description="Search term for full-text company search")


class IndustryRequest(BaseModel):
    industry: str = Field(..., description="Industry category name")


class NewsSearchRequest(BaseModel):
    company_name: str = Field(..., description="Company name to filter news for")
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(5, ge=1, le=10, description="Maximum results (1-10)")


class ArticleRequest(BaseModel):
    article_id: str = Field(..., description="Article ID from news search results")


class PeopleRequest(BaseModel):
    company_id: str = Field(..., description="Company ID from company profile")


class RelationshipsRequest(BaseModel):
    company_name: str = Field(..., description="Company name to analyze")
    max_depth: int = Field(2, ge=1, le=3, description="Graph traversal depth (1-3)")


class PageRankRequest(BaseModel):
    limit: int = Field(10, ge=1, le=50, description="Number of top companies")


class DateRequest(BaseModel):
    date: str = Field(..., description="Start date in yyyy-mm-dd format")


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def get_health():
    """Check Neo4j connectivity and API status."""
    return health_check()


# ---------------------------------------------------------------------------
# Company Tools
# ---------------------------------------------------------------------------

@app.post(
    "/tools/query_company",
    tags=["Company"],
    summary="Get company profile from knowledge graph",
    description=(
        "Retrieves detailed information about a specific company including "
        "its industry sector, headquarters location, key leadership, and "
        "company ID. Use this when the user asks about a specific company. "
        "Always returns company_id for use in follow-up queries."
    ),
)
def api_query_company(req: CompanyNameRequest, _=Depends(verify_api_key)):
    result = query_company(req.company_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Company '{req.company_name}' not found")
    return result


@app.post(
    "/tools/search_companies",
    tags=["Company"],
    summary="Search for companies by name",
    description=(
        "Full-text search to find companies matching a name or search term. "
        "Returns company_id values needed for subsequent queries. "
        "Use when the exact company name is unknown."
    ),
)
def api_search_companies(req: SearchRequest, _=Depends(verify_api_key)):
    return {"companies": search_companies(req.search)[:20]}


@app.get(
    "/tools/list_industries",
    tags=["Industry"],
    summary="List all industry categories",
    description=(
        "Returns all available industry categories in the knowledge graph. "
        "Use before filtering companies by industry."
    ),
)
def api_list_industries(_=Depends(verify_api_key)):
    return {"industries": list_industries()}


@app.post(
    "/tools/companies_in_industry",
    tags=["Industry"],
    summary="Get companies in a specific industry",
    description=(
        "Returns companies in a given industry category. "
        "Excludes subsidiaries. Use list_industries() first to get valid category names."
    ),
)
def api_companies_in_industry(req: IndustryRequest, _=Depends(verify_api_key)):
    return {"companies": companies_in_industry(req.industry)}


# ---------------------------------------------------------------------------
# News Tools
# ---------------------------------------------------------------------------

@app.post(
    "/tools/search_news",
    tags=["News"],
    summary="Search company news using vector similarity",
    description=(
        "Semantic vector search for news articles about a company. "
        "Finds the most relevant articles based on the search query. "
        "Returns article_id values for retrieving full content."
    ),
)
def api_search_news(req: NewsSearchRequest, _=Depends(verify_api_key)):
    try:
        results = search_news(req.company_name, req.query, req.limit)
        return {"articles": results, "count": len(results)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post(
    "/tools/articles_in_month",
    tags=["News"],
    summary="Get articles published in a specific month",
    description=(
        "Returns news articles published within a given month. "
        "Useful for time-based research and tracking events. "
        "Date format: yyyy-mm-dd (e.g., 2024-01-01 for January 2024)."
    ),
)
def api_articles_in_month(req: DateRequest, _=Depends(verify_api_key)):
    return {"articles": articles_in_month(req.date)}


@app.post(
    "/tools/get_article",
    tags=["News"],
    summary="Get full article content",
    description=(
        "Retrieves complete article details including full text content. "
        "Use article_id from search_news() or articles_in_month() results."
    ),
)
def api_get_article(req: ArticleRequest, _=Depends(verify_api_key)):
    result = get_article(req.article_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Article '{req.article_id}' not found")
    # Truncate full content to 1000 chars to stay within ARE context limits
    if result.get("content") and len(result["content"]) > 1000:
        result["content"] = result["content"][:1000] + "...[truncated]"
    return result


@app.post(
    "/tools/companies_in_article",
    tags=["News"],
    summary="Get companies mentioned in an article",
    description=(
        "Returns all companies mentioned in a specific article. "
        "Use article_id from search_news() results."
    ),
)
def api_companies_in_article(req: ArticleRequest, _=Depends(verify_api_key)):
    return {"companies": companies_in_article(req.article_id)}


# ---------------------------------------------------------------------------
# People and Relationships
# ---------------------------------------------------------------------------

@app.post(
    "/tools/people_at_company",
    tags=["People"],
    summary="Get people associated with a company",
    description=(
        "Returns people and their roles at a specific company. "
        "Requires company_id from query_company() or search_companies() results."
    ),
)
def api_people_at_company(req: PeopleRequest, _=Depends(verify_api_key)):
    return {"people": people_at_company(req.company_id)}


@app.post(
    "/tools/analyze_relationships",
    tags=["Relationships"],
    summary="Find organizations related to a company",
    description=(
        "Graph traversal to find organizations connected to the target company. "
        "Returns direct (distance=1) and indirect (distance=2) relationships. "
        "Useful for competitive analysis and supply chain research."
    ),
)
def api_analyze_relationships(req: RelationshipsRequest, _=Depends(verify_api_key)):
    return {"relationships": analyze_relationships(req.company_name, req.max_depth)}


@app.post(
    "/tools/find_influential_companies",
    tags=["Analytics"],
    summary="Find most influential companies using PageRank",
    description=(
        "Runs PageRank graph algorithm to identify the most influential companies "
        "based on their organizational relationships. Higher scores = more connected "
        "and important in the business network. Requires GDS plugin."
    ),
)
def api_find_influential_companies(req: PageRankRequest, _=Depends(verify_api_key)):
    try:
        return {"companies": find_influential_companies(req.limit)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"GDS algorithm failed: {str(e)}")


# ---------------------------------------------------------------------------
# Combined Research (Minimize Apex callouts — recommended for AgentForce)
# ---------------------------------------------------------------------------

@app.post(
    "/research/company",
    tags=["Research"],
    summary="Full company research in a single API call",
    description=(
        "Combined endpoint returning company profile, recent news, and relationships "
        "in a single call. Designed to minimize Apex HTTP callouts (limit: 10/transaction). "
        "Use this as the primary research action in AgentForce for company queries."
    ),
)
def api_research_company(req: CompanyNameRequest, _=Depends(verify_api_key)):
    result = research_company_full(req.company_name)
    if not result.get("profile"):
        raise HTTPException(status_code=404, detail=f"Company '{req.company_name}' not found")
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
