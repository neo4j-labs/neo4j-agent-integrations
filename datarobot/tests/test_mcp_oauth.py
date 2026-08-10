"""Unit tests for the OAuth 2.0 client-credentials auth mode in mcp_client.py.

Covers the machine-to-machine auth model used by hosted Neo4j Aura MCP
endpoints -- both Aura Agents' /invoke REST API and an Aura hosted-database
MCP URL (Aura Console "Inspect" tab): dynamic token-endpoint discovery (RFC
9728 Protected Resource Metadata + OIDC discovery), token fetch, in-process
caching, expiry-based refresh, priority ordering against the other auth
modes, and graceful fallback on failure.

The discovery flow and the "hosted-database MCP endpoints require OAuth,
not Basic auth" finding below were confirmed against a real Aura
hosted-database MCP endpoint (an unauthenticated request returns 401 with
RFC 9728 discovery metadata pointing at a region-specific Auth0 tenant).
All HTTP calls in these tests are mocked with respx -- no live Aura
credentials or network access are required to run them.
"""
from __future__ import annotations

import importlib
import time

import pytest
import respx
from httpx import Response

import agent.mcp_client as mcp_client

SERVER_URL = "https://bdf4a2af.mcp-instances.neo4j.io"


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Ensure each test starts with a clean env and no cached token/discovery."""
    for var in [
        "MCP_OAUTH_CLIENT_ID",
        "MCP_OAUTH_CLIENT_SECRET",
        "MCP_OAUTH_TOKEN_URL",
        "MCP_OAUTH_SCOPE",
        "MCP_OAUTH_AUDIENCE",
        "MCP_AUTH_TOKEN",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
    ]:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(mcp_client)
    yield
    importlib.reload(mcp_client)


def _mock_discovery(respx_mock, token_url="https://aura-mcp.eu.auth0.com/oauth/token"):
    """Mock the RFC 9728 + OIDC discovery chain for SERVER_URL."""
    respx_mock.get(f"{SERVER_URL}/.well-known/oauth-protected-resource").mock(
        return_value=Response(
            200,
            json={
                "authorization_servers": ["https://aura-mcp.eu.auth0.com"],
                "bearer_methods_supported": ["header"],
                "resource": SERVER_URL,
            },
        )
    )
    respx_mock.get("https://aura-mcp.eu.auth0.com/.well-known/openid-configuration").mock(
        return_value=Response(200, json={"token_endpoint": token_url})
    )


@pytest.mark.asyncio
async def test_oauth_not_configured_returns_no_headers():
    assert not mcp_client._oauth_client_credentials_configured()
    headers = await mcp_client._auth_headers(SERVER_URL)
    assert headers == {}


@pytest.mark.asyncio
async def test_discovery_resolves_token_endpoint_and_audience(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "test-client-secret")

    with respx.mock(assert_all_called=True) as respx_mock:
        _mock_discovery(respx_mock)
        token_route = respx_mock.post("https://aura-mcp.eu.auth0.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "abc123", "expires_in": 3600})
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    assert headers == {"Authorization": "Bearer abc123"}
    body = token_route.calls[0].request.read().decode()
    assert "audience=https%3A%2F%2Fbdf4a2af.mcp-instances.neo4j.io" in body


@pytest.mark.asyncio
async def test_discovery_is_cached_across_calls(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")

    with respx.mock(assert_all_called=True) as respx_mock:
        resource_route = respx_mock.get(
            f"{SERVER_URL}/.well-known/oauth-protected-resource"
        ).mock(
            return_value=Response(
                200,
                json={
                    "authorization_servers": ["https://aura-mcp.eu.auth0.com"],
                    "resource": SERVER_URL,
                },
            )
        )
        config_route = respx_mock.get(
            "https://aura-mcp.eu.auth0.com/.well-known/openid-configuration"
        ).mock(
            return_value=Response(
                200, json={"token_endpoint": "https://aura-mcp.eu.auth0.com/oauth/token"}
            )
        )
        respx_mock.post("https://aura-mcp.eu.auth0.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "tok", "expires_in": 3600})
        )
        await mcp_client._auth_headers(SERVER_URL)
        # Force a fresh token fetch (bypassing the token cache) to prove
        # discovery itself is reused rather than re-fetched.
        mcp_client._oauth_token_cache["expires_at"] = time.time() - 1
        await mcp_client._auth_headers(SERVER_URL)

    assert resource_route.call_count == 1
    assert config_route.call_count == 1


@pytest.mark.asyncio
async def test_discovery_failure_falls_back_to_default_token_url(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")

    with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.get(f"{SERVER_URL}/.well-known/oauth-protected-resource").mock(
            return_value=Response(404)
        )
        route = respx_mock.post(mcp_client._DEFAULT_AURA_OAUTH_TOKEN_URL).mock(
            return_value=Response(200, json={"access_token": "fallback-tok", "expires_in": 3600})
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    assert route.called
    assert headers == {"Authorization": "Bearer fallback-tok"}


@pytest.mark.asyncio
async def test_explicit_token_url_skips_discovery(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://override.example.com/oauth/token")

    with respx.mock(assert_all_called=True) as respx_mock:
        # No discovery routes registered -- assert_all_called=True would fail
        # if discovery were attempted (it isn't, since MCP_OAUTH_TOKEN_URL
        # takes precedence).
        route = respx_mock.post("https://override.example.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "tok", "expires_in": 3600})
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    assert route.called
    assert headers == {"Authorization": "Bearer tok"}


@pytest.mark.asyncio
async def test_explicit_audience_overrides_discovered_resource(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_AUDIENCE", "https://custom-audience.example.com")

    with respx.mock(assert_all_called=True) as respx_mock:
        _mock_discovery(respx_mock)
        route = respx_mock.post("https://aura-mcp.eu.auth0.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "tok", "expires_in": 3600})
        )
        await mcp_client._auth_headers(SERVER_URL)

    body = route.calls[0].request.read().decode()
    assert "audience=https%3A%2F%2Fcustom-audience.example.com" in body


@pytest.mark.asyncio
async def test_oauth_token_sends_scope_when_set(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")
    monkeypatch.setenv("MCP_OAUTH_SCOPE", "mcp:read")

    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "tok", "expires_in": 3600})
        )
        await mcp_client._auth_headers(SERVER_URL)

    body = route.calls[0].request.read().decode()
    assert "grant_type=client_credentials" in body
    assert "scope=mcp%3Aread" in body


@pytest.mark.asyncio
async def test_oauth_uses_basic_auth_with_client_id_and_secret(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")

    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "tok", "expires_in": 3600})
        )
        await mcp_client._auth_headers(SERVER_URL)

    auth_header = route.calls[0].request.headers["authorization"]
    assert auth_header.startswith("Basic ")


@pytest.mark.asyncio
async def test_oauth_token_is_cached_between_calls(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")

    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "cached-tok", "expires_in": 3600})
        )
        first = await mcp_client._auth_headers(SERVER_URL)
        second = await mcp_client._auth_headers(SERVER_URL)

    assert route.call_count == 1  # token endpoint hit only once
    assert first == second == {"Authorization": "Bearer cached-tok"}


@pytest.mark.asyncio
async def test_oauth_token_refreshed_after_expiry(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")

    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.post("https://aura.example.com/oauth/token").mock(
            side_effect=[
                Response(200, json={"access_token": "tok-1", "expires_in": 1}),
                Response(200, json={"access_token": "tok-2", "expires_in": 3600}),
            ]
        )
        first = await mcp_client._auth_headers(SERVER_URL)
        # Force the cached token past its expiry/refresh-margin window.
        mcp_client._oauth_token_cache["expires_at"] = time.time() - 1
        second = await mcp_client._auth_headers(SERVER_URL)

    assert route.call_count == 2
    assert first == {"Authorization": "Bearer tok-1"}
    assert second == {"Authorization": "Bearer tok-2"}


@pytest.mark.asyncio
async def test_oauth_failure_falls_back_to_other_auth(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")

    with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(500, text="server error")
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    # OAuth fetch failed (non-fatal) -> falls back to Basic auth, agent keeps working.
    assert headers["Authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_oauth_failure_with_no_fallback_returns_empty_headers(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")

    with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(401, text="invalid client")
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    assert headers == {}


@pytest.mark.asyncio
async def test_oauth_missing_access_token_field_is_non_fatal(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")

    with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(200, json={"token_type": "bearer"})
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    assert headers == {}


@pytest.mark.asyncio
async def test_oauth_takes_priority_over_static_bearer_and_basic(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://aura.example.com/oauth/token")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "static-token")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")

    with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.post("https://aura.example.com/oauth/token").mock(
            return_value=Response(200, json={"access_token": "oauth-tok", "expires_in": 3600})
        )
        headers = await mcp_client._auth_headers(SERVER_URL)

    assert headers == {"Authorization": "Bearer oauth-tok"}


@pytest.mark.asyncio
async def test_static_bearer_still_takes_priority_over_basic(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "static-token")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")

    headers = await mcp_client._auth_headers(SERVER_URL)

    assert headers == {"Authorization": "Bearer static-token"}


@pytest.mark.asyncio
async def test_basic_auth_used_when_only_neo4j_credentials_set(monkeypatch):
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")

    headers = await mcp_client._auth_headers(SERVER_URL)

    assert headers["Authorization"].startswith("Basic ")


def test_oauth_default_token_url_is_aura_endpoint():
    assert mcp_client._DEFAULT_AURA_OAUTH_TOKEN_URL == "https://api.neo4j.io/oauth/token"
