# Copyright (c) Neo4j. All rights reserved.
"""Microsoft Agent Framework + Neo4j: multi-agent investment research.

Implements the multi-agent pattern from EXAMPLE_AGENT.md as a coordinator that
delegates to a Neo4j database agent and an analyst agent. Wrapped with
ResponsesHostServer for Foundry hosted-agent deployment. Self-contained on
purpose; ../multi-agent/multi_agent_neo4j.py is a parallel, near-identical file
for the local-dev runtime.
"""

import os
import shutil
from typing import Annotated
from typing import Any

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIEmbeddingClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import AzureCliCredential, ChainedTokenCredential, DefaultAzureCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from azure.identity.aio import ChainedTokenCredential as AsyncChainedTokenCredential
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pydantic import Field

load_dotenv()


def configure_demo_observability() -> None:
    """Keep demo logs readable when optional hosted-agent telemetry is unavailable."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

    if os.environ.get("ENABLE_AGENT365_OBSERVABILITY", "false").lower() not in {"1", "true", "yes", "on"}:
        os.environ["FOUNDRY_AGENT365_TRACING_ENABLED"] = "false"
        os.environ.setdefault("ENABLE_A365_OBSERVABILITY", "false")
        os.environ.setdefault("ENABLE_A365_OBSERVABILITY_EXPORTER", "false")


configure_demo_observability()

DB = os.environ.get("NEO4J_DATABASE", "companies")
driver: Any = None  # initialised in main(); tools reference it via module lookup
embeddings: Any = None  # OpenAIEmbeddingClient — initialised in main()


# Discovery ---------------------------------------------------------------

@tool(approval_mode="never_require")
def search_companies(
    search: Annotated[str, Field(description="Free-text query; matches against the entity full-text index.")],
) -> list[dict]:
    """Full-text fuzzy search for companies by name. Up to 20 ranked matches with company_id."""
    rows, _, _ = driver.execute_query("""
        CALL db.index.fulltext.queryNodes('entity', $search, {limit: 20})
        YIELD node AS c, score
        WHERE c:Organization
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary
        ORDER BY score DESC
    """, search=search, database_=DB)
    return [r.data() for r in rows]


@tool(approval_mode="never_require")
def list_industries() -> list[dict]:
    """All IndustryCategory names, alphabetical."""
    rows, _, _ = driver.execute_query("""
        MATCH (i:IndustryCategory)
        RETURN i.name AS industry
        ORDER BY i.name
    """, database_=DB)
    return [r.data() for r in rows]


@tool(approval_mode="never_require")
def companies_in_industry(
    industry: Annotated[str, Field(description="An exact IndustryCategory name (e.g. 'Software Companies').")],
) -> list[dict]:
    """Up to ten companies in the given IndustryCategory, with company_id."""
    rows, _, _ = driver.execute_query("""
        MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary
        LIMIT 10
    """, industry=industry, database_=DB)
    return [r.data() for r in rows]


# Profile -----------------------------------------------------------------

@tool(approval_mode="never_require")
def query_company(
    company_name: Annotated[str, Field(description="The company's exact name (e.g. 'Microsoft').")],
) -> dict:
    """Primary company lookup — returns company_id, name, industries, locations, leadership."""
    rows, _, _ = driver.execute_query("""
        MATCH (o:Organization {name: $name})
        OPTIONAL MATCH (o)-[:HAS_CATEGORY]->(c:IndustryCategory)
        OPTIONAL MATCH (o)-[:IN_CITY]->(city:City)
        OPTIONAL MATCH (o)-[:IN_COUNTRY]->(country:Country)
        OPTIONAL MATCH (o)-[:HAS_CEO]->(ceo:Person)
        OPTIONAL MATCH (o)-[:HAS_BOARD_MEMBER]->(b:Person)
        RETURN o.id AS company_id, o.name AS name,
               collect(DISTINCT c.name)[..5] AS industries,
               collect(DISTINCT city.name)[..3] + collect(DISTINCT country.name) AS locations,
               [x IN collect(DISTINCT {name: ceo.name, title: 'CEO'})
                   + collect(DISTINCT {name: b.name, title: 'Board Member'})
                 WHERE x.name IS NOT NULL][..6] AS leadership
    """, name=company_name, database_=DB)
    return rows[0].data() if rows else {}


# Network -----------------------------------------------------------------

@tool(approval_mode="never_require")
def analyze_relationships(
    company_name: Annotated[str, Field(description="The company's exact name.")],
) -> list[dict]:
    """1-2 hop org-to-org connections (subsidiaries, suppliers, competitors, board, investors).
    Returns connected orgs with relationship types and distance."""
    rows, _, _ = driver.execute_query("""
        MATCH path = (o1:Organization {name: $name})-[*1..2]-(o2:Organization)
        WHERE o1 <> o2
        RETURN DISTINCT o2.id AS company_id, o2.name AS organization,
               [r IN relationships(path) | type(r)] AS relationships,
               length(path) AS distance
        ORDER BY distance LIMIT 20
    """, name=company_name, database_=DB)
    return [r.data() for r in rows]


@tool(approval_mode="never_require")
def people_at_company(
    company_id: Annotated[str, Field(description="Internal company_id from query_company / search_companies.")],
) -> list[dict]:
    """People associated with a company (by company_id) and their roles (CEO, Board Member, …)."""
    rows, _, _ = driver.execute_query("""
        MATCH (c:Organization {id: $id})-[role]-(p:Person)
        RETURN replace(type(role), 'HAS_', '') AS role,
               p.name AS person_name,
               c.id AS company_id, c.name AS company_name
    """, id=company_id, database_=DB)
    return [r.data() for r in rows]


# News --------------------------------------------------------------------

@tool(approval_mode="never_require")
async def search_news(
    company_name: Annotated[str, Field(description="The company's exact name.")],
    query: Annotated[str, Field(description="Free-text query embedded for semantic similarity search over article chunks.")],
) -> list[dict]:
    """Vector-search news about a company. Embeds `query` via the Foundry embedding
    deployment (text-embedding-3-small, 1536d), then runs cosine similarity over
    Chunks restricted to articles that MENTION the company. Returns up to 5 hits
    with article_id, title, date, sentiment, the matched chunk text, and the score."""
    result = await embeddings.get_embeddings([query])
    vector = result[0].vector
    # The 'news' vector index would return top-K across ALL chunks before our
    # company filter — most of which won't mention this company. Compute cosine
    # similarity directly over the pre-filtered company-mentioning chunks
    # instead. Cheap at this scale (a few thousand chunks per major company).
    # Off-thread the sync neo4j call so we don't block the event loop while
    # the hosted server has concurrent requests in flight.
    def _query() -> list[dict]:
        rows, _, _ = driver.execute_query("""
            MATCH (a:Article)-[:MENTIONS]->(:Organization {name: $name})
            MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
            WHERE c.embedding IS NOT NULL
            WITH a, c, vector.similarity.cosine(c.embedding, $embedding) AS score
            RETURN a.id AS article_id, a.title AS title, toString(a.date) AS date,
                   a.sentiment AS sentiment, c.text AS text, score
            ORDER BY score DESC LIMIT 5
        """, name=company_name, embedding=vector, database_=DB)
        return [r.data() for r in rows]
    return await asyncio.to_thread(_query)


@tool(approval_mode="never_require")
def articles_in_month(
    date: Annotated[str, Field(description="Start of a calendar month, yyyy-mm-dd (e.g. 2022-06-01).")],
) -> list[dict]:
    """Articles in the month starting at the given yyyy-mm-dd date."""
    rows, _, _ = driver.execute_query("""
        MATCH (a:Article)
        WHERE date($date) <= date(a.date) < date($date) + duration('P1M')
        RETURN a.id AS article_id, a.author AS author, a.title AS title,
               toString(a.date) AS date, a.sentiment AS sentiment
        ORDER BY a.date DESC LIMIT 25
    """, date=date, database_=DB)
    return [r.data() for r in rows]


@tool(approval_mode="never_require")
def get_article(
    article_id: Annotated[str, Field(description="Article id from search_news / articles_in_month.")],
) -> dict:
    """Full article body, summary, sentiment, joined from chunks."""
    rows, _, _ = driver.execute_query("""
        MATCH (a:Article {id: $id})-[:HAS_CHUNK]->(c:Chunk)
        WITH a, c ORDER BY id(c) ASC
        WITH a, collect(c.text) AS contents
        RETURN a.id AS article_id, a.author AS author, a.title AS title,
               toString(a.date) AS date, a.summary AS summary,
               a.siteName AS site, a.sentiment AS sentiment,
               apoc.text.join(contents, ' ') AS content
    """, id=article_id, database_=DB)
    return rows[0].data() if rows else {}


@tool(approval_mode="never_require")
def companies_in_article(
    article_id: Annotated[str, Field(description="Article id from search_news / articles_in_month.")],
) -> list[dict]:
    """Companies mentioned in a specific article (by article_id)."""
    rows, _, _ = driver.execute_query("""
        MATCH (a:Article {id: $id})-[:MENTIONS]->(c:Organization)
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary
    """, id=article_id, database_=DB)
    return [r.data() for r in rows]


DATABASE_TOOLS = [
    search_companies,
    list_industries,
    companies_in_industry,
    query_company,
    analyze_relationships,
    people_at_company,
    search_news,
    articles_in_month,
    get_article,
    companies_in_article,
]


DATABASE_INSTRUCTIONS = """\
You are the database_agent from EXAMPLE_AGENT.md. You answer research requests
by querying the Neo4j companies knowledge graph with the available tools.

