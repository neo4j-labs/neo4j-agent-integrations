import os
import json
import logging
import asyncio
import shlex
import shutil
import sysconfig
from pathlib import Path
from neo4j import GraphDatabase
from typing import List, Dict, Any
from google import genai
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "companies")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "companies")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "companies")

logging.basicConfig(level=logging.INFO)

_vertex_client: genai.Client | None = None


def get_vertex_client() -> genai.Client:
    """Create the Vertex AI client only when a news embedding is requested."""
    global _vertex_client
    if _vertex_client is None:
        _vertex_client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location="us-central1",
        )
    return _vertex_client
                      
def get_driver():
    """Returns a Neo4j driver instance."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


def _get_mcp_environment() -> dict[str, str]:
    """Forward the standard Neo4j configuration to the local MCP server."""
    environment = dict(os.environ)
    for mcp_setting, integration_setting in {
        "NEO4J_MCP_URI": "NEO4J_URI",
        "NEO4J_MCP_USERNAME": "NEO4J_USERNAME",
        "NEO4J_MCP_PASSWORD": "NEO4J_PASSWORD",
        "NEO4J_MCP_DATABASE": "NEO4J_DATABASE",
    }.items():
        if not environment.get(mcp_setting) and environment.get(integration_setting):
            environment[mcp_setting] = environment[integration_setting]
    environment.setdefault("NEO4J_MCP_READ_ONLY", "true")
    environment.setdefault("NEO4J_TELEMETRY", "false")
    return environment


async def execute_read_query(query: str, params: Dict[str, Any]) -> str | None:
    """Run a parameterized read query through local MCP when it is configured."""
    command = os.environ.get("MCP_SERVER_COMMAND", "").strip()
    if not command:
        return None

    command_parts = shlex.split(command)
    if not command_parts:
        raise ValueError("MCP_SERVER_COMMAND must contain an executable command.")
    executable = command_parts[0]
    if not os.path.dirname(executable):
        executable = shutil.which(executable) or str(Path(sysconfig.get_path("scripts")) / executable)
    server_params = StdioServerParameters(
        command=executable,
        args=command_parts[1:],
        env=_get_mcp_environment(),
    )
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool("read-cypher", {"query": query, "params": params})
            text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
            return text or json.dumps(result.model_dump())

async def query_company(company_name: str) -> str:
    """
    Query company information from Neo4j.
    Returns a dictionary with company details, locations, industries, and leadership.
    """
    query = """
    MATCH (o:Organization {name: $company})
    RETURN o.name as name,
           [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
           [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
           [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
    LIMIT 1
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                company=company_name,
                database_=NEO4J_DATABASE
            )
            result = records[0].data() if records else {}
            return json.dumps(result, indent=2)
    except Exception as e:
        logging.error(f"Error in query_company: {e}")
        return f"Error querying company: {str(e)}"

async def search_news(company_name: str, query: str, limit: int = 5) -> str:
    """
    Vector search for news articles about a company.
    """
    query_cypher = """
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
    MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
    CALL db.index.vector.queryNodes('news_google', $limit, $embedding)
    YIELD node, score
    WHERE node = c
    RETURN a.title as title,
           a.date as date,
           a.siteName as site,
           c.text as text,
           score
    ORDER BY score DESC
    """
    try:
        embedding = await embed_query(query)
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query_cypher,
                company=company_name,
                limit=limit,
                embedding=embedding,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in search_news: {e}")
        return f"Error searching news: {str(e)}"

async def analyze_relationships(company_name: str, max_depth: int = 2) -> str:
    """
    Find related organizations through graph traversal.
    """
    query = """
    MATCH path = (o1:Organization {name: $company})-[*1..$depth]-(o2:Organization)
    WHERE o1 <> o2
    RETURN DISTINCT o2.name as organization,
           reduce(s = "", r IN relationships(path) | s + "(" + type(r) + ")->") as relationships,
           length(path) as distance
    ORDER BY distance
    LIMIT 20
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                company=company_name,
                depth=max_depth,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in analyze_relationships: {e}")
        return f"Error analyzing relationships: {str(e)}"

async def list_industries() -> str:
    """
    Get all industry categories.
    """
    query = """
    MATCH (i:IndustryCategory)
    RETURN i.name as industry
    ORDER BY i.name
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(query, database_=NEO4J_DATABASE)
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in list_industries: {e}")
        return f"Error listing industries: {str(e)}"

async def companies_in_industry(industry: str) -> str:
    """
    Get companies in a specific industry.
    """
    query = """
    MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
    WHERE NOT EXISTS { (c)<-[:HAS_SUBSIDARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                industry=industry,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in companies_in_industry: {e}")
        return f"Error fetching companies in industry: {str(e)}"

async def search_companies(search: str) -> str:
    """
    Full-text search for companies by name.
    """
    query = """
    CALL db.index.fulltext.queryNodes('entity', $search, {limit: 100})
    YIELD node as c, score
    WHERE c:Organization
    AND NOT EXISTS { (c)<-[:HAS_SUBSIDARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    ORDER BY score DESC
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                search=search,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in search_companies: {e}")
        return f"Error searching companies: {str(e)}"

async def articles_in_month(date: str) -> str:
    """
    Get articles published in a specific month.
    Date format: YYYY-MM-DD
    """
    query = """
    MATCH (a:Article)
    WHERE date($date) <= date(a.date) < date($date) + duration('P1M')
    RETURN a.id as article_id,
           a.author as author,
           a.date as date,
           a.title as title,
           a.sentiment as sentiment
    ORDER BY a.date DESC
    LIMIT 25
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                date=date,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in articles_in_month: {e}")
        return f"Error fetching articles in month: {str(e)}"

async def get_article(article_id: str) -> str:
    """
    Get complete article details with full text content.
    """
    query = """
    MATCH (a:Article)-[:HAS_CHUNK]->(c:Chunk)
    WHERE a.id = $article_id
    WITH a, c ORDER BY id(c) ASC
    WITH a, collect(c.text) as contents
    RETURN a.id as article_id,
           a.author as author,
           a.date as date,
           a.siteName as site,
           a.title as title,
           a.sentiment as sentiment,
           apoc.text.join(contents, ' ') as content
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                article_id=article_id,
                database_=NEO4J_DATABASE
            )
            result = records[0].data() if records else {}
            return json.dumps(result, indent=2)
    except Exception as e:
        logging.error(f"Error in get_article: {e}")
        return f"Error getting article: {str(e)}"

async def companies_in_article(article_id: str) -> str:
    """
    Get companies mentioned in a specific article.
    """
    query = """
    MATCH (a:Article)-[:MENTIONS]->(c:Organization)
    WHERE a.id = $article_id
    AND NOT EXISTS { (c)<-[:HAS_SUBSIDARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                article_id=article_id,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in companies_in_article: {e}")
        return f"Error fetching companies in article: {str(e)}"

async def people_at_company(company_id: str) -> str:
    """
    Get people associated with a company and their roles.
    """
    query = """
    MATCH (c:Organization)-[role]-(p:Person)
    WHERE c.id = $company_id
    RETURN replace(type(role), "HAS_", "") as role,
           p.name as person_name,
           p.id as person_id,
           c.name as company_name
    """
    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query,
                company_id=company_id,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in people_at_company: {e}")
        return f"Error fetching people at company: {str(e)}"

async def find_influential_companies(limit: int = 10) -> str:
    """
    Find most influential companies using PageRank algorithm.
    """
    # The graph is already projected in the server if using the demo instance. If not, you can uncomment the following lines to drop and create the graph projection.
    # drop_query = "CALL gds.graph.drop('companies', false) YIELD graphName"
    # project_query = """
    # MATCH (o1:Organization)--(o2:Organization)
    # WITH o1, o2, count(*) as freq
    # WHERE freq > 1
    # WITH gds.graph.project(
    #     'companies',
    #     o1,
    #     o2,
    #     {
    #         relationshipProperties: 'freq'
    #     }
    # ) as graph
    # RETURN graph.graphName as graph
    # """
    # Run PageRank
    pagerank_query = """
    CALL gds.pageRank.stream('companies')
    YIELD nodeId, score
    WITH * ORDER BY score DESC LIMIT $limit
    RETURN gds.util.asNode(nodeId).name as company_name,
           gds.util.asNode(nodeId).id as company_id,
           score
    """
    try:
        with get_driver() as driver:
            # driver.execute_query(drop_query, database_=NEO4J_DATABASE)
            # driver.execute_query(project_query, database_=NEO4J_DATABASE)
            records, _, _ = driver.execute_query(
                pagerank_query,
                limit=limit,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error in find_influential_companies: {e}")
        return f"Error finding influential companies: {str(e)}"

async def get_investments(company: str) -> str:
    """
    Returns the investments by a company by name. 
    Returns a list of investment ids, names, and types.
    """
    query = """
    MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
    WHERE o.name = $company
    RETURN i.id as id, i.name as name, head(labels(i)) as type
    """
    mcp_result = await execute_read_query(query, {"company": company})
    if mcp_result is not None:
        return mcp_result

    try:
        with get_driver() as driver:
            records, _, _ = driver.execute_query(
                query, 
                company=company,
                database_=NEO4J_DATABASE
            )
            results = [record.data() for record in records]
            return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error executing custom tool: {e}")
        return f"Error fetching investments: {str(e)}"

async def embed_query(text: str, model: str = "text-embedding-004") -> List[float]:
    """
    Generate an embedding for a given text using Google Gemini's embedding model.
    """
    logging.info(f"Generating Gemini embedding for text using model: {model}")
    
    try:
        response = await get_vertex_client().aio.models.embed_content(
            model=model,
            contents=text
        )
        return response.embeddings[0].values
        
    except Exception as e:
        logging.error(f"Error generating Gemini embedding: {e}")
        # Fallback to a default 768-dimensional embedding in case of error
        # Note: Gemini's text-embedding-004 outputs 768 dimensions by default.
        return [0.1] * 768