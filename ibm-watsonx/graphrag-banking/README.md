# Neo4j GraphRAG Banking Support Demo

## Overview

This demo is a bank support agent that runs in IBM watsonx Orchestrate. A signed-in customer asks about their own money, for example: "Why did my wire transfer fail yesterday, and will I be charged a penalty fee?"

Answering that question needs two kinds of data. The customer's accounts and transactions are database records. The bank's fee and hold rules are written policy documents. Plain vector search can find the right policy paragraph. It cannot tell which policy applies to this customer's transaction.

Neo4j stores both kinds of data in one knowledge graph and links each rule to the products and transactions it covers. The agent searches the policy text first. It then follows the graph links to the customer's own accounts and transactions. The answer names the exact transaction, the account product, and the rule that applies.

The same graph, tools, and instructions also run locally in plain Python.

This README has five parts:

- **Overview:** This part covers what the demo shows, the hero scenarios, and how the graph and tools work.
- **[Common setup](#common-setup):** These steps install the project and build the graph. Both ways of running the demo need them.
- **[Running locally](#running-locally):** This part covers chatting with the agent, the vector-only baseline, and the evaluation, all in plain Python.
- **[watsonx Orchestrate](#watsonx-orchestrate):** This part covers installing the ADK, connecting to your instance, and building and running the demo in Orchestrate.
- **[Reference](#reference):** This part describes the data files and the project layout.

### What the demo shows in watsonx Orchestrate

- **Native agent with Python tools:** The `banking_support` agent is defined in YAML and imported with the ADK CLI. It calls six custom Python tools that query Neo4j.
- **Built-in knowledge base as the baseline:** The `banking_baseline` agent answers from an Orchestrate knowledge base that holds the same policy documents. It uses vector search only, so it gives a generic answer. Asking both agents the same question shows what the graph adds.
- **Connection for secrets and identity:** The `banking_creds` connection holds the Neo4j credentials, the embedding key, and the signed-in customer ID. The tools read the customer ID from the connection, so the model never chooses whose data it reads.
- **Data isolation:** The tools only reach accounts the signed-in customer holds. A prompt that asks for another person's account gets no data from that account.
- **One codebase for local and Orchestrate:** Build scripts copy the local tools and instructions into the shape Orchestrate expects. A change to the local code reaches Orchestrate on the next build.
- **Approved packages only:** The tools need only the `neo4j` and `openai` packages. Their versions come from `uv.lock` and pass the tenant's package allowlist.
- **Preview and live:** Both agents are tested in the Orchestrate preview chat, then published to live with one command.
- **Proof in Neo4j Aura:** A saved Cypher query draws the path behind an answer in the Aura graph view. The audience can check each fact against the graph.

### The hero scenarios

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

### How it works

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

### Hosted features of watsonx Orchestrate

Orchestrate is a hosted service, so IBM runs and manages the pieces below. The demo uses each of them:

- **Hosted tool runtime:** The six Python tools run inside Orchestrate, not on a presenter's laptop. Orchestrate installs each tool's packages and runs the tool on every call.
- **Package allowlist:** Orchestrate checks tool packages against a list the tenant has approved. A tool that needs an unapproved package is rejected at import.
- **Managed connections:** Orchestrate stores the Neo4j and OpenAI credentials in the `banking_creds` connection. It keeps separate values for draft and live, and the tools read them at run time.
- **Draft and live versions:** Each agent has a draft version for testing and a live version for users. Publishing copies the tested draft to live.
- **Hosted chat:** Orchestrate provides the chat interface for both agents. The demo needs no web app.
- **Managed knowledge base:** Orchestrate chunks, embeds, and indexes the uploaded policy documents for the baseline agent. The demo writes no ingestion code for it.
- **Model gateway:** Both agents call their chat model through Orchestrate. The agents hold no model API key.

### Coming next

These items are planned or in progress:

- **watsonx.ai models:** The embeddings, the local agent, and the local baseline move from OpenAI to watsonx.ai models. The graph is rebuilt with watsonx.ai embeddings. Today the Orchestrate agents use the Orchestrate model `bedrock/openai.gpt-oss-120b-1:0`, and embeddings use OpenAI.
- **Evaluation against Orchestrate:** One command sends the scenario questions to the deployed Orchestrate agent. It scores the answers with the same checks the local evaluation uses and reports pass or fail per scenario.

These items are optional extras that can be added later:

- **Architect view:** A Streamlit app shows a chat pane next to a graph pane. The graph pane draws the nodes and policy chunks behind the last answer.
- **Architect agent with MCP:** A second Orchestrate agent uses the Neo4j MCP server. It can read the graph schema and run read-only Cypher over the whole graph.
- **GraphRAG as a knowledge base:** The policy search runs as a small web service. Orchestrate calls it as a custom search knowledge base.
- **ADK evaluation:** The scenarios become ADK evaluation test cases. These also check the order of tool calls.
- **watsonx.governance:** The agent is registered for monitoring.
- **Docling:** The policy documents are rendered as PDFs. Docling parses them before chunking.

The full design is in the PRD, [`neo4j_graphrag_banking_demo_prd.md`](neo4j_graphrag_banking_demo_prd.md). It covers the hero scenarios, the graph schema, and the build plan. [`docs/decision_log.md`](docs/decision_log.md) records the decisions, the model results, and the problems found so far.

---

## Common setup

Do these steps first, whether you run the demo locally or in Orchestrate. The Orchestrate tools query the same Aura graph that the local agent uses.

### Prerequisites

- [uv](https://docs.astral.sh/uv/). It installs Python 3.11 from `.python-version` if needed.
- A Neo4j Aura instance. AuraDB Free fits the default data volumes.
- An OpenAI API key.

The Orchestrate demo has its own prerequisites. See [watsonx Orchestrate](#watsonx-orchestrate).

AuraDB Free instances pause after 72 hours without activity. Resume a paused instance from the Aura console. Free snapshots cannot be restored, so rebuild the graph with `make rebuild` instead.

### Install and configure

```bash
cd ibm-watsonx/graphrag-banking
uv sync
cp env.sample .env      # then fill in the Aura and OpenAI values
```

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

### Build the graph

```bash
make check              # runs RETURN 1 against Aura
make rebuild            # wipes the database, then generates, validates, and loads everything
```

`make rebuild` deletes every node in the target database. Point `.env` at a database used only for this demo.

Each pipeline step is a console script, so it runs as `uv run <command>`. The `Makefile` wraps them.

| Make target | Runs | What it does |
|---|---|---|
| `make sync` | `uv sync` | Installs the locked environment |
| `make check` | `check-connection` | Verifies the Aura connection |
| `make reset` | `reset-db` | Deletes all nodes and drops the constraints and indexes |
| `make ingest` | `generate-data`, `render-policies`, `validate-data`, `load-structured`, `build-policy-graph` | Builds the data and loads all three graph layers |
| `make rebuild` | `make reset`, then `make ingest` | Rebuilds the graph from empty |

Use `make rebuild`, not `make ingest` twice. Each `build-policy-graph` run writes new `Chunk` nodes, so a second ingest without a reset duplicates the chunks.

---

## Running locally

Finish [Common setup](#common-setup) first. Then:

```bash
make test               # unit tests plus live checks against the graph
make chat               # chat with the agent as the demo customer
```

| Make target | Runs | What it does |
|---|---|---|
| `make chat` | `chat` | Interactive agent CLI |
| `make baseline` | `baseline-rag` | Vector-only baseline over the policy chunks |
| `make eval` | `eval-local` | Scores the agent on the hero scenarios |
| `make test` | `pytest` | Runs the test suite |
| `make lint` | `ruff check src` | Lints the source |

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
| `--persona NAME` | `customer` | Runs only the scenarios of this persona: `customer` or `staff`. A scenario with no `persona` is a customer's. |

```bash
uv run eval-local --runs 10
uv run eval-local --scenario A --scenario C
```

It exits with status 1 if any check fails. Results are written to `eval/results/eval-<UTC timestamp>.json`.

#### Evaluation in Orchestrate

`make wxo-eval` sends the same scenarios to Orchestrate agents and scores the answers with the same checks. Run `make wxo-env` first. It prints a pass or fail table per agent and scenario, and exits with status 1 if any run fails. Results are written to `eval/results/wxo-eval-<UTC timestamp>.json`.

| Variable | Default | Effect |
|---|---|---|
| `AGENTS` | `banking_support` | Comma-separated agent names, for comparing models |
| `SCENARIOS` | `A,B,C,D` | Comma-separated scenario IDs, or `all` |
| `PERSONA` | `customer` | The persona whose scenarios `all` runs: `customer` or `staff` |
| `RUNS` | `1` | Runs each scenario N times. Each run starts a new chat thread. |
| `SAME_THREAD` | unset | `1` sends the scenarios in order in one thread per run. Each turn is scored on its own answer and tool calls. |
| `SUPERVISOR_CHECK` | unset | `1` also runs `eval/eval-scripts/supervisor_check.py` on the saved results. It checks that the supervisor kept each collaborator's facts and added none. Traces are cached in `TRACES_DIR`, which defaults to `eval/results/traces`. |

```bash
make wxo-eval RUNS=3
make wxo-eval AGENTS=banking_support,banking_support_frontier SCENARIOS=A,B
make wxo-eval SAME_THREAD=1 SCENARIOS=C,D
```

---

## watsonx Orchestrate

The Orchestrate demo uses the same graph, tools, and instructions as the local agent. Nothing is rewritten for Orchestrate. The scripts in `orchestrate/` copy the local code into the shape Orchestrate expects.

Finish [Common setup](#common-setup) first, including `make rebuild`. The Orchestrate demo also needs:

- A watsonx Orchestrate instance on IBM Cloud. IBM offers a [free 30-day trial](https://www.ibm.com/account/reg/us-en/signup?formid=urx-52753).
- The watsonx Orchestrate Agent Development Kit, or ADK. It provides the `orchestrate` command.

### Install the ADK

`uv sync` does not install the ADK. Install it once as a uv tool, so `orchestrate` is on your `PATH` in every shell:

```bash
uv tool install ibm-watsonx-orchestrate --with neo4j --with openai
orchestrate --version
```

`orchestrate tools import` loads the tool file on your machine to read the tool definitions. The tool file imports `neo4j`, so the ADK's own environment needs `neo4j` and `openai` too. Without them, `make wxo-tools` fails with `No module named 'neo4j'`. Orchestrate still installs the pinned versions from `uv.lock` when it runs the tools.

The ADK needs Python 3.11 or later. uv downloads a suitable Python if none is installed. If the shell still reports `orchestrate: command not found`, run `uv tool update-shell` and open a new terminal.

To upgrade the ADK later, run `uv tool upgrade ibm-watsonx-orchestrate`. The upgrade keeps the `--with` packages.

### Connect to your instance

The ADK needs the service instance URL and an API key from your Orchestrate instance. Use the values from the **API details** tab. The credentials on the IBM Cloud resources page do not work with the ADK.

1. Log in to your watsonx Orchestrate instance.
2. Click your user icon at the top right, then click **Settings**.
3. Open the **API details** tab and copy the service instance URL.
4. Click **Generate API key**. The page opens IBM Cloud Identity and Access Management.
5. Click **Create**, enter a name and a description, and copy the key. Store it somewhere safe.

Add these values to `.env`. `WO_ENV_NAME` is any name you choose.

```bash
WO_ENV_NAME=<env>
WO_INSTANCE_URL=<service-instance-url>
WO_API_KEY=<api-key>
```

Then add the environment and activate it:

```bash
make wxo-env
```

`make wxo-env` runs `orchestrate/connect_env.sh`. The script adds the environment the first time, then logs in with the API key from `.env`, so nothing prompts. The ADK picks the auth type from the instance URL. If the login fails with `Error getting IBM_IAM Token` or a similar token error, set `WO_AUTH_TYPE` in `.env` to the right type, run `orchestrate env remove -n <env>`, and run `make wxo-env` again. The valid types are `ibm_iam`, `mcsp`, `mcsp_v1`, `mcsp_v2`, `cpd`, and `k8s`.

The login expires every two hours. When a command fails with an authentication error, run `make wxo-env` again.

### Check the tenant

Both agents use the Orchestrate model `bedrock/openai.gpt-oss-120b-1:0`. Check that your tenant offers it:

```bash
orchestrate models list
```

The tools also need the pinned `neo4j` and `openai` versions on the tenant's package allowlist. [What gets created](#what-gets-created) lists the current pins and how to change the model.

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

```bash
make wxo-env
make wxo-setup
```

| Make target | Runs | What it does |
|---|---|---|
| `make wxo-setup` | the four `wxo-*` targets below, in order | Builds the whole Orchestrate demo |
| `make wxo-connection` | `orchestrate/create_connection.sh` | Creates the `banking_creds` connection from `.env` |
| `make wxo-tools` | `orchestrate/build_tools.sh` | Imports the six tools |
| `make wxo-agent` | `orchestrate/build_agent.py`, then `orchestrate agents import` | Imports the `banking_support` agent |
| `make wxo-baseline` | `orchestrate/build_baseline.sh` | Imports the knowledge base and the `banking_baseline` agent |
| `make wxo-check` | `orchestrate/check_setup.py` | Checks that every demo object exists and is wired together |
| `make wxo-deploy` | `orchestrate agents deploy` | Publishes both agents to live |
| `make wxo-eval` | `eval/eval-scripts/wxo_eval.sh` | Scores the scenarios against Orchestrate agents. See [Evaluation in Orchestrate](#evaluation-in-orchestrate). |

Each target is safe to re-run. Wait until `orchestrate knowledge-bases status -n banking_policies` shows the knowledge base as ready. Test both agents in the Orchestrate preview chat, then publish them with `make wxo-deploy`.

### Running the demo

Start a new chat for each scenario. A follow-up in the same chat carries the earlier answer's context. For example, Scenario D asked right after Scenario C can read "Sarah's account" as the joint account.

1. **The failure.** Ask `banking_baseline` the Scenario A prompt. It answers from the policy documents only, with generic reasons a wire can fail.
2. **The fix.** Ask `banking_support` the same prompt. It says the wire is held, not failed, and that Premium Checking waives both wire fees.
3. **The proof.** Run `orchestrate/proof_query.cypher` in the Aura Query tool and switch to the graph view. It draws the path behind the answer, from Marcus to the held wire, its compliance alert and rule, and the fee rules waived for Premium Checking, each with its policy text. Aura saved queries belong to the user who saves them, so each presenter saves the query into their own Aura console.

Scenarios B to D run on `banking_support` the same way. The expected answers are in [The hero scenarios](#the-hero-scenarios).

### Demo walkthrough

These steps run the scenarios from a terminal. They show each tool the agent called and each model call behind the answer. The output below comes from a run on 2026-10-19 with `bedrock/openai.gpt-oss-120b-1:0`. Answers vary in wording from run to run.

#### Ask an agent from the terminal

`orchestrate chat ask` sends one prompt to an agent in the active environment. It prints a reasoning trace, then the answer:

```bash
echo q | orchestrate chat ask -n banking_baseline \
  -r "Why did my wire transfer to Acme Corp fail yesterday, and will I be charged a penalty fee?"
```

After the answer, `chat ask` waits for the next message. `echo q` ends the chat after the first answer. Without it, the command keeps waiting. With input from `/dev/null`, it loops forever. The last box of the output holds the thread ID, which the model-call steps below need.

#### Scenario A on the baseline

The baseline searches the `banking_policies` knowledge base and gets the wire and fee policy passages:

```text
╭─ 🧠 Reasoning Trace ─────────────────────────────────────────────────────────╮
│  Step 1: Called tool 'banking_policies'                                      │
│    Agent: banking_baseline                                                   │
│  Step 2: Tool 'banking_policies' responded                                   │
│    Response: [                                                               │
│    {                                                                         │
│      "title": "wire_transfers.txt",                                          │
│      "body": "# Wire Transfer Policy\n\nEffective January 1, 2026. ...       │
...
╭─ 🤖 banking_baseline ────────────────────────────────────────────────────────╮
│  **Why the wire to Acme Corp failed**                                        │
│                                                                              │
│  According to our Wire Transfer Policy, a wire is marked **“Failed”** when   │
│  it cannot be sent. The most common reasons are:                             │
│                                                                              │
│  * Incomplete or incorrect beneficiary information (e.g., missing or wrong   │
│  routing number, account number, or beneficiary name)                        │
...
```

The passages it retrieved define a held wire and say Premium Checking waives the wire fees. The baseline cannot see Marcus's transaction, so it never learns that his wire is held. It accepts the question's premise and lists generic reasons a wire fails.

#### Scenario A on banking_support

```bash
echo q | orchestrate chat ask -n banking_support \
  -r "Why did my wire transfer to Acme Corp fail yesterday, and will I be charged a penalty fee?"
```

The agent finds the wire, then explains it with the graph:

```text
╭─ 🧠 Reasoning Trace ─────────────────────────────────────────────────────────╮
│  Step 1: Called tool 'find_my_transactions'                                  │
│    Agent: banking_support                                                    │
│  Step 2: Tool 'find_my_transactions' responded                               │
│    Response: I'm sorry, it seems I've encountered an error calling the       │
│  tool.: Error invoking tool 'find_my_transactions' with kwargs {'type':      │
│  ['WIRE_OUT'], 'date_from': '2026-10-07', 'date_to': '2026-10-07'} with      │
│  error:                                                                      │
│   type: Input should be a valid string                                       │
│  Step 3: Called tool 'find_my_transactions'                                  │
│  Step 4: Tool 'find_my_transactions' responded                               │
│    Response: {"transactions": [{"account_id": "A-1001", "account_nickname":  │
│  "Premium Checking", "amount": "$5,000.00", ... "status": "HELD",            │
│  "transaction_id": "T-1022", "type": "WIRE_OUT"}]}                           │
│  Step 5: Called tool 'explain_transaction'                                   │
│  Step 6: Tool 'explain_transaction' responded                                │
│    Response: {"account": {"account_id": "A-1001", "nickname": "Premium       │
│  Checking"}, "alerts": [{"alert_id": "AL-1001", ... "rule_code":             │
│  "WIRE-REVIEW-01", ... "fee_rules": [{"amount": "$30.00", ...                │
│  "rule_code": "FEE-WIRE-OUT", ... "waived_for_this_product": true}, ...      │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ 🤖 banking_support ─────────────────────────────────────────────────────────╮
│  Your wire to **Acme Corp** that you started on **October 7** for            │
│  **$5,000** is not a failed transfer—it is being **held for a compliance     │
│  review**.                                                                   │
...
│  **Fees**                                                                    │
│  - The outgoing‑wire fee ($30) is waived for your Premium Checking account.  │
│  - The returned‑wire fee ($35) applies only when a wire is sent and then     │
│  returned by the receiving bank; it is not charged for wires that are held   │
│  for review.                                                                 │
...
╭───────────────────────── 💾 Save Your Conversation ──────────────────────────╮
│ Thread ID: 63037803-210a-425f-a862-3b6eb2a464cc                              │
```

Each step in the trace is visible:

- **Steps 1 and 2:** The model passed `type` as a list. The tool rejected it, and the model retried. gpt-oss often makes this mistake on its first call.
- **Steps 3 and 4:** `find_my_transactions` found wire `T-1022` with status `HELD`.
- **Steps 5 and 6:** `explain_transaction` followed the graph from the wire to its compliance alert and rule `WIRE-REVIEW-01`. It also returned the fee rules for Premium Checking, each marked as waived.

`chat ask` shows the tool responses. It does not show the arguments the model sent. The model calls below show them.

#### See the model calls

Orchestrate records every model call in a trace. A trace's session ID is the chat's thread ID. Find the trace:

```bash
orchestrate observability traces search --last 30m \
  --session-id 63037803-210a-425f-a862-3b6eb2a464cc
```

```text
┃ Timestamp      ┃ Trace ID                         ┃ Agent Name     ┃ Latency ┃
│ 10/19/2026 ,   │ 39cdf394182527d729d8b2cbf1a2f1d6 │ banking_suppo… │  7.717s │
```

`orchestrate observability traces export` fails with a 400 on every published ADK version. It leaves out a time window that the API requires. `eval/eval-scripts/traces.py` calls the API with that window and saves the trace's observations as JSON. It runs with the ADK's Python:

```bash
ADK_PY="$(uv tool dir)/ibm-watsonx-orchestrate/bin/python"
"$ADK_PY" -I eval/eval-scripts/traces.py get 39cdf394182527d729d8b2cbf1a2f1d6 trace.json
```

Each model call is an observation of type `GENERATION`. This `jq` command prints one line per model call, with the model, input tokens, output tokens, latency, and the tool calls it chose:

```bash
jq -r '.[] | select(.type == "GENERATION")
  | [.model, .inputTokens, .outputTokens, "\(.latency)ms",
     ([.output.tool_calls[]? | "\(.name) \(.args | tojson)"] | join("; ")
      | if . == "" then "(answer)" else . end)]
  | @tsv' trace.json
```

```text
openai.gpt-oss-120b-1:0  1266  87   1735ms  find_my_transactions {"type":["WIRE_OUT"],"date_from":"2026-10-07","date_to":"2026-10-07"}
openai.gpt-oss-120b-1:0  1398  60   531ms   find_my_transactions {"type":"WIRE_OUT","date_from":"2026-10-07","date_to":"2026-10-07"}
openai.gpt-oss-120b-1:0  1612  42   368ms   explain_transaction {"transaction_id":"T-1022"}
openai.gpt-oss-120b-1:0  2428  260  1576ms  (answer)
```

The agent made four model calls. The first three each chose one tool. The fourth wrote the answer. The input grows with each call, because each tool response joins the conversation.

gpt-oss also returns its reasoning text. This prints the reasoning behind the first call:

```bash
jq -r '[.[] | select(.type == "GENERATION")][0].output.additional_kwargs.reasoning' trace.json
```

```text
We need to find transaction. Use find_my_transactions for WIRE_OUT, date_from yesterday (2026-10-07) to date_to yesterday.
```

`traces.py get` can only fetch traces from the last four hours. The first tool call after a quiet period can take close to a minute while the tool runtime starts. The trace shows this as a long `find_my_transactions` span.

#### Scenarios B to D

Run each prompt in a new chat with `echo q | orchestrate chat ask -n banking_support -r "<prompt>"`.

| Scenario | Tools called | What the answer said |
|---|---|---|
| B | `get_my_accounts`, `find_my_transactions`, `get_scheduled_payments` | The $2,000 check is pending and available October 9. Today's available balance is $1,800. The $3,200 Lakeside Home Loans payment on October 13 is covered, with $3,800 available before it. |
| C | `get_my_accounts`, `search_policies` | The joint account is Standard Checking, so the fee is $29 per item. No fee is charged when the account is overdrawn by $50 or less. Overdraft Protection from Marcus's Emergency Fund costs $10 per transfer. |
| D | `get_my_accounts`, then `find_my_transactions` four times | The agent listed Marcus's own Emergency Fund deposits. No data from Sarah's savings account `A-2001` appeared. |

In Scenario D, gpt-oss read "Sarah's savings account" as Marcus's own savings. The data stayed isolated, but the answer did not explain why. With `watsonx-orchestrate/frontier`, the agent instead says it can only show accounts Marcus holds.

#### Score the scenarios

`eval/eval-scripts/run_agent.py` sends prompts to an agent and saves each answer and tool response. `eval/eval-scripts/score.py` scores them with the same checks as `make eval`:

```bash
"$ADK_PY" -I eval/eval-scripts/run_agent.py runs --agents banking_support --scenarios A
uv run python eval/eval-scripts/score.py runs
```

`make wxo-eval` runs both steps. [`docs/orchestrate-demo.md`](docs/orchestrate-demo.md) has the results for gpt-oss, frontier, Granite and two OpenAI models.

### Removing the demo

Remove the agents first, because they reference the tools and the knowledge base.

```bash
orchestrate agents remove --name banking_support --kind native
orchestrate agents remove --name banking_baseline --kind native
orchestrate knowledge-bases remove --name banking_policies
for tool in search_policies get_my_accounts find_my_transactions \
            explain_transaction get_my_household get_scheduled_payments; do
  orchestrate tools remove --name "$tool"
done
orchestrate connections remove --app-id banking_creds
```

This leaves the Aura graph in place. Run `make reset` to empty the database too.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `orchestrate: command not found` | Install the ADK. See [Install the ADK](#install-the-adk). If it is installed, run `uv tool update-shell` and open a new terminal. |
| A command fails with an authentication or token error | The login expired. Run `make wxo-env`. |
| `make wxo-env` fails with `Error getting IBM_IAM Token` | The auth type does not match the API key. Set `WO_AUTH_TYPE` in `.env`, run `orchestrate env remove -n <env>`, then run `make wxo-env` again. |
| `WO_<KEY> is not set in .env` from `connect_env.sh` | Fill in that value in `.env`, then re-run `make wxo-env`. |
| `<KEY> is not set in .env` from `create_connection.sh` | Fill in that value in `.env`, then re-run `make wxo-connection`. |
| The tool import rejects `neo4j` or `openai` | The tenant's package allowlist does not include the pinned version. Compare the pins in `orchestrate/build/requirements.txt` with the allowlist. |
| `banking_baseline` answers without any policy content | The knowledge base is still processing. Check `orchestrate knowledge-bases status -n banking_policies` and wait until it is ready. |
| The tools return Neo4j connection errors | The AuraDB Free instance may be paused. Resume it from the Aura console. |

---

## Reference

### Data

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

### Orchestrate overview

These are the main commands for the Orchestrate demo. The `make` targets wrap the scripts in `orchestrate/`. The `orchestrate` commands come from the ADK and act on the active environment.

| Command | What it does |
|---|---|
| `make wxo-env` | Adds the environment from `.env` and logs in. Re-run it when the two-hour login expires. |
| `make wxo-setup` | Creates the connection, tools, agent, knowledge base, and baseline agent |
| `make wxo-deploy` | Publishes both agents from draft to live |
| `orchestrate env list` | Lists the environments and marks the active one |
| `orchestrate models list` | Lists the models the tenant offers |
| `orchestrate connections list` | Lists the connections and their draft and live settings |
| `orchestrate tools list` | Lists the imported tools |
| `orchestrate agents list` | Lists the agents |
| `orchestrate knowledge-bases status -n banking_policies` | Shows whether the knowledge base is ready |

#### Validate your environment

Run these checks in order. Each one depends on the step before it.

```bash
make check                                              # Aura answers RETURN 1
orchestrate --version                                   # the ADK is installed
make wxo-env                                            # logs in to the instance
orchestrate env list                                    # WO_ENV_NAME is marked (active)
orchestrate models list | grep bedrock/openai.gpt-oss   # the tenant offers the agent model
```

After `make wxo-setup`, check that each object exists:

```bash
make wxo-check
```

`make wxo-check` runs `orchestrate/check_setup.py` with `uv run`. The ADK list commands return every object in the tenant. The script keeps only the demo's objects and prints a PASS or FAIL line for each check:

- **Environment:** The active environment must match `WO_ENV_NAME`.
- **Tools:** All six tools from `tools.py` must be imported.
- **Knowledge base:** `banking_policies` must exist, and its status must be ready.
- **Connection:** `banking_creds` must have credentials for draft and live.
- **Agents:** `banking_support` must use all six tools, and `banking_baseline` must use `banking_policies`.

It exits with status 1 if any check fails. To inspect the objects by hand, run the ADK commands it wraps:

```bash
orchestrate connections list                            # banking_creds, for draft and live
orchestrate tools list                                  # the six tools from tools.py
orchestrate agents list                                 # banking_support and banking_baseline
orchestrate knowledge-bases status -n banking_policies  # ready
```

If a check fails, see [Troubleshooting](#troubleshooting).

### Layout

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