Responsibilities
  1. Resolve the target company. Use search_companies if the name is ambiguous.
  2. Gather the profile with query_company, preserving company_id.
  3. Gather industry context. Use the industries returned by query_company with
     one companies_in_industry call for the industry most relevant to the user
     request; use list_industries only if needed.
  4. Gather recent news with one search_news call.
  5. Gather relationships with one analyze_relationships call.
  6. Gather people with one people_at_company call using the company_id from
     query_company.

Output requirements
  Return only grounded data from tool results. Use one fenced ```json``` block
  per tool call, with this shape:

  {
    "tool": "<tool name>",
    "args": { ... },
    "rows": [ ... every returned field verbatim ... ]
  }

Always preserve IDs such as company_id and article_id. Do not invent facts,
short IDs, partner names, or relationship types.
Keep the demo concise: prefer 5-6 total tool calls unless the user explicitly
asks for broader exploration.
"""

ANALYST_INSTRUCTIONS = """\
You are the analyst from EXAMPLE_AGENT.md. You receive structured data from the
database_agent and synthesize it into an investment-research report.

Report structure
  Executive Summary   - 2-3 sentences with the headline finding.
  Company Profile     - industries, locations, leadership; cite company_id.
  Recent Developments - bullets with article_id, title, date, and sentiment.
  Network             - table with company_id, organization, relationships,
                        and distance when available.
  Risks & Outlook     - data-backed interpretation and what is missing.

