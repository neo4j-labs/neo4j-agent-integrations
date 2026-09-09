"""Local MCP integration for CrewAI agents.

The official ``neo4j-mcp-server`` runs as a local stdio subprocess. Its tools
are discovered at startup and exposed to CrewAI as regular ``BaseTool``
instances.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import sysconfig
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

try:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


def get_local_mcp_command() -> str | None:
    """Return the configured local MCP command, if local MCP is enabled."""
    command = os.environ.get("MCP_SERVER_COMMAND", "").strip()
    return command or None


def is_mcp_enabled() -> bool:
    """Check whether a local MCP stdio command has been configured."""
    return get_local_mcp_command() is not None


def _local_mcp_environment() -> dict[str, str]:
    """Build the local Neo4j MCP server environment from integration settings."""
    environment = dict(os.environ)
    setting_pairs = {
        "NEO4J_MCP_URI": "NEO4J_URI",
        "NEO4J_MCP_USERNAME": "NEO4J_USERNAME",
        "NEO4J_MCP_PASSWORD": "NEO4J_PASSWORD",
        "NEO4J_MCP_DATABASE": "NEO4J_DATABASE",
    }
    for mcp_setting, integration_setting in setting_pairs.items():
        if not environment.get(mcp_setting) and environment.get(integration_setting):
            environment[mcp_setting] = environment[integration_setting]

    environment.setdefault("NEO4J_MCP_READ_ONLY", "true")
    environment.setdefault("NEO4J_TELEMETRY", "false")
    return environment


def _server_parameters(command: str) -> StdioServerParameters:
    """Parse a configured local MCP command into stdio server parameters."""
    command_parts = shlex.split(command)
    if not command_parts:
        raise ValueError("MCP_SERVER_COMMAND must contain an executable command.")
    executable = command_parts[0]
    if not os.path.dirname(executable):
        executable = shutil.which(executable) or str(
            Path(sysconfig.get_path("scripts")) / executable
        )
    return StdioServerParameters(
        command=executable,
        args=command_parts[1:],
        env=_local_mcp_environment(),
    )


async def _async_list_mcp_tools(command: str) -> list[dict[str, Any]]:
    """Start the configured local server and list its available tools."""
    if not _HAS_MCP:
        raise RuntimeError(
            "Local MCP support requires the 'mcp' extra. Install with: pip install -e '.[mcp]'"
        )

    async with (
        stdio_client(_server_parameters(command)) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools_result = await session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for tool in tools_result.tools
        ]


async def _async_call_mcp_tool(
    command: str, tool_name: str, arguments: dict[str, Any]
) -> str:
    """Start the configured local server and invoke a specific tool."""
    if not _HAS_MCP:
        raise RuntimeError(
            "Local MCP support requires the 'mcp' extra. Install with: pip install -e '.[mcp]'"
        )

    async with (
        stdio_client(_server_parameters(command)) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(tool_name, arguments=arguments)
        content = [item.text for item in result.content if hasattr(item, "text")]
        return "\n".join(content) if content else json.dumps(result.model_dump())


class DynamicMCPToolInput(BaseModel):
    """Dynamic input container for local MCP tools."""

    arguments: str = Field(default="{}", description="JSON string containing MCP tool arguments.")


class DynamicMCPTool(BaseTool):
    """CrewAI tool wrapper that dispatches to a local MCP stdio subprocess."""

    name: str = "mcp_tool"
    description: str = "Execute a local MCP tool."
    server_command: str = ""
    target_tool_name: str = ""

    def _run(self, **kwargs: Any) -> str:
        arguments = kwargs
        if "arguments" in kwargs and len(kwargs) == 1:
            try:
                arguments = json.loads(kwargs["arguments"])
            except json.JSONDecodeError as error:
                return f"Invalid MCP tool arguments: {error.msg}"

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                _async_call_mcp_tool(self.server_command, self.target_tool_name, arguments)
            )

        raise RuntimeError(
            "DynamicMCPTool cannot run from an active event loop. "
            "Run the CrewAI workflow from a synchronous context."
        )


def load_mcp_tools(command: str | None = None) -> list[BaseTool]:
    """Discover tools from the configured local MCP server."""
    local_command = command or get_local_mcp_command()
    if not local_command:
        return []

    tools_metadata = asyncio.run(_async_list_mcp_tools(local_command))
    return [
        DynamicMCPTool(
            name=f"mcp_{metadata['name']}",
            description=f"[MCP] {metadata.get('description') or metadata['name']}",
            server_command=local_command,
            target_tool_name=metadata["name"],
        )
        for metadata in tools_metadata
    ]
