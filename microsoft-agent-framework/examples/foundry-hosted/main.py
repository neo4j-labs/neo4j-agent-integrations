# Copyright (c) Neo4j. All rights reserved.
"""Microsoft Agent Framework + Neo4j: multi-agent investment research,
packaged as a Foundry hosted agent.

Implements the multi-agent spec from EXAMPLE_AGENT.md — Coordinator delegates
to a Database Agent (10 typed Neo4j function tools) and an Analyst Agent
(synthesis only). Wrapped with ResponsesHostServer for Foundry hosted-agent
deployment. Self-contained on purpose; ../multi-agent/multi_agent_neo4j.py
is a parallel, near-identical file for the local-dev runtime.
"""

import asyncio
import os
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIEmbeddingClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pydantic import Field

load_dotenv()

DB = os.environ.get("NEO4J_DATABASE", "companies")
driver = None  # initialised in main(); tools reference it via module lookup
embeddings = None  # OpenAIEmbeddingClient — initialised in main()


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
    search_companies, list_industries, companies_in_industry,
    query_company,
    analyze_relationships, people_at_company,
    search_news, articles_in_month, get_article, companies_in_article,
]


# Agent instructions ------------------------------------------------------

DATABASE_INSTRUCTIONS = """\
You are a data-access agent over a Neo4j knowledge graph of companies (Organization),
people (Person), industries (IndustryCategory), locations (City, Country), and
articles (Article). Other agents call you to fetch facts.

Tools (read-only):
  Discovery: search_companies, list_industries, companies_in_industry
  Profile:   query_company
  Network:   analyze_relationships, people_at_company
  News:      search_news (vector — needs a query string), articles_in_month, get_article, companies_in_article

Output protocol — STRICT, machine-readable
  Your reply is consumed by another agent, not a human. Output ONE fenced
  ```json``` block per tool call you made, with this exact shape:

    ```json
    {
      "tool": "<tool name>",
      "args": { ... what you passed in ... },
      "rows": [ ... the tool result, verbatim, every field ... ]
    }
    ```

  Rules
  • Include EVERY field the tool returned — `company_id`, `article_id`, `title`,
    `date`, `sentiment`, `relationships`, `distance`, `industries`, `locations`,
    `leadership`, etc. Real IDs look like `EIsFKrN_ZNLSWsvxdQfWutQ` and
    `ART11195006745`; never shorten or substitute.
  • If a tool returns no rows, set `"rows": []`.
  • No prose. No summary. No headings. Only the JSON blocks, one per call.
  • Never reason from prior knowledge — the only valid content is what the
    tools returned this turn.
"""

ANALYST_INSTRUCTIONS = """\
You are an investment-research analyst. Your input is one or more ```json```
blocks the database agent gathered. Each block has `tool`, `args`, and `rows`.
Synthesize a concise investment-research report from those rows — and only
those rows.

Report structure
  Executive Summary   — 2-3 sentences with the headline finding.
  Company Profile     — industries, locations, leadership; one short paragraph.
                        Cite the `company_id` once.
  Recent Developments — bullet list. Each bullet MUST start with the real
                        `article_id` from the rows, then the `title`, `date`,
                        and `sentiment`.
  Network             — Markdown table with columns: `company_id`,
                        `organization`, `relationships`, `distance` — copied
                        from the rows verbatim.
  Risks & Outlook     — what the data suggests, and what's missing.

Rules — STRICT, no exceptions
  • Every `company_id`, `article_id`, `title`, and relationship type in your
    report must appear verbatim in the input rows. Real IDs look like
    `EIsFKrN_ZNLSWsvxdQfWutQ` and `ART11195006745`.
  • If you find yourself writing a short numeric ID like "101" or "201", or a
    generic name ("Strategic Partner", "AWS partnership") that isn't in the
    rows, STOP — that is hallucination. Re-read the JSON blocks.
  • If a section has no supporting rows, write "(no data)" — never pad.
  • Insight is welcome in Risks & Outlook only, and only insight that follows
    directly from the rows.
"""

COORDINATOR_INSTRUCTIONS = """\
You orchestrate investment research. You delegate to two specialists:

  database_agent — fetches rows from the graph. Returns one or more
                   ```json``` blocks per call, each with `tool`, `args`,
                   and `rows`.
  analyst        — turns those JSON blocks into an investment-research report.

Workflow
  1. Call `database_agent` once per facet: company profile, peers, recent
     news, relationships, key people. Each call should be a focused request
     like "query_company('Microsoft')" or
     "companies_in_industry('Software Companies')".
  2. CONCATENATE every `database_agent` response verbatim into one string
     and pass that string as the `task` to `analyst`. The analyst MUST see
     the raw JSON blocks — never strip them down to bare IDs or summaries.
  3. Return the analyst's report verbatim — don't paraphrase or re-summarize.

Never query the graph yourself. Never write the report yourself. Faithful
relaying is your job.
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

    # Single sync DefaultAzureCredential reused by both clients. Sync is fine
    # here — both clients accept TokenCredential | AsyncTokenCredential, and
    # the sync variant has no async session to leak across the long-running
    # ResponsesHostServer process.
    credential = DefaultAzureCredential()

    # OpenAIEmbeddingClient is the canonical agent-framework path for Entra-ID
    # auth against an Azure OpenAI / Foundry endpoint. See microsoft/agent-framework:
    # python/samples/02-agents/embeddings/openai_embeddings_on_azure.py
    embeddings = OpenAIEmbeddingClient(
        model=os.environ.get("FOUNDRY_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small"),
        azure_endpoint=project_endpoint.split("/api/")[0],
        credential=credential,
    )

    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Names match EXAMPLE_AGENT.md — `database_agent`, `analyst`,
    # `coordinator` — so the trace and instructions read consistently
    # across the spec, the code, and the model's tool-call surface.
    database_agent = Agent(
        client=client,
        name="database_agent",
        instructions=DATABASE_INSTRUCTIONS,
        tools=DATABASE_TOOLS,
    )
    analyst_agent = Agent(
        client=client,
        name="analyst",
        instructions=ANALYST_INSTRUCTIONS,
    )
    coordinator = Agent(
        client=client,
        name="coordinator",
        instructions=COORDINATOR_INSTRUCTIONS,
        tools=[
            database_agent.as_tool(
                name="database_agent",
                description="Fetch company / news / relationship / people rows from the Neo4j graph. Returns JSON blocks with raw rows.",
                arg_name="task",
                arg_description="What to fetch — be specific (which company, what aspect).",
            ),
            analyst_agent.as_tool(
                name="analyst",
                description="Synthesize JSON rows from `database_agent` into an investment-research report.",
                arg_name="task",
                arg_description="Concatenated JSON blocks the database agent returned, plus the analysis goal.",
            ),
        ],
        # The Foundry hosting infrastructure manages conversation history;
        # don't double-persist on the OpenAI Responses side.
        default_options={"store": False},
    )

    try:
        ResponsesHostServer(coordinator).run()
    finally:
        driver.close()


if __name__ == "__main__":
    main()