Rules
  Use only data supplied by the database_agent. Every company_id, article_id,
  title, and relationship type must appear verbatim in the input data. If a
  section lacks supporting rows, write "(no data)" rather than filling gaps.
  Return only the report. Do not ask follow-up questions or propose extra data
  pulls unless the user requested them.
"""

COORDINATOR_INSTRUCTIONS = """\
You are the coordinator from EXAMPLE_AGENT.md. Manage two delegated agents:

  database_agent - queries the Neo4j knowledge graph for company profiles,
  industry context, news, relationships, and people. It preserves IDs.

  analyst - turns the database_agent output into an investment-research report.

For each user research request:
  1. Ask database_agent to gather all relevant graph data for the request.
  2. Pass the complete database_agent output to analyst.
  3. Return the analyst report to the user without extra preamble, commentary,
     follow-up questions, or suggested next steps.

Keep the flow simple. Do not answer from prior knowledge, and do not skip the
analyst step for investment-research prompts.
"""

# Server ------------------------------------------------------------------

def main() -> None:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

    global driver, embeddings
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USERNAME", "companies"),
              os.environ.get("NEO4J_PASSWORD", "companies")),
    )

    tenant_id = os.environ.get("AZURE_TENANT_ID")
    cli_kwargs = {"tenant_id": tenant_id} if tenant_id else {}
    if shutil.which("az"):
        credential = ChainedTokenCredential(
            AzureCliCredential(**cli_kwargs),
            DefaultAzureCredential(),
        )
        embedding_credential = AsyncChainedTokenCredential(
            AsyncAzureCliCredential(**cli_kwargs),
            AsyncDefaultAzureCredential(),
        )
    else:
        credential = DefaultAzureCredential()
        embedding_credential = AsyncDefaultAzureCredential()

    # OpenAIEmbeddingClient provides Entra ID authentication against the
    # Azure OpenAI / Foundry endpoint. See microsoft/agent-framework:
    # python/samples/02-agents/embeddings/openai_embeddings_on_azure.py
    embeddings = OpenAIEmbeddingClient(
        model=os.environ.get("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small"),
        azure_endpoint=project_endpoint.split("/api/")[0],
        credential=embedding_credential,
    )

    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    agent_options = {"store": False}

    database_agent = Agent(
        client=client,
        name="database_agent",
        description="Queries Neo4j for company profiles, news, relationships, people, and industry context.",
        instructions=DATABASE_INSTRUCTIONS,
        tools=DATABASE_TOOLS,
        default_options=agent_options,
    )
    analyst_agent = Agent(
        client=client,
        name="analyst",
        description="Synthesizes Neo4j query results into an investment-research report.",
        instructions=ANALYST_INSTRUCTIONS,
        default_options=agent_options,
    )
    coordinator = Agent(
        client=client,
        name="coordinator",
        instructions=COORDINATOR_INSTRUCTIONS,
        tools=[
            database_agent.as_tool(
                name="database_agent",
                description="Gather grounded company, news, relationship, people, and industry data from Neo4j.",
                arg_name="task",
                arg_description="Specific graph data to gather for the research request.",
            ),
            analyst_agent.as_tool(
                name="analyst",
                description="Synthesize database_agent output into the final investment-research report.",
                arg_name="data",
                arg_description="Complete structured output returned by database_agent.",
            ),
        ],
        default_options=agent_options,
    )

    try:
        ResponsesHostServer(coordinator).run()
    finally:
        driver.close()


if __name__ == "__main__":
    main()
