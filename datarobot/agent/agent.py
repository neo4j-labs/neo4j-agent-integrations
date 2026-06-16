from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable

from neo4j import GraphDatabase
from openai import OpenAI

try:
    from .helpers import build_agent_messages, empty_usage, merge_usage
    from . import mcp_client
except ImportError:
    from helpers import build_agent_messages, empty_usage, merge_usage  # type: ignore[no-redef]
    import mcp_client  # type: ignore[no-redef]

SYSTEM_PROMPT = """You are an industry research agent with access to a Neo4j company news knowledge graph.

Use the available tools whenever you need facts about companies, industries, relationships, people, and recent articles.
Ground every answer in tool results from this session. When useful, produce concise Markdown with sections such as:
- Executive Summary
- Company Profile
- Recent Developments
- Organizational Network
- Risks / Opportunities

If the user asks for a broad research brief, combine multiple tools before answering.
"""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]


class Neo4jResearchAgent:
    def __init__(
        self,
        model: str | None = None,
        embedding_model: str | None = None,
        max_steps: int | None = None,
    ) -> None:
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.embedding_model = (
            embedding_model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        )
        self.max_steps = max_steps or int(os.environ.get("AGENT_MAX_TOOL_STEPS", "6"))
        self.database = os.environ.get("NEO4J_DATABASE", "companies")

        # OPENAI_BASE_URL lets this agent run against any OpenAI-compatible endpoint
        # (e.g. DataRobot's own LLM proxy, Azure OpenAI, local servers).
        openai_kwargs: dict = {"api_key": os.environ["OPENAI_API_KEY"]}
        base_url = os.environ.get("OPENAI_BASE_URL")
        if base_url:
            openai_kwargs["base_url"] = base_url
        self.client = OpenAI(**openai_kwargs)
        self.driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        self.tools = self._build_tools()
        self._load_mcp_tools()
        self.tool_index = {tool.name: tool for tool in self.tools}

    def close(self) -> None:
        self.driver.close()

    def _run_query(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(query, database_=self.database, **params)
        return [record.data() for record in records]

    def search_companies(self, search: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._run_query(
            """
            CALL db.index.fulltext.queryNodes('entity', $search, {limit: $limit})
            YIELD node AS c, score
            WHERE c:Organization
            RETURN c.id AS company_id, c.name AS name, c.summary AS summary, score
            ORDER BY score DESC
            """,
            search=search,
            limit=limit,
        )

    def list_industries(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._run_query(
            """
            MATCH (i:IndustryCategory)
            RETURN i.name AS industry
            ORDER BY industry
            LIMIT $limit
            """,
            limit=limit,
        )

    def companies_in_industry(self, industry: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._run_query(
            """
            MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
            RETURN c.id AS company_id, c.name AS name, c.summary AS summary
            ORDER BY c.name
            LIMIT $limit
            """,
            industry=industry,
            limit=limit,
        )

    def query_company(self, company_name: str) -> dict[str, Any]:
        rows = self._run_query(
            """
            MATCH (o:Organization {name: $name})
            OPTIONAL MATCH (o)-[:HAS_CATEGORY]->(c:IndustryCategory)
            OPTIONAL MATCH (o)-[:IN_CITY]->(city:City)
            OPTIONAL MATCH (city)-[:IN_COUNTRY]->(country:Country)
            OPTIONAL MATCH (o)-[:HAS_CEO]->(ceo:Person)
            OPTIONAL MATCH (o)-[:HAS_BOARD_MEMBER]->(board:Person)
            RETURN o.id AS company_id,
                   o.name AS name,
                   o.summary AS summary,
                   collect(DISTINCT c.name)[..5] AS industries,
                   collect(DISTINCT city.name)[..3] + collect(DISTINCT country.name)[..3] AS locations,
                   [person IN collect(DISTINCT {name: ceo.name, title: 'CEO'})
                          + collect(DISTINCT {name: board.name, title: 'Board Member'})
                    WHERE person.name IS NOT NULL][..8] AS leadership
            LIMIT 1
            """,
            name=company_name,
        )
        return rows[0] if rows else {}

    def analyze_relationships(self, company_name: str, max_depth: int = 2) -> list[dict[str, Any]]:
        depth = max(1, min(int(max_depth), 4))
        return self._run_query(
            f"""
            MATCH path = (o1:Organization {{name: $name}})-[*1..{depth}]-(o2:Organization)
            WHERE o1 <> o2
            RETURN DISTINCT o2.id AS company_id,
                   o2.name AS organization,
                   [rel IN relationships(path) | type(rel)] AS relationships,
                   length(path) AS distance
            ORDER BY distance, organization
            LIMIT 20
            """,
            name=company_name,
        )

    def people_at_company(self, company_id: str) -> list[dict[str, Any]]:
        return self._run_query(
            """
            MATCH (c:Organization {id: $company_id})-[role]-(p:Person)
            RETURN replace(type(role), 'HAS_', '') AS role,
                   p.name AS person_name,
                   c.id AS company_id,
                   c.name AS company_name
            ORDER BY role, person_name
            """,
            company_id=company_id,
        )

    def search_news(self, company_name: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        embedding = self.client.embeddings.create(
            model=self.embedding_model,
            input=query,
        ).data[0].embedding
        return self._run_query(
            """
            MATCH (a:Article)-[:MENTIONS]->(:Organization {name: $name})
            MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
            WHERE c.embedding IS NOT NULL
            WITH a, c, vector.similarity.cosine(c.embedding, $embedding) AS score
            RETURN a.id AS article_id,
                   a.title AS title,
                   toString(a.date) AS date,
                   a.sentiment AS sentiment,
                   c.text AS text,
                   score
            ORDER BY score DESC
            LIMIT $limit
            """,
            name=company_name,
            embedding=embedding,
            limit=limit,
        )

    def articles_in_month(self, date: str, limit: int = 25) -> list[dict[str, Any]]:
        return self._run_query(
            """
            MATCH (a:Article)
            WHERE date($date) <= date(a.date) < date($date) + duration('P1M')
            RETURN a.id AS article_id,
                   a.author AS author,
                   a.title AS title,
                   toString(a.date) AS date,
                   a.sentiment AS sentiment
            ORDER BY a.date DESC
            LIMIT $limit
            """,
            date=date,
            limit=limit,
        )

    def get_article(self, article_id: str) -> dict[str, Any]:
        rows = self._run_query(
            """
            MATCH (a:Article {id: $article_id})-[:HAS_CHUNK]->(c:Chunk)
            WITH a, c ORDER BY id(c) ASC
            RETURN a.id AS article_id,
                   a.author AS author,
                   a.title AS title,
                   toString(a.date) AS date,
                   a.summary AS summary,
                   a.siteName AS site,
                   a.sentiment AS sentiment,
                   collect(c.text) AS chunks
            LIMIT 1
            """,
            article_id=article_id,
        )
        if not rows:
            return {}
        row = rows[0]
        row["content"] = " ".join(row.pop("chunks", []))
        return row

    def companies_in_article(self, article_id: str) -> list[dict[str, Any]]:
        return self._run_query(
            """
            MATCH (a:Article {id: $article_id})-[:MENTIONS]->(c:Organization)
            RETURN c.id AS company_id, c.name AS name, c.summary AS summary
            ORDER BY c.name
            """,
            article_id=article_id,
        )

    @staticmethod
    def _make_mcp_func(tool_name: str) -> Callable[..., Any]:
        def _call(**kwargs: Any) -> Any:
            return mcp_client.call_tool(tool_name, kwargs)
        return _call

    def _load_mcp_tools(self) -> None:
        """Fetch tools from MCP server (if MCP_SERVER_URL is set) and append them."""
        self._mcp_tool_names: set[str] = set()
        mcp_tool_defs = mcp_client.list_tools()
        for t in mcp_tool_defs:
            name = t.get("name", "")
            if not name or name in self.tool_index:
                continue
            schema = t.get("inputSchema") or {}
            self.tools.append(ToolDefinition(
                name=name,
                description=t.get("description", ""),
                parameters=schema,
                func=self._make_mcp_func(name),
            ))
            self._mcp_tool_names.add(name)
        if self._mcp_tool_names:
            import logging as _log
            _log.getLogger(__name__).info(
                "Loaded %d MCP tools from %s: %s",
                len(self._mcp_tool_names),
                os.environ.get("MCP_SERVER_URL", ""),
                ", ".join(sorted(self._mcp_tool_names)),
            )

    def _build_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_companies",
                description="Full-text company lookup when the user gives a partial or approximate company name.",
                parameters={
                    "type": "object",
                    "properties": {
                        "search": {"type": "string", "description": "Company search text."},
                        "limit": {"type": "integer", "description": "Maximum results.", "default": 10},
                    },
                    "required": ["search"],
                },
                func=self.search_companies,
            ),
            ToolDefinition(
                name="list_industries",
                description="List known industry categories from the Neo4j graph.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum results.", "default": 50},
                    },
                },
                func=self.list_industries,
            ),
            ToolDefinition(
                name="companies_in_industry",
                description="Find companies that belong to a specific IndustryCategory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "industry": {"type": "string", "description": "Exact industry category name."},
                        "limit": {"type": "integer", "description": "Maximum results.", "default": 10},
                    },
                    "required": ["industry"],
                },
                func=self.companies_in_industry,
            ),
            ToolDefinition(
                name="query_company",
                description="Fetch a company profile including summary, industries, locations, and leadership.",
                parameters={
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string", "description": "Exact company name."},
                    },
                    "required": ["company_name"],
                },
                func=self.query_company,
            ),
            ToolDefinition(
                name="analyze_relationships",
                description="Explore 1-2 hop organization relationships such as subsidiaries, investors, or competitors.",
                parameters={
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string", "description": "Exact company name."},
                        "max_depth": {"type": "integer", "description": "Maximum graph depth.", "default": 2},
                    },
                    "required": ["company_name"],
                },
                func=self.analyze_relationships,
            ),
            ToolDefinition(
                name="people_at_company",
                description="List people connected to a company by its company_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "company_id": {"type": "string", "description": "The internal company_id field."},
                    },
                    "required": ["company_id"],
                },
                func=self.people_at_company,
            ),
            ToolDefinition(
                name="search_news",
                description="Semantic news search over chunks mentioning a company.",
                parameters={
                    "type": "object",
                    "properties": {
                        "company_name": {"type": "string", "description": "Exact company name."},
                        "query": {"type": "string", "description": "Free-text search query to embed."},
                        "limit": {"type": "integer", "description": "Maximum results.", "default": 5},
                    },
                    "required": ["company_name", "query"],
                },
                func=self.search_news,
            ),
            ToolDefinition(
                name="articles_in_month",
                description="Fetch articles published during the month beginning at yyyy-mm-dd.",
                parameters={
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Month start date in yyyy-mm-dd format."},
                        "limit": {"type": "integer", "description": "Maximum results.", "default": 25},
                    },
                    "required": ["date"],
                },
                func=self.articles_in_month,
            ),
            ToolDefinition(
                name="get_article",
                description="Retrieve a full article body and metadata by article_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "article_id": {"type": "string", "description": "Article id from a previous tool result."},
                    },
                    "required": ["article_id"],
                },
                func=self.get_article,
            ),
            ToolDefinition(
                name="companies_in_article",
                description="List organizations mentioned in an article by article_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "article_id": {"type": "string", "description": "Article id from a previous tool result."},
                    },
                    "required": ["article_id"],
                },
                func=self.companies_in_article,
            ),
        ]

    def _openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self.tools
        ]

    def run(self, completion_create_params: dict[str, Any]) -> tuple[str, dict[str, int]]:
        messages = build_agent_messages(SYSTEM_PROMPT, completion_create_params)
        usage = empty_usage()

        for _ in range(self.max_steps):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self._openai_tools(),
                tool_choice="auto",
                temperature=0.2,
            )
            merge_usage(usage, response.usage)
            message = response.choices[0].message

            assistant_message: dict[str, Any] = {"role": "assistant"}
            if message.content:
                assistant_message["content"] = message.content
            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    tool_call.model_dump() for tool_call in message.tool_calls
                ]
            messages.append(assistant_message)

            if not message.tool_calls:
                final_text = message.content or "No response generated."
                return final_text, usage

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments or "{}")
                if tool_name in self._mcp_tool_names:
                    result = mcp_client.call_tool(tool_name, arguments)
                else:
                    tool = self.tool_index[tool_name]
                    result = tool.func(**arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        raise RuntimeError(
            f"Agent exceeded the configured tool-call budget ({self.max_steps} steps)."
        )
