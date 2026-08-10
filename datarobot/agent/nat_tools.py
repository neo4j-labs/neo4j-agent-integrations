"""NeMo Agent Toolkit (NAT) function registrations for the Neo4j company tools.

Addresses the DataRobot review feedback (PR #67, jpclemens0 / rabih-datarobot)
that the Neo4j tools should be usable by "any agent flavour," not just
LangChain. These wrap the exact same parameterized-Cypher implementations in
`neo4j_tools.py` (no query logic is duplicated) as native NAT `FunctionInfo`
objects, so they can be:

- referenced directly in a `workflow.yaml`'s `functions:` section, or
- exposed as an MCP server for any MCP-capable agent framework via
  `nat mcp serve --config_file agent/workflow.yaml` (NAT's built-in MCP
  front end), which is the concrete, testable version of "expose these as
  MCP tools" raised in review.

Not currently wired into `agent/workflow.yaml`'s primary `neo4j_agent`
function — that agent (see `agent/myagent.py`/`agent/register.py`) calls
`neo4j_tools.py`'s LangChain tools directly instead. These NAT-native
function registrations are kept as an optional, independently-servable
surface (e.g. `nat mcp serve`) for callers that want the Neo4j tools without
the full LangGraph agent.
"""
from __future__ import annotations

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

try:
    from . import neo4j_tools as nt
except ImportError:
    import neo4j_tools as nt  # type: ignore[no-redef]


class SearchCompaniesConfig(FunctionBaseConfig, name="neo4j_search_companies"):
    """Full-text search for companies in the Neo4j knowledge graph by name or keyword."""


class QueryCompanyProfileConfig(FunctionBaseConfig, name="neo4j_query_company_profile"):
    """Fetch a company profile including summary, industries, locations, and leadership."""


class ListIndustriesConfig(FunctionBaseConfig, name="neo4j_list_industries"):
    """List all industry categories available in the Neo4j knowledge graph."""


class CompaniesInIndustryConfig(FunctionBaseConfig, name="neo4j_companies_in_industry"):
    """Find companies that belong to a specific industry category."""


class AnalyzeCompanyRelationshipsConfig(FunctionBaseConfig, name="neo4j_analyze_company_relationships"):
    """Explore organization-to-organization relationships in the Neo4j knowledge graph."""


class PeopleAtCompanyConfig(FunctionBaseConfig, name="neo4j_people_at_company"):
    """List executives and board members at a company by its internal company_id."""


class RunCypherQueryConfig(FunctionBaseConfig, name="neo4j_run_cypher_query"):
    """Execute a raw Cypher query against the Neo4j knowledge graph."""


@register_function(config_type=SearchCompaniesConfig)
async def neo4j_search_companies(_config: SearchCompaniesConfig, _builder: Builder):
    async def _run(search: str, limit: int = 10) -> str:
        return nt.search_companies.invoke({"search": search, "limit": limit})

    yield FunctionInfo.from_fn(
        _run,
        description="Full-text search for companies in the Neo4j knowledge graph by name or keyword.",
    )


@register_function(config_type=QueryCompanyProfileConfig)
async def neo4j_query_company_profile(_config: QueryCompanyProfileConfig, _builder: Builder):
    async def _run(company_name: str) -> str:
        return nt.query_company_profile.invoke({"company_name": company_name})

    yield FunctionInfo.from_fn(
        _run,
        description=(
            "Fetch a company profile including summary, industries, locations, "
            "and leadership from the Neo4j knowledge graph."
        ),
    )


@register_function(config_type=ListIndustriesConfig)
async def neo4j_list_industries(_config: ListIndustriesConfig, _builder: Builder):
    async def _run(limit: int = 50) -> str:
        return nt.list_industries.invoke({"limit": limit})

    yield FunctionInfo.from_fn(
        _run,
        description="List all industry categories available in the Neo4j knowledge graph.",
    )


@register_function(config_type=CompaniesInIndustryConfig)
async def neo4j_companies_in_industry(_config: CompaniesInIndustryConfig, _builder: Builder):
    async def _run(industry: str) -> str:
        return nt.companies_in_industry.invoke({"industry": industry})

    yield FunctionInfo.from_fn(
        _run,
        description="Find companies that belong to a specific industry category (use list_industries first).",
    )


@register_function(config_type=AnalyzeCompanyRelationshipsConfig)
async def neo4j_analyze_company_relationships(_config: AnalyzeCompanyRelationshipsConfig, _builder: Builder):
    async def _run(company_name: str, max_depth: int = 2) -> str:
        return nt.analyze_company_relationships.invoke(
            {"company_name": company_name, "max_depth": max_depth}
        )

    yield FunctionInfo.from_fn(
        _run,
        description=(
            "Explore organization-to-organization relationships (subsidiaries, investors, "
            "competitors) in the Neo4j knowledge graph. max_depth is 1-4."
        ),
    )


@register_function(config_type=PeopleAtCompanyConfig)
async def neo4j_people_at_company(_config: PeopleAtCompanyConfig, _builder: Builder):
    async def _run(company_id: str) -> str:
        return nt.people_at_company.invoke({"company_id": company_id})

    yield FunctionInfo.from_fn(
        _run,
        description="List executives and board members at a company by its internal company_id.",
    )


@register_function(config_type=RunCypherQueryConfig)
async def neo4j_run_cypher_query(_config: RunCypherQueryConfig, _builder: Builder):
    async def _run(cypher_query: str) -> str:
        return nt.run_cypher_query.invoke({"cypher_query": cypher_query})

    yield FunctionInfo.from_fn(
        _run,
        description="Execute a raw Cypher query against the Neo4j knowledge graph and return results.",
    )
