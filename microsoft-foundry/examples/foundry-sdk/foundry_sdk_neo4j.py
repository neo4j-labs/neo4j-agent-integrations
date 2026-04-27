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
"""Foundry SDK + Neo4j: an investment research agent with three narrow function tools. See README.md."""

import json
import os
import sys
from pathlib import Path

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


def query_company(company_name: str) -> dict:
    """Profile: name, locations, industries, leadership."""
    rows, _, _ = driver.execute_query("""
        MATCH (o:Organization {name: $name})
        OPTIONAL MATCH (o)-[:HAS_CATEGORY]->(c:IndustryCategory)
        OPTIONAL MATCH (o)-[:IN_CITY]->(city:City)
        OPTIONAL MATCH (o)-[:IN_COUNTRY]->(country:Country)
        OPTIONAL MATCH (o)-[:HAS_CEO]->(ceo:Person)
        OPTIONAL MATCH (o)-[:HAS_BOARD_MEMBER]->(b:Person)
        RETURN o.name AS name,
               collect(DISTINCT c.name)[..5] AS industries,
               collect(DISTINCT city.name)[..3] + collect(DISTINCT country.name) AS locations,
               [x IN collect(DISTINCT {name: ceo.name, title: 'CEO'})
                   + collect(DISTINCT {name: b.name, title: 'Board Member'})
                 WHERE x.name IS NOT NULL][..6] AS leadership
    """, name=company_name, database_=DB)
    return rows[0].data() if rows else {}


def companies_in_industry(industry: str) -> list[dict]:
    """Up to ten companies in the given IndustryCategory."""
    rows, _, _ = driver.execute_query("""
        MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
        RETURN c.name AS name LIMIT 10
    """, industry=industry, database_=DB)
    return [r.data() for r in rows]


def search_news(company_name: str) -> list[dict]:
    """Up to five recent articles that mention the company."""
    rows, _, _ = driver.execute_query("""
        MATCH (a:Article)-[:MENTIONS]->(:Organization {name: $name})
        RETURN a.title AS title, a.date AS date, a.sentiment AS sentiment
        ORDER BY a.date DESC LIMIT 5
    """, name=company_name, database_=DB)
    return [r.data() for r in rows]


TOOL_IMPLS = {
    "query_company": query_company,
    "companies_in_industry": companies_in_industry,
    "search_news": search_news,
}


def function_tool(fn) -> FunctionTool:
    """Wrap a single-string-arg Python function as a strict-mode FunctionTool."""
    [param] = list(fn.__code__.co_varnames[: fn.__code__.co_argcount])
    return FunctionTool(
        name=fn.__name__,
        description=fn.__doc__,
        parameters={
            "type": "object",
            "properties": {param: {"type": "string"}},
            "required": [param],
            "additionalProperties": False,
        },
        strict=True,
    )


INSTRUCTIONS = """\
Role: investment research analyst. Source of truth: a Neo4j graph reached
through query_company, companies_in_industry, search_news.

Workflow:
  1. query_company first when the user names a company.
  2. For peers, pick an industry from the result and call companies_in_industry.
  3. For news, call search_news with the company name.

Answer only from rows the tools return. Never use prior knowledge. If a
tool returns nothing, reply "the graph doesn't contain that".
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
