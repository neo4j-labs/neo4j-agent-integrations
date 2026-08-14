# Neo4j Aura-hosted MCP over OAuth (DCR) — Agent Framework

Neo4j Aura ships a built-in MCP endpoint per instance
(`https://<INSTANCE_ID>.mcp-instances.neo4j.io/mcp`). It's protected by **OAuth
2.0 with Dynamic Client Registration (DCR)** — the client registers itself at
runtime, so there's no client ID or secret to paste anywhere.

That's why this path lives in Agent Framework rather than the Foundry portal: the
portal's MCP tool form requires a **static Client ID**, which a DCR-only server
doesn't issue. Here the [MCP SDK's](https://pypi.org/project/mcp/)
`OAuthClientProvider` performs the whole handshake and Agent Framework consumes
the authenticated session.

```
MCP 401 → resource metadata → authorization server
   → DCR self-registration → browser sign-in + consent → bearer token
      → MCPStreamableHTTPTool(http_client=…) → Agent
```

## Bring your own Aura instance

The sign-in is a real Neo4j Aura account (email / SSO), so the agent connects to
**your** instance — the same model as the
[Copilot Studio Aura option](../../../microsoft-copilot-studio/). Starting
fresh? [Create a free Aura instance](https://neo4j.com/docs/aura/getting-started/create-instance/),
choose the built-in **Movies** sample dataset, and
[enable its MCP endpoint](https://neo4j.com/docs/mcp/current/mcp-for-aura/). (The
public `companies` demo graph isn't reachable this way — it has no OAuth.)

## Run

The script uses [uv](https://docs.astral.sh/uv/) with inline dependencies — no
virtualenv to manage.

```bash
# Point at your Aura instance's MCP endpoint. The Foundry chat-model settings
# (project endpoint, deployment, tenant) load automatically from
# ../../../microsoft-foundry/.env, written by microsoft-foundry/infra/deploy.sh.
export NEO4J_AURA_MCP_URL="https://<INSTANCE_ID>.mcp-instances.neo4j.io/mcp"

uv run aura_mcp_oauth_agent.py
```

The **first run opens your browser** to sign in to Aura and consent. The token
is cached at `~/.neo4j-aura-mcp-oauth.json` (mode `600`), so later runs are
non-interactive. Delete that file to force re-consent.

> **Note — this is a local / developer pattern.** The sign-in uses a `localhost`
> redirect, your desktop browser, and a single local token file, so it runs where
> a person can click through consent — not inside a headless Agent API backend
> (e.g. serving a web chat client) or the Foundry hosted-agent runtime. To use
> Aura's DCR MCP behind a web app, keep this OAuth approach but move it to your
> web layer — a public redirect URI, consent in the end-user's browser session,
> and per-user token storage — by replacing the `redirect_handler`,
> `callback_handler`, and `TokenStorage` used here.

Ask your own question and the agent calls `get-schema` then `read-cypher`
against your graph:

```bash
QUESTION="Which actors have worked with the most directors?" uv run aura_mcp_oauth_agent.py
```
