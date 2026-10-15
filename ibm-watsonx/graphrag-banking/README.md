# Neo4j GraphRAG Banking Support Demo

A banking support agent that answers questions no single data source can answer on its own. Accounts, transactions, and compliance alerts are structured records. Fee schedules, hold rules, and compliance procedures are policy documents. Vector RAG can find the right policy paragraph, but it cannot tell which policy applies to this customer's transaction.

This demo stores both in one Neo4j knowledge graph and connects them. The agent uses vector search to find the right policy text. It then follows graph relationships to the customer's accounts, products, and transactions. Every fact in an answer traces back to a node or a document chunk.

The full design is in the PRD, [`neo4j_graphrag_banking_demo_prd.md`](neo4j_graphrag_banking_demo_prd.md). It covers the hero scenarios, the graph schema, and the phase plan.

---

## Status

Phases 1 to 3 run in plain Python against Neo4j Aura, with OpenAI models.

Phase 5 runs the demo in watsonx Orchestrate. A native Orchestrate agent calls the same six tools as Orchestrate Python tools, and a second agent with an Orchestrate built-in knowledge base is the vector-only baseline. Embeddings still use OpenAI. See [watsonx Orchestrate](#watsonx-orchestrate).

Phases 4, 6, and 7 remain: watsonx.ai models, evaluation against the Orchestrate agent, and stretch goals. [`docs/decision_log.md`](docs/decision_log.md) records the decisions, the Phase 3 model results, and the problems found so far.

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/). It installs Python 3.11 from `.python-version` if needed.
- A Neo4j Aura instance. AuraDB Free fits the default data volumes.
- An OpenAI API key.
- For the Orchestrate demo only: a watsonx Orchestrate instance and the [ADK CLI](https://developer.watson-orchestrate.ibm.com/getting_started/installing), with an environment activated by `orchestrate env activate <env>`.

AuraDB Free instances pause after 72 hours without activity. Resume a paused instance from the Aura console. Free snapshots cannot be restored, so rebuild the graph with `make rebuild` instead.

---

## Quickstart

```bash
cd ibm-watsonx/graphrag-banking
uv sync
cp env.sample .env      # then fill in the Aura and OpenAI values
make check              # runs RETURN 1 against Aura
make rebuild            # wipes the database, then generates, validates, and loads everything
make test               # unit tests plus live checks against the graph
make chat               # chat with the agent as the demo customer
```

`make rebuild` deletes every node in the target database. Point `.env` at a database used only for this demo.

### Configuration

`env.sample` lists every setting. `.env` is git-ignored.

| Variable | Default | Purpose |
|---|---|---|
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | | Aura connection, from the credentials file Aura downloads |
| `OPENAI_API_KEY` | | OpenAI access |
| `OPENAI_CHAT_MODEL` | `gpt-5.6-terra` | Chat model for the agent and the vector-only baseline |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model. Its 1536 dimensions set the vector index size. |
| `DEMO_AS_OF` | `2026-10-08` | The demo's fixed "today". "Yesterday" and "this morning" resolve from it. |
| `DEMO_CUSTOMER_ID` | `C-1001` | The signed-in customer. Tools read it from config, never from the model. |
| `DATA_SEED` | `42` | Seed for the synthetic data generator |

The agent and the baseline use the same chat model, so the side-by-side comparison is fair.

---

## Commands

Each pipeline step is a console script, so it runs as `uv run <command>`. The `Makefile` wraps them.

| Make target | Runs | What it does |
|---|---|---|
| `make sync` | `uv sync` | Installs the locked environment |
| `make check` | `check-connection` | Verifies the Aura connection |
| `make reset` | `reset-db` | Deletes all nodes and drops the constraints and indexes |
| `make ingest` | `generate-data`, `render-policies`, `validate-data`, `load-structured`, `build-policy-graph` | Builds the data and loads all three graph layers |
| `make rebuild` | `make reset`, then `make ingest` | Rebuilds the graph from empty |
| `make chat` | `chat` | Interactive agent CLI |
| `make baseline` | `baseline-rag` | Vector-only baseline over the policy chunks |
| `make eval` | `eval-local` | Scores the agent on the hero scenarios |
| `make test` | `pytest` | Runs the test suite |
| `make lint` | `ruff check src` | Lints the source |
| `make wxo-setup` | the four `wxo-*` targets below, in order | Builds the whole Orchestrate demo |
| `make wxo-connection` | `orchestrate/create_connection.sh` | Creates the `banking_creds` connection from `.env` |
| `make wxo-tools` | `orchestrate/build_tools.sh` | Imports the six tools |
| `make wxo-agent` | `orchestrate/build_agent.py`, then `orchestrate agents import` | Imports the `banking_support` agent |
| `make wxo-baseline` | `orchestrate/build_baseline.sh` | Imports the knowledge base and the `banking_baseline` agent |
| `make wxo-deploy` | `orchestrate agents deploy` | Publishes both agents to live |

Use `make rebuild`, not `make ingest` twice. Each `build-policy-graph` run writes new `Chunk` nodes, so a second ingest without a reset duplicates the chunks.

### Chat

`uv run chat` signs in as `DEMO_CUSTOMER_ID`. After each answer it prints a trace of the tools called, the Cypher they ran, and the policy chunks retrieved. Press Ctrl-D to quit.

See [The hero scenarios](#the-hero-scenarios) for sample questions.

### Baseline

`uv run baseline-rag` answers with vector search over the policy chunks only. It has no access to the customer's accounts. With no argument it runs the Scenario A to D prompts. With a question argument it runs only that question.

```bash
uv run baseline-rag "What's the overdraft fee on our joint account?"
```

In Orchestrate, the `banking_baseline` agent replaces it. See [watsonx Orchestrate](#watsonx-orchestrate).

### Evaluation

`uv run eval-local` runs every scenario in `eval/scenarios.yaml` through the agent and scores it. It checks facts, not exact wording:

- **Answer facts:** These amounts, dates, and statuses must appear in the answer. Amounts and dates are normalized first, so "$5,000.00" matches "$5,000" and "Oct 7th" matches "2026-10-07".
- **Trace facts:** These rule codes and account IDs must appear in the recorded tool results.
- **Must-not-appear facts:** None of these may appear in the answer.

Some scenarios also list `manual_review` items. These are printed for a human reader and not scored.

| Flag | Default | Effect |
|---|---|---|
| `--runs N` | `3` | Runs each scenario N times |
| `--scenario ID` | all | Runs only this scenario. Repeat the flag to run several. |

```bash
uv run eval-local --runs 10
uv run eval-local --scenario A --scenario C
```

It exits with status 1 if any check fails. Results are written to `eval/results/eval-<UTC timestamp>.json`.

---

## The hero scenarios

All scenarios run as one demo customer, Marcus Okafor (`C-1001`), on `2026-10-08`.

| Account | Product | Holders |
|---|---|---|
| `A-1001` | Premium Checking | Marcus |
| `A-1002` | Standard Checking, named "Joint Checking" | Marcus and Sarah Okafor |
| `A-1003` | Standard Savings, named "Emergency Fund" | Marcus only |
| `A-2001` | Standard Savings | Sarah only |

| Scenario | Prompt | What the graph adds |
|---|---|---|
| A | "Why did my wire transfer to Acme Corp fail yesterday, and will I be charged a penalty fee?" | The wire is on a compliance hold, not failed. Premium Checking waives the wire fees. |
| B | "Sarah deposited a check into our joint account this morning. Has it cleared, and do we have enough to cover the mortgage auto-pay?" | The check hold date, the available balance today, and the next mortgage run date |
| C | "What's the overdraft fee on our joint account, and how can we avoid it?" | The joint account's product, so the agent quotes Standard Checking terms and not Premium Checking terms. It also names Marcus's Emergency Fund as the account to link for Overdraft Protection. |
| D | "Show me the recent transactions on Sarah's savings account." | Data isolation. The tools only reach accounts Marcus holds. |

`eval/scenarios.yaml` also holds five adversarial isolation prompts, `D1` to `D5`. The baseline skips them. PRD section 4 lists the expected answer and every checked fact for each scenario.

---

## How it works

The graph has three layers:

1. **Structured layer:** Customers, accounts, transactions, counterparties, scheduled payments, and compliance alerts. These load from CSVs with batched `UNWIND ... MERGE`.
2. **Rule layer:** Products, policies, and fee, hold, and compliance rules. These load from `data/policy_facts.yaml`. Each rule has a rule code.
3. **Document layer:** Policy documents, chunked by heading and embedded with a neo4j-graphrag `Pipeline`. Each chunk links to the rules it covers through its rule codes.

The agent is a LangGraph ReAct agent with six tools in `src/graphrag_banking/tools.py`:

| Tool | What it returns |
|---|---|
| `search_policies` | The best matching policy passages and the passages next to them, with the rules each defines and the products they apply to |
| `get_my_accounts` | The customer's accounts, with product, balances, and co-holders |
| `find_my_transactions` | The customer's transactions, newest first, filtered by payee, type, or date range |
| `explain_transaction` | One transaction with its alerts, fees, and the fee and hold rules for the account's product |
| `get_my_household` | Household members and the accounts they share with the customer |
| `get_scheduled_payments` | Upcoming payments on one account, with the balance available before each and whether it is covered |

Every customer-scoped tool starts from `DEMO_CUSTOMER_ID` and traverses `HOLDS`. The model never supplies the customer ID. `tools.py` imports only the `neo4j` driver and `embeddings.embed`, so the same code ships unchanged as Orchestrate Python tools.

The agent's instructions are in `prompts/agent_instructions.md`. `DEMO_AS_OF` is filled in when the agent loads the file.

---

## watsonx Orchestrate

The Orchestrate demo uses the same graph, tools, and instructions as the local agent. Nothing is rewritten for Orchestrate. The scripts in `orchestrate/` copy the local code into the shape Orchestrate expects.

### What gets created

| Orchestrate object | Name | Built from |
|---|---|---|
| Connection | `banking_creds` | `.env`. It holds the Aura credentials, the OpenAI key and embedding model, `DEMO_CUSTOMER_ID`, and `DEMO_AS_OF`, for both draft and live. |
| Python tools | the six tools in `tools.py` | `orchestrate/tools/banking_tools.py`, a thin wrapper per tool |
| Agent | `banking_support` | `prompts/agent_instructions.md`, with the date written in |
| Knowledge base | `banking_policies` | The eight documents in `data/policies/` |
| Agent | `banking_baseline` | `orchestrate/baseline_agent.yaml` |

Each tool wrapper reads `banking_creds`, opens a Neo4j driver, and calls the matching function in `tools.py`. The customer ID comes from the connection, so the model never chooses whose data it reads. Each wrapper also takes its description from the matching function, so the agent sees the same tool descriptions in Orchestrate as it does locally.

`build_tools.sh` assembles the tool package in `orchestrate/build/` on every run. It copies `tools.py` as `banking_queries.py` and `embeddings.py` next to the wrapper, so `tools.py` stays the single source of truth. `build_agent.py` fills the date into the instructions the same way the local agent does, because Orchestrate instructions have no placeholders. Re-run both after changing the tools or the instructions. `orchestrate/build/` is git-ignored.

The tools install `neo4j` and `openai`. `build_tools.sh` exports their pins from `uv.lock` with `uv export` and keeps only those two, so uv stays the source of truth. The current pins, `neo4j==6.4.0` and `openai==3.29.0`, are on the tenant package allowlist.

Both agents use the Orchestrate model `bedrock/openai.gpt-oss-120b-1:0`. To use another model from `orchestrate models list`, set `ORCHESTRATE_MODEL` for `build_agent.py` and edit `llm` in `orchestrate/baseline_agent.yaml`.

### Setup

Build the graph first with `make rebuild`. Then:

```bash
orchestrate env activate <env>
make wxo-setup
```

Wait until `orchestrate knowledge-bases status -n banking_policies` shows the knowledge base as ready. Test both agents in the Orchestrate preview chat, then publish them with `make wxo-deploy`.

### Running the demo

Start a new chat for each scenario. A follow-up in the same chat carries the earlier answer's context. For example, Scenario D asked right after Scenario C can read "Sarah's account" as the joint account.

1. **The failure.** Ask `banking_baseline` the Scenario A prompt. It answers from the policy documents only, with generic reasons a wire can fail.
2. **The fix.** Ask `banking_support` the same prompt. It says the wire is held, not failed, and that Premium Checking waives both wire fees.
3. **The proof.** Run `orchestrate/proof_query.cypher` in the Aura Query tool and switch to the graph view. It draws the path behind the answer, from Marcus to the held wire, its compliance alert and rule, and the fee rules waived for Premium Checking, each with its policy text. Aura saved queries belong to the user who saves them, so each presenter saves the query into their own Aura console.

Scenarios B to D run on `banking_support` the same way. The expected answers are in [The hero scenarios](#the-hero-scenarios).

---

## Data

`make ingest` generates a seeded synthetic population with Faker, then merges in the hand-written hero records. `validate-data` checks referential integrity, balance reconciliation, every expected scenario fact, and that every rule code appears in exactly one policy section.

| Path | Committed | Contents |
|---|---|---|
| `data/policy_facts.yaml` | Yes | Canonical products, policies, and rules |
| `data/hero_fixtures.yaml` | Yes | Hand-written records for the hero scenarios |
| `data/policy_templates/` | Yes | Policy Markdown with placeholders |
| `data/policies/` | Yes | Rendered policy documents, written by `render-policies` |
| `data/generated/` | No | CSVs written by `generate-data` |

Background data never touches the hero customers or accounts. The hero history is fully hand-written in `data/hero_fixtures.yaml`. Edit hero balances there, and `validate-data` reconciles them against the transactions.

After editing `policy_facts.yaml` or a template, run `make rebuild`. It re-renders the policies, and they must be committed. `data/README.md` documents the CSV columns, controlled values, and hero ID ranges.

---

## Layout

```
graphrag-banking/
├── neo4j_graphrag_banking_demo_prd.md
├── pyproject.toml                  dependencies and console scripts
├── uv.lock
├── env.sample
├── Makefile
├── docs/
│   └── decision_log.md             decisions, model results, and problems found
├── data/                           see the Data section
├── prompts/
│   └── agent_instructions.md
├── eval/
│   ├── scenarios.yaml
│   └── results/                    eval-local output
├── orchestrate/                    watsonx Orchestrate demo
│   ├── create_connection.sh        banking_creds connection from .env
│   ├── build_tools.sh              assembles and imports the six tools
│   ├── build_agent.py              writes the banking_support agent YAML
│   ├── build_baseline.sh           knowledge base and baseline agent
│   ├── baseline_agent.yaml         banking_baseline agent
│   ├── proof_query.cypher          Scenario A subgraph for the Aura console
│   ├── tools/
│   │   └── banking_tools.py        Orchestrate wrappers around tools.py
│   └── build/                      generated by the scripts, git-ignored
├── src/graphrag_banking/
│   ├── config.py                   settings from .env
│   ├── embeddings.py               embed(), shared by tools and ingestion
│   ├── models.py                   neo4j-graphrag Embedder wrapper
│   ├── generate_data.py
│   ├── render_policies.py
│   ├── validate_data.py
│   ├── reset_db.py
│   ├── load_structured.py          structured and rule layers
│   ├── build_policy_graph.py       document layer and vector index
│   ├── tools.py                    agent tools
│   ├── agent.py                    LangGraph agent
│   ├── chat.py
│   ├── baseline_vector_rag.py
│   └── eval_local.py
└── tests/
    ├── test_graph.py               live checks against the built graph
    └── test_track_b.py             unit tests, no database needed
```