#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     # The meta-package "agent-framework" ships an empty __init__.py that
#     # shadows -core's exports — so we depend on the split packages directly.
#     "agent-framework-core>=1.7.0",
#     "agent-framework-foundry>=1.7.0",
#     "agent-framework-openai>=1.7.0",  # OpenAIEmbeddingClient (Entra-ID)
#     "aiohttp",  # azure-ai-projects async transport
#     "azure-identity",
#     "python-dotenv",
#     "neo4j>=5",
# ]
# ///
"""Microsoft Agent Framework + Neo4j: multi-agent investment research, run locally.

Implements the multi-agent pattern from EXAMPLE_AGENT.md as a coordinator that
delegates to a Neo4j database agent and an analyst agent. Self-contained on
purpose; foundry-hosted/main.py is a parallel, near-identical file packaged for
the Foundry hosted-agent runtime.
"""

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from agent_framework import Agent, AgentContext, FunctionInvocationContext
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIEmbeddingClient
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[3] / "microsoft-foundry" / ".env", override=True)

DB = os.environ.get("NEO4J_DATABASE", "companies")
driver: Any = None  # initialised in main(); tools reference it via module lookup
embeddings: Any = None  # OpenAIEmbeddingClient — initialised in main()


# Discovery ---------------------------------------------------------------

def search_companies(search: str) -> list[dict]:
    """Full-text fuzzy search for companies by name. Up to 20 ranked matches with company_id."""
    rows, _, _ = driver.execute_query("""
        CALL db.index.fulltext.queryNodes('entity', $search, {limit: 20})
        YIELD node AS c, score
        WHERE c:Organization
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary
        ORDER BY score DESC
    """, search=search, database_=DB)
    return [r.data() for r in rows]


def list_industries() -> list[dict]:
    """All IndustryCategory names, alphabetical."""
    rows, _, _ = driver.execute_query("""
        MATCH (i:IndustryCategory)
        RETURN i.name AS industry
        ORDER BY i.name
    """, database_=DB)
    return [r.data() for r in rows]


def companies_in_industry(industry: str) -> list[dict]:
    """Up to ten companies in the given IndustryCategory, with company_id."""
    rows, _, _ = driver.execute_query("""
        MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary
        LIMIT 10
    """, industry=industry, database_=DB)
    return [r.data() for r in rows]


# Profile -----------------------------------------------------------------

def query_company(company_name: str) -> dict:
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

def analyze_relationships(company_name: str) -> list[dict]:
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


def people_at_company(company_id: str) -> list[dict]:
    """People associated with a company (by company_id) and their roles (CEO, Board Member, …)."""
    rows, _, _ = driver.execute_query("""
        MATCH (c:Organization {id: $id})-[role]-(p:Person)
        RETURN replace(type(role), 'HAS_', '') AS role,
               p.name AS person_name,
               c.id AS company_id, c.name AS company_name
    """, id=company_id, database_=DB)
    return [r.data() for r in rows]


# News --------------------------------------------------------------------

async def search_news(company_name: str, query: str) -> list[dict]:
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
    # the agent has other tool calls in flight.
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


def articles_in_month(date: str) -> list[dict]:
    """Articles in the month starting at the given yyyy-mm-dd date."""
    rows, _, _ = driver.execute_query("""
        MATCH (a:Article)
        WHERE date($date) <= date(a.date) < date($date) + duration('P1M')
        RETURN a.id AS article_id, a.author AS author, a.title AS title,
               toString(a.date) AS date, a.sentiment AS sentiment
        ORDER BY a.date DESC LIMIT 25
    """, date=date, database_=DB)
    return [r.data() for r in rows]


def get_article(article_id: str) -> dict:
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


def companies_in_article(article_id: str) -> list[dict]:
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


# Middleware --------------------------------------------------------------

async def log_agent(context: AgentContext, call_next: Callable[[], Awaitable[None]]) -> None:
    """Log which agent is invoked, with a short preview of the input."""
    name = context.agent.name or "?"
    last = context.messages[-1].text if context.messages else ""
    preview = (last[:80] + "…") if len(last) > 80 else last
    print(f"  [agent={name}] {preview}")
    await call_next()


async def log_tool(context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]) -> None:
    """Log every tool invocation (name + args)."""
    args = ", ".join(f"{k}={v!r}" for k, v in (context.arguments or {}).items())
    print(f"    → {context.function.name}({args})")
    await call_next()


# Agent instructions ------------------------------------------------------

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

# Entry -------------------------------------------------------------------

async def main() -> None:
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    neo4j_uri = os.environ.get("NEO4J_URI")
    embedding_deployment = os.environ.get("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small")
    if not (project_endpoint and tenant_id and neo4j_uri):
        sys.exit(
            "Missing FOUNDRY_PROJECT_ENDPOINT, AZURE_TENANT_ID, or NEO4J_URI. "
            "Run microsoft-foundry/infra/deploy.sh first."
        )

    # Foundry account base URL: strip the /api/projects/<project> path off the project endpoint.
    # OpenAIEmbeddingClient routes /openai/deployments/<model>/embeddings under it.
    account_endpoint = project_endpoint.split("/api/")[0]

    global driver, embeddings
    driver = GraphDatabase.driver(
        neo4j_uri,
        auth=(os.environ.get("NEO4J_USERNAME", "companies"),
              os.environ.get("NEO4J_PASSWORD", "companies")),
    )
    embed_credential = AsyncAzureCliCredential(tenant_id=tenant_id)
    try:
        # OpenAIEmbeddingClient is the canonical agent-framework path for Entra-ID
        # auth against an Azure OpenAI / Foundry endpoint (FoundryEmbeddingClient
        # is API-key only and won't work with disableLocalAuth=true accounts).
        # See microsoft/agent-framework: python/samples/02-agents/embeddings/openai_embeddings_on_azure.py
        embeddings = OpenAIEmbeddingClient(
            model=embedding_deployment,
            azure_endpoint=account_endpoint,
            credential=embed_credential,
        )

        client = FoundryChatClient(
            project_endpoint=project_endpoint,
            model=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-5-mini"),
            credential=AzureCliCredential(tenant_id=tenant_id),
        )

        agent_options = {"store": False}

        database_agent = Agent(
            client=client,
            middleware=[log_agent, log_tool],
            name="database_agent",
            description="Queries Neo4j for company profiles, news, relationships, people, and industry context.",
            instructions=DATABASE_INSTRUCTIONS,
            tools=DATABASE_TOOLS,
            default_options=agent_options,
        )
        analyst_agent = Agent(
            client=client,
            middleware=[log_agent, log_tool],
            name="analyst",
            description="Synthesizes Neo4j query results into an investment-research report.",
            instructions=ANALYST_INSTRUCTIONS,
            default_options=agent_options,
        )
        coordinator = Agent(
            client=client,
            middleware=[log_agent],
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

        question = os.environ.get(
            "FOUNDRY_QUESTION",
            "Research Microsoft's position in the software industry. Gather company "
            "profile, recent news, and key relationships, then synthesize an "
            "investment outlook.",
        )
        print(f"> {question}\n")
        result = await coordinator.run(question)
        print(result)
    finally:
        await embed_credential.close()
        driver.close()


if __name__ == "__main__":
    asyncio.run(main())
