#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "azure-ai-projects>=2.0.0",
#     "azure-identity",
#     "openai",
#     "python-dotenv",
#     "neo4j>=5",
# ]
# ///
"""Foundry SDK + Neo4j: investment research agent. See README.md."""

import inspect
import json
import os
import sys
from pathlib import Path
from typing import get_type_hints

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai.types.responses.response_input_param import FunctionCallOutput

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

DB = os.environ.get("NEO4J_DATABASE", "companies")
driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ.get("NEO4J_USERNAME", "companies"),
          os.environ.get("NEO4J_PASSWORD", "companies")),
)


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

def search_news(company_name: str) -> list[dict]:
    """Up to five recent articles that MENTION the company. Returns article_id for follow-up calls."""
    rows, _, _ = driver.execute_query("""
        MATCH (a:Article)-[:MENTIONS]->(:Organization {name: $name})
        RETURN a.id AS article_id, a.title AS title, a.date AS date, a.sentiment AS sentiment
        ORDER BY a.date DESC LIMIT 5
    """, name=company_name, database_=DB)
    return [r.data() for r in rows]


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


# Tool registry + helper --------------------------------------------------

TOOL_IMPLS = {
    fn.__name__: fn for fn in [
        search_companies, list_industries, companies_in_industry,
        query_company,
        analyze_relationships, people_at_company,
        search_news, articles_in_month, get_article, companies_in_article,
    ]
}

JSON_TYPE = {str: "string", int: "integer", float: "number", bool: "boolean"}


def function_tool(fn) -> FunctionTool:
    """Wrap a typed Python function as a strict-mode FunctionTool. Required-only schema."""
    hints = get_type_hints(fn)
    properties = {
        name: {"type": JSON_TYPE.get(hints.get(name, str), "string")}
        for name, param in inspect.signature(fn).parameters.items()
        if param.default is inspect.Parameter.empty
    }
    return FunctionTool(
        name=fn.__name__,
        description=fn.__doc__,
        parameters={
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
        strict=True,
    )


# Agent -------------------------------------------------------------------

INSTRUCTIONS = """\
Role: investment research analyst. Source of truth: a Neo4j knowledge graph
reached exclusively through the tools below (read-only).

Discovery
  search_companies(search)             full-text fuzzy company name search
  list_industries()                    all industry categories
  companies_in_industry(industry)      companies in a given industry

Profile
  query_company(company_name)          primary lookup — returns company_id, industries, locations, leadership

Network
  analyze_relationships(company_name)  1-2 hop org-to-org traversal (subsidiaries, suppliers, competitors, board, investors)
  people_at_company(company_id)        people and their roles at a company

News
  search_news(company_name)            recent articles mentioning the company (returns article_id)
  articles_in_month(date)              articles in the month starting at yyyy-mm-dd
  get_article(article_id)              full article body, summary, sentiment
  companies_in_article(article_id)     companies mentioned in an article

Workflow:
  1. When the user names a company, start with query_company. Cite the company_id
     so subsequent calls (people_at_company, analyze_relationships) can build on it.
  2. For peers / competitors, follow up with companies_in_industry on a returned industry.
  3. For org-to-org connections (subsidiaries, suppliers, competitors), use analyze_relationships.
  4. For people, use people_at_company with company_id.
  5. For news, use search_news; for the full read use get_article + companies_in_article with article_id.
  6. For industry-wide questions, start with list_industries.

Answer only from rows the tools return. Always cite IDs (company_id, article_id) so
follow-up questions can build on them. Never use prior knowledge — if a tool returns
nothing, reply "the graph doesn't contain that".
"""


def main() -> None:
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    if not (project_endpoint and tenant_id):
        sys.exit("Missing FOUNDRY_PROJECT_ENDPOINT or AZURE_TENANT_ID. Run microsoft-foundry/infra/deploy.sh first.")

    project = AIProjectClient(endpoint=project_endpoint, credential=AzureCliCredential(tenant_id=tenant_id))
    openai = project.get_openai_client()

    agent = project.agents.create_version(
        agent_name=os.environ.get("FOUNDRY_TEST_AGENT_NAME", "neo4j-research-agent-sdk"),
        definition=PromptAgentDefinition(
            model=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"),
            instructions=INSTRUCTIONS,
            tools=[function_tool(fn) for fn in TOOL_IMPLS.values()],
        ),
    )
    agent_ref = {"agent_reference": {"name": agent.name, "type": "agent_reference"}}

    question = os.environ.get(
        "FOUNDRY_QUESTION",
        "Tell me about Microsoft — its industry, who runs it, and where it's "
        "based. Then suggest three peers in the same industry.",
    )
    print(f"> {question}")

    try:
        response = openai.responses.create(input=question, extra_body=agent_ref)
        while True:
            outputs = []
            for item in response.output:
                if item.type == "function_call":
                    args = json.loads(item.arguments) if item.arguments else {}
                    print(f"  → {item.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                    outputs.append(FunctionCallOutput(
                        type="function_call_output",
                        call_id=item.call_id,
                        output=json.dumps(TOOL_IMPLS[item.name](**args), default=str),
                    ))
            if not outputs:
                break
            response = openai.responses.create(
                input=outputs, previous_response_id=response.id, extra_body=agent_ref,
            )
        print(f"\n{response.output_text}")
    finally:
        project.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        driver.close()


if __name__ == "__main__":
    main()
