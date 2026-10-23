# Neo4j GraphRAG Banking Support Demo

## Overview

This demo shows the Neo4j and IBM watsonx integration story. It is a bank support agent that runs in **IBM watsonx Orchestrate** and answers from a Neo4j knowledge graph. A signed-in customer asks about their own money, for example: "Why did my wire transfer fail yesterday, and will I be charged a penalty fee?"

Answering that question needs two kinds of data. The customer's accounts and transactions are database records. The bank's fee and hold rules are written policy documents. Plain vector search can find the right policy paragraph. It cannot tell which policy applies to this customer's transaction.

Neo4j stores both kinds of data in one knowledge graph and links each rule to the products and transactions it covers. The agent searches the policy text first. It then follows the graph links to the customer's own accounts and transactions. The answer names the exact transaction, the account product, and the rule that applies.

The same graph, tools, and instructions also run locally in plain Python.

The **watsonx Orchestrate** part has two demos on the same graph. [Demo One](#orchestrate-demo-one-staff-and-fraud) is for bank staff. A relationship manager asks whether a loan can be approved, and the graph shows the application is part of a fraud ring. [Demo Two](#orchestrate-demo-two-customer-support) is the customer support agent described above.

Two more examples show other ways Neo4j can integrate with Orchestrate. Orchestrate supplies the **agent builder**, the **chat**, the **managed connections**, and the **draft and live deployment**. Neo4j supplies the connected context that a text index cannot, such as which rule covers which product and which business sits in a fraud ring.

- **MCP server integration:** The Neo4j MCP server joins Orchestrate as an **MCP toolkit** on a **managed connection**. An agent reads the schema and runs read-only Cypher, with no tool written for each question.
- **Custom knowledge service integration:** Neo4j plugs into Orchestrate as a **custom service knowledge source**. A small service in front of the graph implements the Orchestrate request format, so any agent answers from the graph just by adding the knowledge source.

This README has five parts:

- **Overview:** This part covers what the demos show, the three ways the graph connects to Orchestrate, the hero scenarios, and how the graph and tools work.
- **[Common setup](#common-setup):** These steps install the project and build the graph. Every path below needs them.
- **[Running locally](#running-locally):** This part covers chatting with the agent, the vector-only baseline, and the evaluation, all in plain Python.
- **[watsonx Orchestrate](#watsonx-orchestrate):** This part covers installing the ADK, connecting to your instance, the shared setup, the two demos, and scoring the Orchestrate agents with the evaluation.
- **[More documentation](#more-documentation):** This part links to the presenter scripts, the graph schema, the reference pages, the troubleshooting guide, and the decision log.

### Neo4j integration with watsonx Orchestrate through MCP

[`mcp-setup/`](mcp-setup/README.md) integrates Neo4j into **watsonx Orchestrate** through the Model Context Protocol. Orchestrate registers the Neo4j finance MCP server as an **MCP toolkit**, so its tools appear next to every other tool an agent can use. The server runs behind an AWS AgentCore gateway that a Cognito OAuth client credentials flow protects. An Orchestrate **managed connection** holds the credentials and fetches the tokens, so no agent holds a secret.

The integration point is the toolkit and its connection. The server exposes two tools, one for the graph schema and one for read-only Cypher, and Orchestrate imports both. A LangGraph agent, `finance_graph_agent`, runs in the **Orchestrate agent runtime** and uses the tools to answer questions such as "Which account products exist and how many accounts use each one?" New questions need no new tool. The folder has the connection script, the agent, a deploy script, and a local runner.

### Neo4j integration with the watsonx Orchestrate custom knowledge service source

[`custom_knowledge_service/`](custom_knowledge_service/README.md) integrates Neo4j into **watsonx Orchestrate** through its **custom service knowledge source**. Orchestrate calls out to a service that you host, and the Neo4j graph sits behind it. A small FastAPI service on AWS Lambda implements the Orchestrate **custom service** request and response format. It searches the policy chunks in Neo4j and, for a named business, runs the fraud screen, then returns passages with their rule codes.

The integration point is the knowledge source itself. An Orchestrate **knowledge base** of type custom service holds the service URL and a **managed connection** with the key, so Orchestrate treats the graph like any other knowledge source. The test agent, `graph_knowledge_demo`, has no tools. It answers from that source alone, for example by listing the three fraud rules that Ortega Builders matches. Any other agent on the tenant can add the same source. The folder has the service, the Lambda build and deploy scripts, and the upload script.

### Other agent demo scenarios

The two **watsonx Orchestrate** demos use Python tools on a **managed connection**, with the graph as the source of truth. They run against the same graph as the local agent:

- **[Demo One: Staff and fraud](#orchestrate-demo-one-staff-and-fraud):** `bank_supervisor` routes a relationship manager's loan question to a credit specialist, a fraud specialist, and a policy agent, as **multi-agent collaborators**. The scenarios are E to J.
- **[Demo Two: Customer support](#orchestrate-demo-two-customer-support):** `banking_support` answers the signed-in customer from the graph, and `banking_baseline` answers from the policy documents alone, through the built-in **knowledge base**. The scenarios are A to D, and they follow below.

The agent also runs locally in plain Python. See [Running locally](#running-locally).

### Choose your path

| Path | What you get | Parts to follow, in order | First and last command after Common setup |
|---|---|---|---|
| Local only | The agent and the vector-only baseline in plain Python | Common setup, Running locally | `make test`, then `make chat` |
| Demo One: Staff and fraud | `bank_supervisor` with three specialists | Common setup, then [Orchestrate Demos Setup](#orchestrate-demos-setup), then [Demo One](#orchestrate-demo-one-staff-and-fraud) | `make wxo-env`, then `uv run fraud-demo-walkthrough` |
| Demo Two: Customer support | `banking_support` against `banking_baseline` | Common setup, then [Orchestrate Demos Setup](#orchestrate-demos-setup), then [Demo Two](#orchestrate-demo-two-customer-support) | `make wxo-env`, then `uv run demo-walkthrough` |

Both Orchestrate paths need the ADK installed and your instance connected first. [watsonx Orchestrate](#watsonx-orchestrate) covers both. [Orchestrate Demos Setup](#orchestrate-demos-setup) builds both demos together, because Demo One reads the knowledge base that Demo Two builds. [Evaluation in Orchestrate](#evaluation-in-orchestrate) scores either one.

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

`eval/scenarios.yaml` also holds five adversarial isolation prompts, `D1` to `D5`. The baseline skips them. The same file lists the expected answer and every checked fact for each scenario.

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

- **Hosted tool runtime:** The demo's Python tools run inside Orchestrate, not on a presenter's laptop. Orchestrate installs each tool's packages and runs the tool on every call.
- **Package allowlist:** Orchestrate checks tool packages against a list the tenant has approved. A tool that needs an unapproved package is rejected at import.
- **Managed connections:** Orchestrate stores the Neo4j and OpenAI credentials in the `banking_creds` connection. It keeps separate values for draft and live, and the tools read them at run time.
- **Draft and live versions:** Each agent has a draft version for testing and a live version for users. Publishing copies the tested draft to live.
- **Hosted chat:** Orchestrate provides the chat interface for both agents. The demo needs no web app.
- **Managed knowledge base:** Orchestrate chunks, embeds, and indexes the uploaded policy documents for the baseline agent. The demo writes no ingestion code for it.
- **Model gateway:** Both agents call their chat model through Orchestrate. The agents hold no model API key.

### Coming next

These items are planned or in progress:

- **watsonx.ai models:** The embeddings, the local agent, and the local baseline move from OpenAI to watsonx.ai models. The graph is rebuilt with watsonx.ai embeddings. Today the Orchestrate agents use the Orchestrate model `bedrock/openai.gpt-oss-120b-1:0`, and embeddings use OpenAI.

These items are optional extras that can be added later:

- **Architect view:** A Streamlit app shows a chat pane next to a graph pane. The graph pane draws the nodes and policy chunks behind the last answer.
- **Architect agent with MCP:** A second Orchestrate agent uses the Neo4j MCP server. It can read the graph schema and run read-only Cypher over the whole graph.
- **GraphRAG as a knowledge base:** The policy search runs as a small web service. Orchestrate calls it as a custom search knowledge base.
- **ADK evaluation:** The scenarios become ADK evaluation test cases. These also check the order of tool calls.
- **watsonx.governance:** The agent is registered for monitoring.
- **Docling:** The policy documents are rendered as PDFs. Docling parses them before chunking.

[`docs/decision_log.md`](docs/decision_log.md) records the decisions, the model results, and the problems found so far.

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

Change to the project directory:

```bash
cd ibm-watsonx/graphrag-banking
```

Install the locked environment:

```bash
uv sync
```

Copy the sample settings, then fill in the Aura and OpenAI values:

```bash
cp env.sample .env
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

Check the Aura connection. The command runs `RETURN 1` against Aura:

```bash
make check
```

Wipe the database, then generate, validate, and load everything:

```bash
make rebuild
```

`make rebuild` deletes every node in the target database. Point `.env` at a database used only for this demo.

Each pipeline step is a console script, so it runs as `uv run <command>`. The `Makefile` wraps them. The [Command reference](docs/reference.md#command-reference) lists every target and what it runs.

`make ingest` ends with `build-groups`, which finds the connected groups for the fraud demo. It creates an Aura Graph Analytics session, which is billed while it runs.

Use `make rebuild`, not `make ingest` twice. Each `build-policy-graph` run writes new `Chunk` nodes, so a second ingest without a reset duplicates the chunks.

---

## Running locally

Finish [Common setup](#common-setup) first. Then run the unit tests and the live checks against the graph:

```bash
make test
```

Chat with the agent as the demo customer:

```bash
make chat
```

The sections below cover chat, the baseline, and the evaluation. The [Command reference](docs/reference.md#command-reference) lists every `make` target.

### Chat

`uv run chat` signs in as `DEMO_CUSTOMER_ID`. After each answer it prints a trace of the tools called, the Cypher they ran, and the policy chunks retrieved. Press Ctrl-D to quit.

See [The hero scenarios](#the-hero-scenarios) for sample questions.

### Baseline

`uv run baseline-rag` answers with vector search over the policy chunks only. It has no access to the customer's accounts. With no argument it runs the Scenario A to D prompts:

```bash
uv run baseline-rag
```

With a question argument it runs only that question:

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

Run every scenario three times:

```bash
uv run eval-local
```

| Flag | Default | Effect |
|---|---|---|
| `--runs N` | `3` | Runs each scenario N times |
| `--scenario ID` | all | Runs only this scenario. Repeat the flag to run several. |
| `--persona NAME` | `customer` | Runs only the scenarios of this persona: `customer` or `staff`. A scenario with no `persona` is a customer's. |

Run each scenario ten times:

```bash
uv run eval-local --runs 10
```

Run only Scenarios A and C:

```bash
uv run eval-local --scenario A --scenario C
```

It exits with status 1 if any check fails. Results are written to `eval/results/eval-<UTC timestamp>.json`.

---

## watsonx Orchestrate

The Orchestrate demos use the same graph, tools, and instructions as the local agent. Nothing is rewritten for Orchestrate. The scripts in `orchestrate/` copy the local code into the shape Orchestrate expects.

Finish [Common setup](#common-setup) first, including `make rebuild`. The Orchestrate demos also need:

- A watsonx Orchestrate instance on IBM Cloud. IBM offers a [free 30-day trial](https://www.ibm.com/account/reg/us-en/signup?formid=urx-52753).
- The watsonx Orchestrate Agent Development Kit, or ADK. It provides the `orchestrate` command.

This section sets up the ADK, your connection, and both demos once, then covers the two demos on the same graph:

- **[Demo One: Staff and fraud](#orchestrate-demo-one-staff-and-fraud):** `bank_supervisor` and three specialists help a relationship manager review a loan application.
- **[Demo Two: Customer support](#orchestrate-demo-two-customer-support):** `banking_support` and `banking_baseline` answer a signed-in customer.

[Evaluation in Orchestrate](#evaluation-in-orchestrate) scores either demo.

### Install the ADK

`uv sync` does not install the ADK. Install it once as a uv tool, so `orchestrate` is on your `PATH` in every shell:

```bash
uv tool install ibm-watsonx-orchestrate --with neo4j --with openai
```

Check the install:

```bash
orchestrate --version
```

`orchestrate tools import` loads the tool file on your machine to read the tool definitions. The tool file imports `neo4j`, so the ADK's own environment needs `neo4j` and `openai` too. Without them, `make wxo-tools` fails with `No module named 'neo4j'`. Orchestrate still installs the pinned versions from `uv.lock` when it runs the tools.

The ADK needs Python 3.11 or later. uv downloads a suitable Python if none is installed. If the shell still reports `orchestrate: command not found`, add the uv tool directory to your path:

```bash
uv tool update-shell
```

Then open a new terminal.

To upgrade the ADK later, run this command. The upgrade keeps the `--with` packages.

```bash
uv tool upgrade ibm-watsonx-orchestrate
```

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

`make wxo-env` runs `orchestrate/connect_env.sh`. The script adds the environment the first time, then logs in with the API key from `.env`, so nothing prompts. The ADK picks the auth type from the instance URL. If the login fails with `Error getting IBM_IAM Token` or a similar token error, set `WO_AUTH_TYPE` in `.env` to the right type. The valid types are `ibm_iam`, `mcsp`, `mcsp_v1`, `mcsp_v2`, `cpd`, and `k8s`. Then remove the environment:

```bash
orchestrate env remove -n <env>
```

Add the environment again with the new type:

```bash
make wxo-env
```

The login expires every two hours. When a command fails with an authentication error, run `make wxo-env` again.

### Check the tenant

The demos use two models. The specialists and the customer agents use the Orchestrate model `bedrock/openai.gpt-oss-120b-1:0`. `bank_supervisor` uses `virtual-model/openai/gpt-6-luna`, which comes from the tenant's custom model provider. Check that your tenant offers both:

```bash
orchestrate models list
```

The tools also need the pinned `neo4j` and `openai` versions on the tenant's package allowlist. [How the setup works](#how-the-setup-works) lists the current pins and how to change the model.

### Orchestrate Demos Setup

Build both demos once. Demo One reads the `banking_policies` knowledge base that Demo Two builds, so one setup covers both.

Before you start:

- Finish [Common setup](#common-setup), including `make rebuild`. It loads the fraud data and runs `build-groups`, which creates a billed Aura Graph Analytics session while it runs.
- Be logged in to your instance. The first command in [Build both demos](#build-both-demos) logs in.

#### What the setup creates

| Orchestrate object | Name | Built from |
|---|---|---|
| Connection | `banking_creds` | `.env`. It holds the Aura credentials, the OpenAI key and embedding model, `DEMO_CUSTOMER_ID`, and `DEMO_AS_OF`, for both draft and live. |
| Python tools | the six tools in `tools.py` | `orchestrate/tools/banking_tools.py`, a thin wrapper per tool |
| Agent | `banking_support` | `prompts/agent_instructions.md`, with the date written in |
| Knowledge base | `banking_policies` | The twelve documents in `data/policies/` |
| Agent | `banking_baseline` | `orchestrate/baseline_agent.yaml` |
| Connection | `banker_creds` | `.env`. It holds the Aura credentials, `DEMO_BANKER_ID`, and `DEMO_AS_OF`, for both draft and live. `DEMO_BANKER_ID` fixes every chat to the banker `RM-07`, so the model never chooses whose book it reads. |
| Python tools | seven staff tools: `find_my_client`, `get_application`, `check_lending_rules`, `get_beneficial_owners`, `get_connected_group`, `find_circular_flows`, `screen_business` | `orchestrate/tools/staff_banking_tools.py`, a thin wrapper per tool around `src/graphrag_banking/staff_tools.py` |
| Agent | `banking_policy` | `orchestrate/banking_policy_agent.yaml`. It answers general policy questions from `banking_policies` and has no tools. |
| Agents | `credit_analyst`, `fraud_investigator` | `orchestrate/credit_analyst_agent.yaml` and `orchestrate/fraud_investigator_agent.yaml` |
| Agent | `bank_supervisor` | `orchestrate/bank_supervisor.yaml`. It routes each question to the three specialists as collaborators and has no tools of its own. |

#### Build both demos

Log in to your instance:

```bash
make wxo-env
```

Build the customer demo, which creates `banking_creds`, six tools, `banking_support`, `banking_policies`, and `banking_baseline`:

```bash
make wxo-setup
```

Build the staff demo, which creates `banker_creds`, seven tools, `banking_policy`, the two specialists, and `bank_supervisor`:

```bash
make wxo-staff-setup
```

Each target is safe to re-run, and you can run any of them alone. The [Command reference](docs/reference.md#command-reference) lists what each target runs and needs first.

Wait until the knowledge base is ready. This command shows its status:

```bash
orchestrate knowledge-bases status -n banking_policies
```

Check that every customer demo object exists and is wired together:

```bash
make wxo-check
```

Publish `banking_support` and `banking_baseline` to live:

```bash
make wxo-deploy
```

`make wxo-check` and `make wxo-deploy` cover only the customer demo's objects. The staff agents run on draft, and `make wxo-deploy` does not publish them. To check the staff objects, run the ADK list commands. This one shows `banker_creds` for draft and live:

```bash
orchestrate connections list
```

This one shows the seven staff tools:

```bash
orchestrate tools list
```

This one shows `banking_policy`, `credit_analyst`, `fraud_investigator`, and `bank_supervisor`:

```bash
orchestrate agents list
```

#### Update after changing code

The tenant keeps the tools and agents it last imported. A change in the repo reaches Orchestrate only after you import again. Orchestrate checks each tool call against the schema it imported, so a stale tool rejects arguments that the new code accepts.

After a change to `src/graphrag_banking/tools.py`, `orchestrate/tools/banking_tools.py`, or `prompts/agent_instructions.md`, import the customer tools again:

```bash
make wxo-tools
```

Then import `banking_support` again. This step rebuilds its instructions:

```bash
make wxo-agent
```

To repeat the whole customer setup in one command, run this instead of the two above:

```bash
make wxo-setup
```

After a change to `src/graphrag_banking/staff_tools.py`, `orchestrate/tools/staff_banking_tools.py`, or the staff agent YAML files, repeat the staff setup:

```bash
make wxo-staff-setup
```

If you published the customer agents, publish them again. The staff agents run on draft, so they need no publish step.

```bash
make wxo-deploy
```

#### How the setup works

Each customer tool wrapper reads `banking_creds`, opens a Neo4j driver, and calls the matching function in `tools.py`. The customer ID comes from the connection, so the model never chooses whose data it reads. Each wrapper also takes its description from the matching function, so the agent sees the same tool descriptions in Orchestrate as it does locally.

`build_tools.sh` assembles the tool package in `orchestrate/build/` on every run. It copies `tools.py` as `banking_queries.py` and `embeddings.py` next to the wrapper, so `tools.py` stays the single source of truth. `build_agent.py` fills the date into the instructions the same way the local agent does, because Orchestrate instructions have no placeholders. [Update after changing code](#update-after-changing-code) lists the commands to run after a change. `orchestrate/build/` is git-ignored.

The tools install `neo4j` and `openai`. `build_tools.sh` exports their pins from `uv.lock` with `uv export` and keeps only those two, so uv stays the source of truth. The current pins, `neo4j==6.4.0` and `openai==3.29.0`, are on the tenant package allowlist.

The customer agents use the Orchestrate model `bedrock/openai.gpt-oss-120b-1:0`. To use another model from `orchestrate models list`, set `ORCHESTRATE_MODEL` for `build_agent.py` and edit `llm` in `orchestrate/baseline_agent.yaml`.

`make wxo-staff-setup` runs `wxo-staff-connection`, `wxo-staff-tools`, `wxo-policy`, `wxo-staff-agents`, and `wxo-supervisor` in that order. The connection step runs `create_staff_connection.sh`, which needs `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `DEMO_BANKER_ID`, and `DEMO_AS_OF` in `.env`. It stops if one is missing. `wxo-policy` needs the `banking_policies` knowledge base from `make wxo-setup`. `wxo-supervisor` runs last, because `bank_supervisor` lists the other three agents as collaborators.

#### Optional: referral workflow

The `fraud_referral` workflow lets Dana confirm a referral in the chat. It then writes a `FraudReferral` node to the graph and sends a review form to Sam Price. It is built but not on the tenant, and `bank_supervisor` does not call it yet. `FRAUD_REVIEWER_EMAIL` is not read from `.env`, so set it in the shell:

```bash
export FRAUD_REVIEWER_EMAIL=<tenant login for Sam Price>
```

Import the two referral tools on `banker_creds`, then the flow:

```bash
./orchestrate/build_referral_tools.sh
```

After a referral has been written, delete every `FraudReferral` and leave the rest of the graph alone, so the next run starts clean:

```bash
make demo-reset
```

### Orchestrate Demo One: Staff and fraud

A relationship manager, Dana Whitfield (`RM-07`), asks whether Ortega Builders can have a $400,000 line of credit. A credit specialist alone says yes, because the revenue supports the line and the amount is under Dana's limit. A supervisor that also asks a fraud specialist finds the application is part of a fraud ring and recommends a referral.

**What it shows**

- **Multi-agent routing:** `bank_supervisor` has no tools. It sends each question to `credit_analyst`, `fraud_investigator`, or `banking_policy` as collaborators and writes one answer.
- **Python tools on a managed connection:** Seven staff tools query Neo4j through the `banker_creds` connection, which fixes the signed-in banker to Dana.
- **Policy answers from a knowledge base:** `banking_policy` answers from the `banking_policies` knowledge base.
- **Graph patterns:** The fraud checks find multi-hop `OWNS` links, phones and devices shared across businesses, circular money flows, a `ConnectedGroup` with centrality scores, and each `FraudRule` linked to its policy `Chunk`.
- **Tipping-off guard:** The follow-up answer gives Dana safe wording and does not mention the referral, under `AML-NO-TIPOFF`.
- **Proof in Neo4j Aura:** A Cypher query returns the graph behind the answer, so the audience can check each fact.

**Run it**

```bash
uv run fraud-demo-walkthrough
```

[`docs/fraud-demo-walkthrough.md`](docs/fraud-demo-walkthrough.md) is the presenter script. It has the story, the cast, the steps, the prompts, the expected answers, and the runner options, including `--steps` to run one step or a range.

### Orchestrate Demo Two: Customer support

A customer, Marcus Okafor (`C-1001`), asks why his wire transfer to Acme Corp failed and whether he will be charged a penalty fee. `banking_baseline` answers from the policy documents alone, with generic reasons a wire can fail. `banking_support` follows the graph links and says the wire is held, not failed, and that Premium Checking waives both wire fees. The expected answers for the other scenarios are in [The hero scenarios](#the-hero-scenarios).

**What it shows**

- **Native agent with Python tools:** The `banking_support` agent is defined in YAML and imported with the ADK CLI. It calls six custom Python tools that query Neo4j.
- **Built-in knowledge base as the baseline:** The `banking_baseline` agent answers from an Orchestrate knowledge base that holds the same policy documents. It uses vector search only, so it gives a generic answer. Asking both agents the same question shows what the graph adds.
- **Connection for secrets and identity:** The `banking_creds` connection holds the Neo4j credentials, the embedding key, and the signed-in customer ID. The tools read the customer ID from the connection, so the model never chooses whose data it reads.
- **Data isolation:** The tools only reach accounts the signed-in customer holds. A prompt that asks for another person's account gets no data from that account.
- **One codebase for local and Orchestrate:** Build scripts copy the local tools and instructions into the shape Orchestrate expects. A change to the local code reaches Orchestrate on the next build.
- **Approved packages only:** The tools need only the `neo4j` and `openai` packages. Their versions come from `uv.lock` and pass the tenant's package allowlist.
- **Draft and live:** Both agents run as drafts, and `make wxo-deploy` publishes them to live with one command.
- **Proof in Neo4j Aura:** A Cypher query returns the path behind an answer. The audience can check each fact against the graph.

**Run it**

```bash
uv run demo-walkthrough
```

[`docs/customer-demo-walkthrough.md`](docs/customer-demo-walkthrough.md) is the presenter script. It has the eleven steps, the commands, and the runner options, including `--steps` to run one step or a range.

### Evaluation in Orchestrate

`make wxo-eval` sends the same scenarios as `make eval` to Orchestrate agents and scores the answers with the same checks. Finish [Orchestrate Demos Setup](#orchestrate-demos-setup) first, and run `make wxo-env` if the two-hour login has expired. It prints a Summary table with the columns Agent, Scenario, Result, Runs passed, and Checks passed, then `Overall: N of M runs passed`. A run passes only if it completed and every check passed. It exits with status 1 if any run fails. Results are written to `eval/results/wxo-eval-<UTC timestamp>.json`.

The staff scenarios are in `eval/scenarios.yaml`:

| Scenario | Title |
|---|---|
| E | The fraud ring |
| F | A clean application |
| G | The false alarm |
| H | Tipping off |
| I | Limits outside the book |
| I1 | Limits outside the book, with a coverage claim |
| J | The fraud referral. It needs the [referral workflow](#optional-referral-workflow). |

| Variable | Default | Effect |
|---|---|---|
| `AGENTS` | `banking_support` | Comma-separated agent names, for comparing models |
| `SCENARIOS` | `A,B,C,D` | Comma-separated scenario IDs, or `all` |
| `PERSONA` | `customer` | The persona whose scenarios `all` runs: `customer` or `staff` |
| `RUNS` | `1` | Runs each scenario N times. Each run starts a new chat thread. |
| `SAME_THREAD` | unset | `1` sends the scenarios in order in one thread per run. Each turn is scored on its own answer and tool calls. |
| `REFERRAL_FLOW` | unset | `1` runs scenarios `E` then `J` in one thread and ignores `SCENARIOS`. After `J`, it presses Confirm on the `fraud_referral` flow's form and waits for the message with the referral ID. It never answers the review form that follows. It needs the [referral workflow](#optional-referral-workflow). Run `make demo-reset` first, so the referral is `REF-0001`. |
| `SUPERVISOR_CHECK` | unset | `1` also runs `eval/eval-scripts/supervisor_check.py` on the saved results. It checks that the supervisor kept each collaborator's facts and added none. Traces are cached in `TRACES_DIR`, which defaults to `eval/results/traces`. |

Run each scenario three times:

```bash
make wxo-eval RUNS=3
```

Compare two agents on Scenarios A and B:

```bash
make wxo-eval AGENTS=banking_support,banking_support_frontier SCENARIOS=A,B
```

Send Scenarios C and D in one thread:

```bash
make wxo-eval SAME_THREAD=1 SCENARIOS=C,D
```

Score the supervisor on Scenarios E and H, then check that it kept its collaborators' facts:

```bash
make wxo-eval AGENTS=bank_supervisor SCENARIOS=E,H SUPERVISOR_CHECK=1
```

Variables you set on the `make` command line reach the script, including `PERSONA`, `REFERRAL_FLOW`, `SUPERVISOR_CHECK`, and `TRACES_DIR`, which the `Makefile` does not list.

---

## More documentation

- **[Customer demo walkthrough](docs/customer-demo-walkthrough.md):** The presenter script for Demo Two.
- **[Fraud demo walkthrough](docs/fraud-demo-walkthrough.md):** The presenter script for Demo One.
- **[Graph schema](docs/schema.md):** The node labels, relationships, and indexes.
- **[Reference](docs/reference.md):** The data files, every command, and the project layout.
- **[Troubleshooting and cleanup](docs/troubleshooting.md):** The environment checks, common failures, and how to remove the demo from your tenant.
- **[Decision log](docs/decision_log.md):** The decisions, model results, and problems found.
