"""CrewAI adapters for the repository's reusable custom Neo4j tools."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_CUSTOM_TOOL_METADATA = {
    "query_company": "Retrieve a company's locations, industries, and leadership. Arguments: company_name.",
    "search_news": "Search company news using the graph vector index. Arguments: company_name, query, limit.",
    "analyze_relationships": "Analyze organization relationships. Arguments: company_name, max_depth.",
    "list_industries": "List industry categories. Arguments: none.",
    "companies_in_industry": "Find companies in an industry. Arguments: industry.",
    "search_companies": "Search companies by name. Arguments: search.",
    "articles_in_month": "List articles published in a month. Arguments: date (YYYY-MM-DD).",
    "get_article": "Retrieve an article and its full text. Arguments: article_id.",
    "companies_in_article": "List organizations mentioned by an article. Arguments: article_id.",
    "people_at_company": "List people and roles for an organization. Arguments: company_id.",
    "find_influential_companies": "Rank companies with PageRank. Arguments: limit.",
    "get_investments": "List investments for an organization. Arguments: company.",
}


class CustomToolInput(BaseModel):
    """JSON arguments passed to a reusable custom tool."""

    arguments: str = Field(
        default="{}",
        description="A JSON object containing the arguments documented by the selected custom tool.",
    )


class CustomNeo4jTool(BaseTool):
    """Adapt an async shared custom tool for synchronous CrewAI execution."""

    name: str = "custom_neo4j_tool"
    description: str = "Execute a reusable custom Neo4j tool."
    target_tool_name: str
    args_schema: type[BaseModel] = CustomToolInput

    def _run(self, arguments: str = "{}") -> str:
        try:
            parameters = json.loads(arguments)
        except json.JSONDecodeError as error:
            return json.dumps({"error": f"Invalid custom tool arguments: {error.msg}"})
        if not isinstance(parameters, dict):
            return json.dumps({"error": "Custom tool arguments must be a JSON object."})

        try:
            import custom_tools
        except ImportError as error:
            raise RuntimeError(
                "Custom tools are enabled but unavailable. "
                "Install them with: pip install -e ../custom_tools"
            ) from error

        handler = getattr(custom_tools, self.target_tool_name)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(handler(**parameters))

        raise RuntimeError(
            "CustomNeo4jTool cannot run from an active event loop. "
            "Run the CrewAI workflow from a synchronous context."
        )


def get_custom_tools() -> list[BaseTool]:
    """Return CrewAI wrappers for every installed shared custom tool."""
    if importlib.util.find_spec("custom_tools") is None:
        raise RuntimeError(
            "Shared custom tools are unavailable. Install the repository dependencies with: "
            "pip install -r requirements.txt"
        )

    return [
        CustomNeo4jTool(
            name=f"custom_{tool_name}",
            description=f"[Custom Neo4j] {description}",
            target_tool_name=tool_name,
        )
        for tool_name, description in _CUSTOM_TOOL_METADATA.items()
    ]
