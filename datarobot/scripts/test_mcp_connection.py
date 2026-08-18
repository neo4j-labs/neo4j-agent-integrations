#!/usr/bin/env python3
"""Standalone smoke test for the MCP client — no OpenAI key or full agent
required, just the MCP_SERVER_URL (+ auth) env vars.

Useful for quickly validating a hosted Neo4j Aura MCP connection (Aura
Agents via OAuth client-credentials, or an Aura hosted-database MCP URL from
the Console "Inspect" tab) before running the full agent end-to-end.

Usage:
    # Aura Agent (OAuth client-credentials)
    MCP_SERVER_URL=<aura-agent-mcp-endpoint> \\
    MCP_OAUTH_CLIENT_ID=<client-id> \\
    MCP_OAUTH_CLIENT_SECRET=<client-secret> \\
        python scripts/test_mcp_connection.py

    # Aura hosted database (Inspect tab URL) — also OAuth client-credentials;
    # the token endpoint is auto-discovered from the server (RFC 9728), so no
    # database username/password is needed here.
    MCP_SERVER_URL=<aura-inspect-tab-mcp-url> \\
    MCP_OAUTH_CLIENT_ID=<client-id> \\
    MCP_OAUTH_CLIENT_SECRET=<client-secret> \\
        python scripts/test_mcp_connection.py

    # Optionally call a specific tool once tools are listed:
    python scripts/test_mcp_connection.py --call get-schema --args '{}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import mcp_client  # noqa: E402  (path insert must run first)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--call", metavar="TOOL_NAME", help="Also invoke this tool after listing tools"
    )
    parser.add_argument(
        "--args", default="{}", help="JSON object of arguments for --call (default: {})"
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help=(
            "Only run RFC 9728 OAuth discovery against MCP_SERVER_URL and print the "
            "resolved token endpoint/audience, without fetching a token or listing "
            "tools. Useful to sanity-check a hosted Aura MCP URL with no OAuth "
            "credentials at hand."
        ),
    )
    args = parser.parse_args()

    if not os.environ.get("MCP_SERVER_URL"):
        print("MCP_SERVER_URL is not set — nothing to test.", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2

    if args.discover_only:
        import anyio

        server_url = os.environ["MCP_SERVER_URL"]
        print(f"Discovering OAuth metadata for: {server_url}")
        metadata = anyio.run(mcp_client._discover_oauth_metadata, server_url)  # noqa: SLF001
        if metadata is None:
            print(
                "No RFC 9728 discovery metadata found (server may not require OAuth, "
                "or doesn't publish '.well-known/oauth-protected-resource')."
            )
            return 1
        print(f"  token_url: {metadata.get('token_url')}")
        print(f"  audience:  {metadata.get('audience')}")
        return 0

    if not mcp_client._HAS_MCP:  # noqa: SLF001 — internal check, script-only use
        print(
            "The 'mcp' package is not importable in this interpreter "
            f"({sys.version.split()[0]}). It requires Python >=3.10 — "
            "run 'pip install -r requirements.txt' with a suitable interpreter.",
            file=sys.stderr,
        )
        return 2

    print(f"Connecting to MCP server: {os.environ['MCP_SERVER_URL']}")
    if mcp_client._oauth_client_credentials_configured():  # noqa: SLF001
        print("Auth mode: OAuth 2.0 client-credentials (MCP_OAUTH_CLIENT_ID/SECRET)")
    elif os.environ.get("MCP_AUTH_TOKEN"):
        print("Auth mode: static bearer token (MCP_AUTH_TOKEN)")
    elif os.environ.get("NEO4J_USERNAME") and os.environ.get("NEO4J_PASSWORD"):
        print("Auth mode: Basic auth (NEO4J_USERNAME/NEO4J_PASSWORD)")
    else:
        print("Auth mode: none (no auth env vars set)")

    tools = mcp_client.list_tools()
    if not tools:
        print(
            "\nNo tools returned. Check the WARNING logs above for the real cause "
            "(auth failure, unreachable server, wrong transport, etc.) — "
            "list_tools() fails open and returns [] rather than raising."
        )
        return 1

    print(f"\n{len(tools)} tool(s) discovered:")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description'][:100]}")

    if args.call:
        try:
            call_args = json.loads(args.args)
        except json.JSONDecodeError as exc:
            print(f"--args is not valid JSON: {exc}", file=sys.stderr)
            return 2
        print(f"\nCalling tool '{args.call}' with args {call_args} ...")
        result = mcp_client.call_tool(args.call, call_args)
        print(json.dumps(result, indent=2, default=str))
        if isinstance(result, dict) and "error" in result:
            return 1

    return 0


if __name__ == "__main__":
    logging_level = os.environ.get("LOG_LEVEL", "WARNING")
    import logging

    logging.basicConfig(level=logging_level, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
