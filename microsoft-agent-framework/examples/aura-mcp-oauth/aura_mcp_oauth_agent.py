# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "agent-framework-core>=1.13",
#     "agent-framework-foundry>=1.10",
#     "mcp>=1.24,<2",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///
"""Microsoft Agent Framework + Neo4j Aura-hosted MCP over OAuth (DCR).

The Aura-hosted MCP endpoint is protected by OAuth 2.0 with Dynamic Client
Registration (DCR): there is no client ID to paste anywhere. The client
discovers the authorization server from the endpoint's 401 response, registers
itself at runtime, and drives a PKCE authorization-code flow. This is the path
the Foundry portal MCP form can't express (it requires a static client ID), so
we do it in code and hand the authenticated MCP session to Agent Framework.

Flow the first time you run this:
  MCP 401 -> resource metadata -> authorization server (Auth0)
    -> DCR self-registration -> browser sign-in + consent -> bearer token

The token is cached under your home directory, so consent happens only once.

The sign-in is a real Neo4j Aura account (email / SSO), so you connect the agent
to your own Aura instance. Create a free one with the built-in Movies sample
dataset (https://neo4j.com/docs/aura/getting-started/create-instance/) and enable
its MCP endpoint (https://neo4j.com/docs/mcp/current/mcp-for-aura/).

Run it (uv reads the inline dependencies above; the Foundry chat-model settings
load automatically from microsoft-foundry/.env, written by deploy.sh):

    export NEO4J_AURA_MCP_URL="https://<INSTANCE_ID>.mcp-instances.neo4j.io/mcp"
    uv run aura_mcp_oauth_agent.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import webbrowser
from contextlib import AsyncExitStack
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

# Loopback address the DCR client registers as its OAuth redirect URI. It only
# needs to be reachable by your own browser during sign-in.
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

# How long to wait for the browser sign-in before giving up.
CONSENT_TIMEOUT_SECONDS = 300

# The shared Foundry env written by microsoft-foundry/infra/deploy.sh, located
# relative to this file so `uv run` works from any directory.
SHARED_ENV = Path(__file__).resolve().parents[3] / "microsoft-foundry" / ".env"

INSTRUCTIONS = """You are a data analyst grounded in a Neo4j graph. You can only learn
about the graph through the get-schema and read-cypher tools (both read-only) —
never from prior knowledge.

Call get-schema once to discover the labels and relationships, then use
read-cypher for every factual claim and answer only from the rows it returns.
If a query returns nothing, say so. Use modern Cypher (`WHERE x IS NOT NULL`)
and project stable identifiers (`id`/`name`) so follow-up questions can build on
the results."""

# Works against any graph. For the Movies sample, try e.g.
# "Which actors have worked with the most directors?"
DEFAULT_QUESTION = (
    "Explore the graph: call get-schema, then use read-cypher to summarize what "
    "kinds of entities and relationships it contains and give one concrete example."
)


class FileTokenStorage(TokenStorage):
    """Persist the DCR client registration and tokens so consent is a one-time step.

    Written to the user's home directory (not the repo) because it holds bearer
    tokens. Delete the file to force re-registration and re-consent.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> dict:
        if self._path.exists():
            return json.loads(self._path.read_text())
        return {}

    def _save(self, data: dict) -> None:
        # Write 0o600 from creation, then atomically replace — the file holds
        # bearer tokens, so never leave it world-readable or half-written.
        tmp = self._path.with_name(self._path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self._path)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._load().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._load()
        data["tokens"] = tokens.model_dump(mode="json")
        self._save(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._load().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._load()
        data["client_info"] = client_info.model_dump(mode="json")
        self._save(data)


async def _redirect_handler(authorization_url: str) -> None:
    """Open the authorization server's sign-in page in the user's browser."""
    print("\nOpening your browser to sign in to Neo4j Aura...")
    print(f"If it doesn't open, visit:\n  {authorization_url}\n")
    webbrowser.open(authorization_url)


async def _callback_handler() -> tuple[str, str | None]:
    """Run a one-shot loopback server to catch the OAuth redirect and return (code, state)."""
    captured: dict[str, str | None] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server API)
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            # Ignore stray requests (e.g. /favicon.ico) — only the redirect to
            # our callback path with a code (or error) completes the flow.
            if parsed.path != CALLBACK_PATH or not (params.get("code") or params.get("error")):
                self.send_response(404)
                self.end_headers()
                return
            captured["code"] = params.get("code", [None])[0]
            captured["state"] = params.get("state", [None])[0]
            captured["error"] = params.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h3>Sign-in complete. You can close this tab.</h3>")
            done.set()

        def log_message(self, *_args) -> None:  # silence request logging
            pass

    # Bind in this thread so a port-in-use error surfaces here instead of being
    # swallowed in the background thread (which would hang forever on the wait).
    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), Handler)
    server.timeout = 1  # let the loop re-check `done`/deadline even without traffic

    def serve() -> None:
        deadline = time.monotonic() + CONSENT_TIMEOUT_SECONDS
        try:
            while not done.is_set() and time.monotonic() < deadline:
                server.handle_request()
        finally:
            server.server_close()

    await asyncio.to_thread(serve)
    if captured.get("error"):
        raise RuntimeError(f"OAuth sign-in failed: {captured['error']}")
    if not captured.get("code"):
        raise RuntimeError(
            f"No OAuth callback received within {CONSENT_TIMEOUT_SECONDS}s — "
            "the sign-in wasn't completed."
        )
    return captured["code"], captured.get("state")


