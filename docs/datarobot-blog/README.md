# Teaching DataRobot to Think in Graphs: A Memory-Enabled Neo4j Agent, and the Lessons That Rebuilt It

*What we actually learned wiring a Neo4j knowledge-graph agent into a partner platform we don't fully control — memory, MCP, four competing deployment paths that we eventually tore down to one, and the mistakes that taught us the most.*

> **Update:** this post originally documented four parallel deployment paths (Lesson 1 below). After a DataRobot engineer reviewed the PR a second time, we ripped that out and rebuilt on DataRobot's own official agent template instead — that story, plus a clear-text-logging security bug CodeQL caught along the way, is now [Lesson 8](#lesson-8-when-the-platform-hands-you-an-official-template-use-it-dont-evolve-your-own) and [Lesson 9](#lesson-9-a-log-statement-can-leak-a-secret-even-without-printing-it) at the end. The earlier lessons are left intact because the mistakes (and what they taught us) were real, even though the architecture they describe has since been replaced.

---

## Why this project exists

DataRobot lets you deploy arbitrary Python "custom models" and, more recently, full agentic workflows, as production-grade endpoints with autoscaling, monitoring, and governance built in. Neo4j is where a lot of enterprises already keep their most valuable *connected* data — organizations, people, relationships, supply chains, fraud rings, knowledge graphs.

Put those two together and you get something genuinely useful: an LLM agent that can reason over live graph data, running on infrastructure an enterprise already trusts. That's what this integration delivers — a **Neo4j-backed research agent that runs inside DataRobot**, with tool-calling, cross-session memory, and pluggable external tools via MCP.

