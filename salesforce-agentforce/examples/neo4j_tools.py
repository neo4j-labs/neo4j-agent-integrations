"""
neo4j_tools.py — Neo4j Tool Functions for the Industry Research Agent

Full implementation of all reference agent tool functions from EXAMPLE_AGENT.md.
These functions are exposed as REST endpoints via mcp_bridge_server.py and
registered as AgentForce External Service Actions or Apex Actions.

Demo Database:
  URI:      neo4j+s://demo.neo4jlabs.com:7687
  Username: companies
  Password: companies
  Database: companies

Schema:
  (:Organization)-[:IN_INDUSTRY]->(:Industry)
  (:Organization)-[:IN_INDUSTRY]->(:IndustryCategory)
  (:Organization)-[:LOCATED_IN]->(:Location)
  (:Person)-[:WORKS_FOR]->(:Organization)
  (:Article)-[:MENTIONS]->(:Organization)
  (:Article)-[:HAS_CHUNK]->(:Chunk)  <- vector indexed
"""

import os
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Driver initialization — reuse single instance
# ---------------------------------------------------------------------------

NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "companies")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "companies")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "companies")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


# ---------------------------------------------------------------------------
# Helper: embed text (used for vector search)
# ---------------------------------------------------------------------------

def embed_query(text: str) -> list[float]:
    """
    Generate embedding for vector search.
    Uses OpenAI text-embedding-3-small by default.
    Swap for any embedding model compatible with your Neo4j vector index.
    """
    try:
        import openai
        response = openai.embeddings.create(
            model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            input=text
        )
        return response.data[0].embedding
    except ImportError:
        raise RuntimeError(
            "openai package required for vector search. "
            "pip install openai and set OPENAI_API_KEY."
        )


# ---------------------------------------------------------------------------
# Tool 1: Query Company Profile
# ---------------------------------------------------------------------------