def _build_oauth(mcp_url: str) -> OAuthClientProvider:
    cache = Path.home() / ".neo4j-aura-mcp-oauth.json"
    return OAuthClientProvider(
        server_url=mcp_url,
        client_metadata=OAuthClientMetadata(
            client_name="Neo4j Aura MCP - Agent Framework sample",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",  # public client + PKCE
        ),
        storage=FileTokenStorage(cache),
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )


async def main() -> None:
    # Load the Foundry chat-model settings from the shared .env by path (so
    # `uv run` works from any directory). Anything already exported wins.
    load_dotenv(SHARED_ENV)

    mcp_url = os.environ.get("NEO4J_AURA_MCP_URL")
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    if not (mcp_url and project_endpoint and tenant_id):
        sys.exit(
            "Missing NEO4J_AURA_MCP_URL, FOUNDRY_PROJECT_ENDPOINT, or AZURE_TENANT_ID.\n"
            "Set NEO4J_AURA_MCP_URL to your Aura MCP endpoint (…/mcp). The Foundry\n"
            f"values come from {SHARED_ENV} — run microsoft-foundry/infra/deploy.sh\n"
            "first, or export them yourself."
        )

    chat_client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-5-mini"),
        credential=AzureCliCredential(tenant_id=tenant_id),
    )

    async with AsyncExitStack() as stack:
        # An httpx client carrying the OAuth provider as its auth flow
        # (OAuthClientProvider is an httpx.Auth). The provider performs DCR + the
        # PKCE sign-in on the first request — i.e. when the tool below connects
        # and initializes the session.
        http_client = await stack.enter_async_context(
            httpx.AsyncClient(
                auth=_build_oauth(mcp_url),
                timeout=httpx.Timeout(60.0),
                follow_redirects=True,
            )
        )
        neo4j_mcp = await stack.enter_async_context(
            MCPStreamableHTTPTool(name="neo4j-aura", url=mcp_url, http_client=http_client)
        )

        agent = Agent(
            client=chat_client,
            name="neo4j-research-agent",
            instructions=INSTRUCTIONS,
            tools=[neo4j_mcp],
            default_options={"store": False},
        )

        question = os.environ.get("QUESTION", DEFAULT_QUESTION)
        print(f"> {question}\n")
        print(await agent.run(question))


if __name__ == "__main__":
    asyncio.run(main())