![High-level architecture: a user request flows through DataRobot's runtime into the agent, which optionally consults memory, calls Neo4j and MCP tools, then returns an answer](diagrams/overview.png)

**What's in this picture:** a chat request lands on whichever DataRobot runtime is hosting the agent (DRUM, the agent-application template, the Workload API, or NAT — more on that shortly). The runtime hands the request to the same `Neo4jResearchAgent` core regardless of which one it is. That core does three things in order: it asks the **Memory** layer (NAMS) for relevant context from past conversations, if configured; it runs its tool-calling loop against **Neo4j** and any connected **MCP** servers to gather facts; and it returns a normal OpenAI-shaped chat completion. Memory and MCP sit off to the side deliberately — they're consulted, not required, which is the point of Lesson 3 below.

At the core of all of this sits one deceptively simple function. Everything else in this post is really commentary on the lessons we learned building the scaffolding *around* it:

```python
def chat(completion_create_params: dict, model: str | None = None) -> dict:
    for key in RUNTIME_PARAMETER_KEYS:
        maybe_set_env_from_runtime_parameters(key)

    selected_model = completion_create_params.get("model") or os.environ.get(
        "OPENAI_MODEL", "gpt-4o-mini",
    )

    # 1. Pull relevant context from Agent Memory (NAMS), if configured
    session_id = mem.session_id_from_params(completion_create_params)
    user_message = _latest_user_message(completion_create_params)
    memory_context = mem.get_context(user_message, session_id)

    # 2. Run the Neo4j tool-calling agent
    agent = Neo4jResearchAgent(model=selected_model)
    try:
        result, usage = agent.run(completion_create_params)
    finally:
        agent.close()

    # 3. Persist this turn back to memory for future sessions
    mem.save_turn(session_id, user_message, result)

    return to_custom_model_response(result, usage, selected_model)
```

Get context → run the agent → save the turn. That three-line shape is the whole product. The rest of this post is what it took to make that shape *actually work* in production, across four different ways DataRobot lets you deploy code.

---

## Lesson 1: Design for the platform you're on to change under you

We didn't set out to build four deployment paths. We built one — a classic DRUM custom model (`custom.py` with `load_model()`/`chat()`) — and then DataRobot's own deployment story evolved *during* the project. DRUM-based custom models are being phased out in favor of newer mechanisms, and the DataRobot team reviewing our PR asked us to also support their newer agent template and the Workload API.

The lesson that stuck: **don't couple your core logic to any one platform's deployment shape.** Because `Neo4jResearchAgent` and the tool implementations were already factored out from `custom.py`, adding new transports meant writing thin wrappers, not rewriting the agent:

![Four deployment paths — A (DRUM), B (agent-application template), C (Workload API / Cloud Run), D (NeMo Agent Toolkit) — all wrapping the same core Neo4j agent logic](diagrams/paths.png)

**What's in this picture:** four independent entry points, all converging on the same `Neo4jResearchAgent` box in the middle. Nothing about the agent's tool-calling logic, Cypher queries, or memory handling changes based on which path is active — only the outermost layer (how a request physically arrives and how a response is physically returned) differs. That's why a fix made once, like the Cypher parameterization in Lesson 4, is automatically present in all four paths instead of needing to be reapplied four times.

- **Path A — DRUM custom model.** The original shape: `custom.py`'s `load_model()`/`chat()`, deployed via DRUM.
- **Path B — `datarobot-agent-application` template.** DataRobot's own LangGraph-based scaffolding (`myagent.py`), for teams that want to stay inside DataRobot's opinionated agent framework.
- **Path C — Workload API.** A plain container (FastAPI + Dockerfile) deployed as a managed, autoscaling workload via REST API — no DRUM runtime at all. This is the one we also stood up as a public demo on Google Cloud Run.
- **Path D — NeMo Agent Toolkit (NAT).** Because DRUM custom models are on a deprecation path, we added a fourth option: a declarative `workflow.yaml` plus thin tool wrappers, giving us a config-driven workflow and the ability to host the same tools as their own MCP server.

The FastAPI wrapper for Path C is a good example of how thin these transport layers can stay if the core logic is properly separated out:

```python
# agent/server.py — reuses custom.py::chat() unchanged; only the transport differs
from .custom import chat as run_chat, load_model

app = FastAPI()
load_model(code_dir=str(Path(__file__).parent))

@app.get("/readyz")
def readyz():
    return {"status": "ready"}

@app.post("/v1/chat/completions")
def chat_completions(body: dict):
    return run_chat(body)
```

Four transports, one brain. Every fix we made to Cypher safety, memory handling, or tool-call error handling automatically applied to all four paths, because none of them re-implement the agent — they call into it.

---

## Lesson 2: Read the actual protocol, not your assumption of it

We integrated [Neo4j Agent Memory (NAMS)](https://github.com/neo4j-labs/agent-memory) so the agent remembers past conversations across sessions — even a brand-new DataRobot deployment. The interface is simple on paper:

```python
memory_context = mem.get_context(user_message, session_id)
# ... run the agent with memory_context injected as a system message ...
mem.save_turn(session_id, user_message, result)
```

But "simple on paper" hid a protocol detail that only became visible once we traced an actual conversation end-to-end:

![Sequence diagram: the agent looks up a local session key in its cache; on a cache miss it calls NAMS POST /conversations, which always returns a fresh server-assigned UUID regardless of any client-supplied id, and the agent caches that mapping before fetching context and saving the turn](diagrams/memory-flow.png)

**What's in this picture:** three participants — the DataRobot agent, a small local cache, and the NAMS memory API. On every turn, the agent first checks its local cache for a mapping from its own session key to a real NAMS conversation ID. If it's a cache miss (first turn of a new session), the agent calls NAMS to create a conversation — and NAMS's response is the only source of truth for what that conversation's real ID is, regardless of anything the client sent. The agent stores that real ID locally so every subsequent turn in the same session reuses it correctly. Only after that resolution step does the normal `get_context` / run agent / `save_turn` sequence happen. Skipping the resolution step — which is what our first implementation did — silently created a brand-new, disconnected conversation on every single turn instead of one continuous conversation.

The lesson came from what's *underneath* that simple call. Our first implementation assumed we could pick our own conversation ID client-side and use it consistently. We were wrong — NAMS's `POST /conversations` **ignores whatever id you pass** and always mints a fresh server-side UUID. We only found this by reading the actual TypeScript SDK that had just been merged into `agent-memory`, not by guessing at the API shape from documentation. The fix was to keep a small local cache mapping our own session key to the real, server-assigned UUID:

```python
async def _resolve_conversation_id(client, local_key: str) -> str:
    """Map our local session key to a real NAMS conversation UUID, creating one if needed."""
    cache = _load_conversation_cache()
    if local_key in cache:
        return cache[local_key]

    conv = await client.short_term.create_conversation(local_key, user_identifier=local_key)
    cache[local_key] = str(conv.id)
    _save_conversation_cache(cache)
    return cache[local_key]
```

The broader lesson: **when you integrate against someone else's service, the source of truth is the actual request/response contract their SDK implements, not the mental model you built from the README.** We also decided that a silently swallowed memory failure is worse than a visible one — if the memory API is unreachable or misconfigured, the agent still works, but it now logs a clear warning instead of quietly degrading with no signal at all.

---

## Lesson 3: Optional features should be *provably* optional

Both Memory and MCP are designed so that if you don't configure them, the agent behaves exactly as it did before either existed — no crashes, no missing imports, no partial states:

```python
try:
    from neo4j_agent_memory import MemoryClient
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

def get_context(user_message: str, session_id: str) -> str:
    if not _HAS_MEMORY or not os.environ.get("MEMORY_API_KEY"):
        return ""  # silent no-op — the agent works exactly as before
    ...
```

The same pattern holds for [MCP](https://modelcontextprotocol.io/) — the agent can connect to *any* MCP server (the NAMS memory server, the official Neo4j MCP server, or a fully custom one), and those tools become indistinguishable from the built-in Neo4j tools to the tool-calling loop:

```python
class MCPToolClient:
    async def list_tools(self) -> list[dict]:
        """Discover tools once at startup. Returns [] if unreachable — never raises."""
        if not self._server_url:
            return []
        try:
            async with self._session() as session:
                result = await session.list_tools()
                return [self._to_openai_tool(t) for t in result.tools]
        except Exception as exc:
            logger.warning("MCP list_tools failed (non-fatal): %s", exc)
            return []
```

Put together, the graceful-degradation path for both features looks like this:

![Flowchart: at agent startup, if MEMORY_API_KEY is unset, get_context silently returns an empty string; if set, the agent calls NAMS and falls back to an empty context with a logged warning on error. In parallel, if MCP_SERVER_URL is unset, list_tools returns an empty list; if set, the agent discovers MCP tools and falls back to an empty tool list with a logged warning on error. Either way, the Neo4j Research Agent runs](diagrams/optional-features-flow.png)

**What's in this picture:** two parallel decision trees that both terminate at the same place — "the agent runs regardless." For memory: no API key means an instant, silent empty string, no network call attempted at all. An API key that's set but fails at runtime (wrong key, unreachable host) logs a warning and still returns an empty context rather than raising. For MCP: the same two-track logic applies to tool discovery — no server URL means an empty tool list immediately; a configured-but-unreachable server logs a warning and falls back to an empty list rather than crashing startup. Both trees are symmetrical on purpose: an operator should never be able to tell, from the agent's behavior alone, whether a feature was "not configured" or "configured but failing," except by checking the logs — and either way, the core Neo4j functionality is unaffected.

This is the same symmetry that makes Path D interesting: because NeMo Agent Toolkit can host our own Neo4j tools *as* an MCP server (`nat mcp serve`), the exact same tool implementations can act as either an MCP **client** (pulling in someone else's tools) or an MCP **server** (exposing our tools to someone else's agent). The lesson generalizes well beyond this project: **an integration that degrades gracefully when a dependency is absent is far more valuable than one that assumes the dependency is always there.** Every optional feature in this codebase was tested by deliberately *not* configuring it, not just by configuring it correctly.

---

## Lesson 4: Trust boundaries deserve as much attention as functionality

The most important thing we found during review wasn't a missing feature — it was a security bug hiding inside working code. Several tool functions built Cypher queries by interpolating user-controlled arguments directly into the query text:

```python
# Before — vulnerable to Cypher injection via the `search` argument
query = f"""
    CALL db.index.fulltext.queryNodes('entity', '{search}', {{limit: {limit}}})
    YIELD node AS c, score
    RETURN c.name AS name, score
"""
```

It ran fine on every normal input we threw at it in development — which is exactly the trap. Naive string-escaping isn't a defense; it's a false sense of one. The fix was to route every user-controlled value through Neo4j's native query parameters instead of the query text:

```python
# After — the search term can never alter query structure, no matter what it contains
query = """
    CALL db.index.fulltext.queryNodes('entity', $search, {limit: $limit})
    YIELD node AS c, score
    RETURN c.name AS name, score
"""
graph.query(query, params={"search": search, "limit": safe_limit})
```

![Flowchart: user input crosses a trust boundary; the before-fix path built query text via string interpolation, so adversarial input like x' OR 1=1 could alter query structure; the after-fix path passes the same input as a query parameter, so the query text stays static and any input, however adversarial, is treated as an inert literal value](diagrams/cypher-trust-boundary.png)

**What's in this picture:** the same user-controlled input taking two different paths through the same trust boundary. On the left branch (the bug), that input becomes part of the query's *text* — so anything shaped like Cypher syntax inside it changes what the query actually does. On the right branch (the fix), the input never touches the query text at all; it's handed to the driver separately as a named parameter, and Neo4j's own parser guarantees a parameter value can only ever be interpreted as a value, never as syntax. The diagram is really the entire security lesson in one picture: everything to the left of "trust boundary" is attacker-controlled, and the only safe designs are ones where attacker-controlled data can never influence the shape of what runs on the right.

We verified the fix against actual adversarial payloads (`x' OR 1=1 //`, `x'}) DETACH DELETE n //`) run through the live tool — each is now treated as inert literal search text rather than altering the query. The one case Cypher genuinely can't parameterize is a variable-length relationship depth (`-[*1..N]-`), which we instead coerce to an integer and clamp to a safe range before use.

**The lesson**: code review that only asks "does this work" will pass code like the vulnerable version above every time, because it *does* work — for well-behaved input. The question that actually matters is "what happens on adversarial input," and that question has to be asked explicitly, not left to hope.

---

## Lesson 5: A feature that silently does nothing is worse than one that errors

One of the quieter bugs we found: `OPENAI_BASE_URL` — used to point the agent at an LLM gateway or Azure OpenAI instead of the public OpenAI API — was declared as a configurable field in DataRobot's runtime parameter schema, and the deployment UI happily let you set it. But the internal list DRUM uses to actually copy runtime parameters into the process environment didn't include it:

```python
# The bug: OPENAI_BASE_URL was declared in model-metadata.yaml and read
# by the agent, but missing from the list DRUM copies into the environment.
RUNTIME_PARAMETER_KEYS = (
    "OPENAI_API_KEY", "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
    "NEO4J_DATABASE", "MEMORY_API_KEY", "MCP_SERVER_URL",
    # "OPENAI_BASE_URL" — missing. Setting it in the DataRobot UI did nothing.
)
```

Someone could set that field in the deployment UI, deploy successfully, see no errors anywhere, and simply... not get the behavior they configured. That's a uniquely hard class of bug to notice, because nothing fails — it just quietly doesn't do what the UI implies it does. The fix was one line, but finding it required cross-checking every field declared in the deployment schema against the code path that actually consumes it, not just testing the fields we remembered to test.

---

## Lesson 6: A dependency pin is a promise you have to keep

The most instructive bug of this whole project didn't come from a code review — it came from a colleague saying "it's not working" some time after the PR had already merged. Going back and re-testing from a clean environment (rather than trusting that "it worked before" still meant "it works now") surfaced a real, 100%-reproducible problem in Path D: `requirements-nat.txt` pinned a version range for `nvidia-nat` that was **impossible to install**, because the underlying `datarobot-genai[dragent]` package hard-requires a different exact version:

```
# Before — unsatisfiable; pip's resolver fails with ResolutionImpossible
nvidia-nat>=1.8.0

# After — pinned to the version datarobot-genai[dragent] actually requires
nvidia-nat==1.7.0
```

Anyone following the README from scratch would have hit a wall of dependency-resolver errors before running a single line of agent code. That lines up uncomfortably well with "it's not working" — and it's the kind of failure that's invisible to the original author, because their local environment already had the dependency resolved from before the conflict existed.

**The lesson**: "it worked when I built it" and "it works, reproducibly, for a stranger following the README from a clean environment months later" are two different bars, and the gap between them is exactly where dependency pins quietly rot. The only way to catch that gap is to periodically re-test the whole surface area from zero — not just re-run the parts someone reported as broken.

---

## Lesson 7: Test the deployment story, not just the code

Testing locally proves the logic works. It doesn't prove the integration is usable by someone who isn't sitting at your terminal. So the last part of this project was standing up a real, publicly reachable deployment of Path C on Google Cloud Run:

![Deployment flow: gcloud CLI builds via Cloud Build into Artifact Registry, deploys to Cloud Run with secrets from Secret Manager, and serves Bearer-token-authenticated requests that call out to Neo4j, OpenAI, and NAMS](diagrams/deployment.png)

**What's in this picture:** the same container image traveling through three managed Google Cloud services before it ever handles a real request. Cloud Build compiles the Dockerfile and pushes the resulting image to Artifact Registry; Cloud Run pulls that image and runs it as an autoscaling, HTTPS-terminated service, injecting secrets (API keys, database passwords) from Secret Manager as environment variables rather than baking them into the image; and every inbound request must carry a Google-issued identity token that Cloud Run's own IAM layer verifies before the container ever sees the request. From there, the container talks outward to Neo4j, OpenAI, and NAMS exactly as it would in any other environment — none of those three integration points know or care that they're being called from Cloud Run instead of DataRobot.

```bash
# Build and push the same Dockerfile used for DataRobot's Workload API —
# it needed zero changes to also run on Cloud Run
gcloud builds submit --tag us-central1-docker.pkg.dev/PROJECT/agent/neo4j-datarobot-agent

gcloud run deploy neo4j-datarobot-agent \
  --image us-central1-docker.pkg.dev/PROJECT/agent/neo4j-datarobot-agent \
  --no-allow-unauthenticated \
  --set-secrets OPENAI_API_KEY=openai-key:latest,NEO4J_PASSWORD=neo4j-pwd:latest

# Every request needs a Google-issued identity token
TOKEN=$(gcloud auth print-identity-token)
curl -s https://neo4j-datarobot-agent-xxxxx.us-central1.run.app/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"messages":[{"role":"user","content":"What companies are in the AI industry?"}]}'
```

The deliberate choices here matter as much as the code itself: secrets came from Secret Manager rather than plaintext env vars, authentication was Bearer-token-only via Cloud Run's own IAM layer rather than any custom auth code, and — because the container already spoke plain HTTP with no DRUM dependency — the exact same Dockerfile used for DataRobot's own Workload API worked on Cloud Run completely unmodified. **The lesson**: designing the container to not assume anything DataRobot-specific about its runtime environment is what made a second, independent hosting target basically free.

---

## Lesson 8: When the platform hands you an official template, use it — don't evolve your own

The "four deployment paths" story above was, in hindsight, the wrong instinct. We built each path to survive whatever DataRobot's shifting deployment story threw at us next — DRUM, then an agent-application template, then a raw Workload API container, then NeMo Agent Toolkit — and that adaptability felt like a strength right up until a DataRobot engineer reviewed the PR again and said, bluntly, that it wasn't:

> "This still contains a lot of leftovers of deprecated architecture, and there are essentially 3 different agents implemented... Rather than evolving this, use the template we provide (`af-component-agent`), and apply Neo4j specifics onto it: tools and memory. Otherwise I can't guarantee it will work in DataRobot."

That was the correct call, and it stung a little precisely because it was correct. `agent.py`/`custom.py` (DRUM), `myagent.py` (LangGraph, unregistered), and `workflow.yaml` (NAT-native) had each been built to *look* like the future at different points in the project, but only one of them was actually wired end-to-end into DataRobot's `dragent` runtime — the other two were live-but-disconnected code that a fresh reader had no way to tell apart from the real path. Flexibility we'd engineered as a hedge against platform churn had quietly become three unfinished agents instead of one finished one.

The fix wasn't a patch — it was starting from DataRobot's own [`af-component-agent`](https://github.com/datarobot-community/af-component-agent) template and grafting the Neo4j-specific pieces (tools, memory, MCP client) onto its scaffolding, rather than the other way around:

```python
# agent/register.py -- the one true entry point, wired into DataRobot's dragent runtime
@register_per_user_function
def neo4j_agent() -> Neo4jAgentConfig:
    # Registers this agent with NAT so dragent can route requests to it.
    return Neo4jAgentConfig(
        name="neo4j_agent",
        description="Neo4j knowledge-graph research agent with memory and MCP tools",
    )
```

Everything downstream — the LangGraph `planner_node`/`writer_node` loop in `myagent.py`, the seven Neo4j tools, the NAMS-backed memory editor, the OAuth-aware MCP client — now hangs off this single registration point instead of being spread across three parallel, only-one-of-which-is-real implementations:

![Consolidated architecture: a request enters via DataRobot's dragent runtime, is registered through NAT's register.py, and flows into a single LangGraph agent (myagent.py) that binds Neo4j tools and optional MCP tools before returning a DRAgentEventResponse](diagrams/template-architecture.png)

**What's in this picture:** one path, not four. A request authenticated by `datarobot_api_key` hits the `dragent_fastapi` front end, passes through DataRobot's own moderation and OpenTelemetry middleware, and lands on `neo4j_agent()` — the single function NAT's registration system knows about. From there it instantiates `MyAgent`, whose `planner_node` binds the seven Neo4j tools *and* any configured MCP tools (including a hosted Neo4j Aura MCP server) to the LLM in one native tool-calling loop, before a `writer_node` formats the final Markdown report and NAT wraps it back into a `DRAgentEventResponse`. Memory is still there, still optional, still symmetric with the MCP path — but it's now a single `nat_memory.py` module wrapped by NAT's own `MemoryEditor` interface rather than a bespoke wrapper reimplemented per deployment path.

The lesson generalizes past this one PR: **when the platform owner publishes an official scaffold, that scaffold is a stronger signal about "how this platform actually wants to be integrated with" than anything you can infer from documentation or your own working code.** Three plausible-looking implementations that a reviewer can't tell apart is a worse deliverable than one implementation that's obviously the only one — even if the three represent more total engineering effort. We kept the multi-path *thinking* (design the core logic so it doesn't care about its transport), we just stopped building the transports ourselves once an official one existed.

---

## Lesson 9: A log statement can leak a secret even without printing it

The last finding came from GitHub's own CodeQL scanner, not a human reviewer — two "clear-text logging of sensitive information" alerts on the OAuth token-fetch path our MCP client uses to authenticate against a hosted Neo4j Aura MCP server. The flagged code didn't look dangerous at a glance:

```python
# Before -- CodeQL flags both of these as clear-text logging, even though
# neither line prints a token, a password, or the client secret directly
except httpx.HTTPError as exc:
    logger.warning("OAuth token request failed: %s", exc)   # (1) logs the exception object
    ...
if "access_token" not in payload:
    logger.error("Token response missing access_token: keys=%s", list(payload.keys()))  # (2) logs only key names
```

Neither line logs a secret value. Line (1) logs an exception object; line (2) logs a list of JSON key names, not the values behind them. Our first reaction was that this looked like a false positive — until we understood what CodeQL is actually tracking. It doesn't scan for secret-shaped strings in your log calls; it does taint tracking on the data flowing into them. Both `exc` and `payload` were produced by a call that carried a client secret (`client.post(token_url, data=data, auth=(client_id, client_secret))`), so anything derived from that call — including an exception's string representation, or a dictionary's key list, both of which could under some code path leak fragments of the request or response — is tainted for the rest of its life, regardless of what it superficially "contains."

The fix wasn't to escape or truncate anything; it was to stop passing tainted objects to the logger at all, and use only values that are structurally guaranteed to carry no data from the secret-bearing call:

```python
# After -- logs carry zero data derived from the tainted OAuth response
except httpx.HTTPError as exc:
    logger.warning("OAuth token request failed: %s", type(exc).__name__)  # class name only, e.g. "ConnectError"
    ...
if "access_token" not in payload:
    logger.error("Token response missing access_token field")  # static string, no payload data at all
```

`type(exc).__name__` is a hardcoded string that ships with the `httpx` library itself — it can never contain anything an attacker (or an accidental secret) put into the request or response. A fixed log message needs no data from `payload` at all, because the only thing worth logging here is *that* the field was missing, not what else was present instead.

**The lesson**: "does this log statement print a secret" is the wrong question to ask when reviewing your own logging code — the right question is "did any value in this log statement originate, however many steps removed, from a call that also carried a secret." If the answer is yes, the only reliably safe fix is to stop passing that value (or anything derived from it) to the logger, full stop — not to redact it, hash it, or log "part of" it. Tools like CodeQL are worth taking at face value here even when the flagged line looks harmless on a human read, because the taint-tracking model catches a category of leak (secrets reachable through a logged object, not contained in it) that manual review consistently misses.

---

## What we'd tell the DataRobot team

If there's one honest takeaway from this whole project, it's this: **we built and tested as much as we possibly could with the information and access we had, then used the DataRobot team's own review feedback as the mechanism to close the remaining gaps** — rather than guessing at internals of a platform we don't fully control. The Cypher injection fix, the broken runtime parameter, the dependency pin bug, the clear-text-logging alert, and ultimately the decision to rebuild on DataRobot's own `af-component-agent` template instead of our own scaffolding were all found (or made) because we kept re-testing and re-listening from a stranger's-eye view, not because we assumed our own familiarity with the code was enough. The final architecture isn't the one we designed on day one — it's the one that survived three rounds of "here's what's actually wrong with this," which is exactly how an integration into a platform you don't own is supposed to go.

---

## Try it yourself

The whole integration — one consolidated agent built on DataRobot's official template, live tool-calling over Neo4j, cross-session memory via NAMS, hosted Neo4j Aura MCP support, and the security hardening above — is documented and open source.

- **Main repository**: [neo4j-labs/neo4j-agent-integrations](https://github.com/neo4j-labs/neo4j-agent-integrations)
- **DataRobot integration source**: [`datarobot/` directory](https://github.com/neo4j-labs/neo4j-agent-integrations/tree/agents/datarobot-neo4j-integration/datarobot) — the consolidated agent, setup instructions, and architecture diagrams for every request flow
- **Pull request with full history**: [PR #67](https://github.com/neo4j-labs/neo4j-agent-integrations/pull/67) — including the reviewer feedback that triggered the template migration and the CodeQL findings that triggered the logging fix
- **DataRobot's official agent template**: [datarobot-community/af-component-agent](https://github.com/datarobot-community/af-component-agent)
- **Neo4j Agent Memory (NAMS)**: [neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory)
- **Model Context Protocol**: [modelcontextprotocol.io](https://modelcontextprotocol.io/)

If you're evaluating Neo4j + DataRobot for your own agentic workflows, or building something similar on top of MCP, we'd love to hear what you build.