def query_company(company_name: str) -> dict:
    """
    Query company information from Neo4j.

    Returns organization details including locations, industries, and leadership.
    Use this first when a user asks about a specific company.

    Args:
        company_name: Exact company name (e.g., "Apple", "Microsoft Corporation")

    Returns:
        {
            'name': str,
            'company_id': str,
            'summary': str,
            'locations': [str],
            'industries': [str],
            'leadership': [{'name': str, 'title': str}]
        }
    """
    query = """
    MATCH (o:Organization {name: $company})
    RETURN o.name as name,
           o.id as company_id,
           o.summary as summary,
           [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
           [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
           [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
    LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        database_=NEO4J_DATABASE
    )
    return records[0].data() if records else {}


# ---------------------------------------------------------------------------
# Tool 2: Search Companies (Full-Text)
# ---------------------------------------------------------------------------

def search_companies(search: str) -> list:
    """
    Full-text search for companies by name.

    Returns up to 100 results ordered by relevance. Excludes subsidiaries.
    Use when you need to find a company name or browse companies matching a term.

    Args:
        search: Partial or full company name search term

    Returns:
        [{'company_id': str, 'name': str, 'summary': str}]
    """
    query = """
    CALL db.index.fulltext.queryNodes('entity', $search, {limit: 100})
    YIELD node as c, score
    WHERE c:Organization
    AND NOT EXISTS { (c)<-[:HAS_SUBSIDIARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    ORDER BY score DESC
    """
    records, summary, keys = driver.execute_query(
        query,
        search=search,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 3: List Industries
# ---------------------------------------------------------------------------

def list_industries() -> list:
    """
    Get all industry categories in the knowledge graph.

    Use to browse available industries before filtering companies by sector.

    Returns:
        [{'industry': str}]
    """
    query = """
    MATCH (i:IndustryCategory)
    RETURN i.name as industry
    ORDER BY i.name
    """
    records, summary, keys = driver.execute_query(
        query,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 4: Companies in Industry
# ---------------------------------------------------------------------------

def companies_in_industry(industry: str) -> list:
    """
    Get companies in a specific industry category.

    Excludes subsidiaries, returns only independent organizations.

    Args:
        industry: Industry category name (use list_industries() to browse)

    Returns:
        [{'company_id': str, 'name': str, 'summary': str}]
    """
    query = """
    MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
    WHERE NOT EXISTS { (c)<-[:HAS_SUBSIDIARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    """
    records, summary, keys = driver.execute_query(
        query,
        industry=industry,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 5: Search News (Vector Search)
# ---------------------------------------------------------------------------

def search_news(company_name: str, query: str, limit: int = 5) -> list:
    """
    Vector similarity search for news articles about a company.

    Uses semantic search over article embeddings to find the most relevant news.
    Requires OPENAI_API_KEY environment variable for embedding generation.

    Args:
        company_name: Company name to filter news for
        query: Natural language search query (e.g., "acquisitions and partnerships")
        limit: Maximum results to return (default 5, max 10)

    Returns:
        [{'title': str, 'date': str, 'text': str, 'score': float, 'article_id': str}]
    """
    cypher = """
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
    MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
    CALL db.index.vector.queryNodes('news', $limit, $embedding)
    YIELD node, score
    WHERE node = c
    RETURN a.title as title,
           a.id as article_id,
           toString(a.date) as date,
           c.text as text,
           score
    ORDER BY score DESC
    """
    embedding = embed_query(query)
    records, summary, keys = driver.execute_query(
        cypher,
        company=company_name,
        limit=min(limit, 10),
        embedding=embedding,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 6: Articles in Month
# ---------------------------------------------------------------------------

def articles_in_month(date: str) -> list:
    """
    Get articles published within a specific month.

    Args:
        date: Start date in yyyy-mm-dd format (e.g., "2024-01-01")

    Returns:
        [{'article_id': str, 'author': str, 'title': str, 'date': str, 'sentiment': float}]
    """
    query = """
    MATCH (a:Article)
    WHERE date($date) <= date(a.date) < date($date) + duration('P1M')
    RETURN a.id as article_id,
           a.author as author,
           a.title as title,
           toString(a.date) as date,
           a.sentiment as sentiment
    ORDER BY a.date DESC
    LIMIT 25
    """
    records, summary, keys = driver.execute_query(
        query,
        date=date,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 7: Get Article Details
# ---------------------------------------------------------------------------

def get_article(article_id: str) -> dict:
    """
    Get complete article details including full text content.

    Args:
        article_id: Article ID from search_news() or articles_in_month()

    Returns:
        {'article_id': str, 'author': str, 'title': str, 'date': str,
         'summary': str, 'site': str, 'sentiment': float, 'content': str}
    """
    query = """
    MATCH (a:Article)-[:HAS_CHUNK]->(c:Chunk)
    WHERE a.id = $article_id
    WITH a, c ORDER BY id(c) ASC
    WITH a, collect(c.text) as contents
    RETURN a.id as article_id,
           a.author as author,
           a.title as title,
           toString(a.date) as date,
           a.summary as summary,
           a.siteName as site,
           a.sentiment as sentiment,
           apoc.text.join(contents, ' ') as content
    """
    records, summary, keys = driver.execute_query(
        query,
        article_id=article_id,
        database_=NEO4J_DATABASE
    )
    return records[0].data() if records else {}


# ---------------------------------------------------------------------------
# Tool 8: Companies in Article
# ---------------------------------------------------------------------------

def companies_in_article(article_id: str) -> list:
    """
    Get companies mentioned in a specific article.

    Args:
        article_id: Article ID from search_news() or articles_in_month()

    Returns:
        [{'company_id': str, 'name': str, 'summary': str}]
    """
    query = """
    MATCH (a:Article)-[:MENTIONS]->(c:Organization)
    WHERE a.id = $article_id
    AND NOT EXISTS { (c)<-[:HAS_SUBSIDIARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    """
    records, summary, keys = driver.execute_query(
        query,
        article_id=article_id,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 9: People at Company
# ---------------------------------------------------------------------------

def people_at_company(company_id: str) -> list:
    """
    Get people associated with a company and their roles.

    Args:
        company_id: Company ID from query_company() or search_companies()

    Returns:
        [{'role': str, 'person_name': str, 'company_id': str, 'company_name': str}]
    """
    query = """
    MATCH (c:Organization)-[role]-(p:Person)
    WHERE c.id = $company_id
    RETURN replace(type(role), "HAS_", "") as role,
           p.name as person_name,
           c.id as company_id,
           c.name as company_name
    """
    records, summary, keys = driver.execute_query(
        query,
        company_id=company_id,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 10: Analyze Relationships
# ---------------------------------------------------------------------------

def analyze_relationships(company_name: str, max_depth: int = 2) -> list:
    """
    Find organizations related to a company through graph traversal.

    Args:
        company_name: Company name to analyze
        max_depth: Graph traversal depth (1=direct, 2=second-degree, default 2)

    Returns:
        [{'organization': str, 'relationships': [str], 'distance': int}]
    """
    query = """
    MATCH path = (o1:Organization {name: $company})
                 -[*1..$depth]-(o2:Organization)
    WHERE o1 <> o2
    RETURN DISTINCT o2.name as organization,
           [r in relationships(path) | type(r)] as relationships,
           length(path) as distance
    ORDER BY distance
    LIMIT 20
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        depth=max_depth,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Tool 11: Find Influential Companies (PageRank)
# ---------------------------------------------------------------------------

def find_influential_companies(limit: int = 10) -> list:
    """
    Identify the most influential companies using PageRank graph algorithm.

    Uses Neo4j GDS to calculate importance based on organizational relationships.
    Requires the GDS (Graph Data Science) plugin.

    Args:
        limit: Number of top companies to return (default 10)

    Returns:
        [{'company_name': str, 'company_id': str, 'score': float}]
    """
    query = """
    CALL gds.graph.drop('companies', false) YIELD graphName
    WITH count(*) as _

    MATCH (o1:Organization)--(o2:Organization)
    WITH o1, o2, count(*) as freq
    WHERE freq > 1
    WITH gds.graph.project(
        'companies',
        o1,
        o2,
        {relationshipProperties: {weight: freq}},
        {undirectedRelationshipTypes: ['*']}
    ) as graph

    CALL gds.pageRank.stream('companies')
    YIELD nodeId, score
    WITH * ORDER BY score DESC LIMIT $limit
    RETURN gds.util.asNode(nodeId).name as company_name,
           gds.util.asNode(nodeId).id as company_id,
           score
    """
    records, summary, keys = driver.execute_query(
        query,
        limit=limit,
        database_=NEO4J_DATABASE
    )
    return [record.data() for record in records]


# ---------------------------------------------------------------------------
# Combined Research Tool (Recommended for AgentForce to minimize callouts)
# ---------------------------------------------------------------------------

def research_company_full(company_name: str) -> dict:
    """
    Combined research endpoint: profile + recent news + relationships in one call.

    Designed for AgentForce to minimize the number of HTTP callouts (Apex limit: 10/tx).
    Returns all key data points needed for a complete company research report.

    Args:
        company_name: Company name to research

    Returns:
        {
            'profile': dict,         # from query_company()
            'recent_news': [dict],   # top 5 recent articles (no vector search, title+date only)
            'relationships': [dict], # direct relationships (depth=1)
            'people': [dict]         # leadership from query_company
        }
    """
    # Company profile with leadership
    profile_query = """
    MATCH (o:Organization {name: $company})
    RETURN o.name as name,
           o.id as company_id,
           o.summary as summary,
           [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
           [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
           [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
    LIMIT 1
    """
    profile_records, _, _ = driver.execute_query(
        profile_query, company=company_name, database_=NEO4J_DATABASE
    )
    profile = profile_records[0].data() if profile_records else {}

    # Recent articles (no embedding needed — sorted by date)
    news_query = """
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
    RETURN a.id as article_id,
           a.title as title,
           toString(a.date) as date,
           a.sentiment as sentiment,
           a.summary as summary
    ORDER BY a.date DESC
    LIMIT 5
    """
    news_records, _, _ = driver.execute_query(
        news_query, company=company_name, database_=NEO4J_DATABASE
    )
    news = [r.data() for r in news_records]

    # Direct organizational relationships
    rel_query = """
    MATCH (o1:Organization {name: $company})-[r]-(o2:Organization)
    RETURN DISTINCT o2.name as organization,
           type(r) as relationship_type,
           1 as distance
    LIMIT 10
    """
    rel_records, _, _ = driver.execute_query(
        rel_query, company=company_name, database_=NEO4J_DATABASE
    )
    relationships = [r.data() for r in rel_records]

    return {
        "profile": profile,
        "recent_news": news,
        "relationships": relationships,
        "total_news_available": len(news)
    }


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def health_check() -> dict:
    """Check Neo4j connectivity and return basic stats."""
    try:
        records, _, _ = driver.execute_query(
            "MATCH (o:Organization) RETURN count(o) as org_count LIMIT 1",
            database_=NEO4J_DATABASE
        )
        return {
            "status": "healthy",
            "neo4j_uri": NEO4J_URI,
            "database": NEO4J_DATABASE,
            "organization_count": records[0]["org_count"] if records else 0
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    # Quick test
    print("Health check:", health_check())
    print("\nSearch for 'Apple':", search_companies("Apple")[:3])
    print("\nCompany profile:", query_company("Apple"))
