# Reference

This page holds the data files, the command reference, and the project layout. The [README](../README.md) explains each step in context.

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

After editing `policy_facts.yaml` or a template, rebuild the graph. The rebuild re-renders the policies, and they must be committed.

```bash
make rebuild
```

[`data/README.md`](../data/README.md) documents the CSV columns, controlled values, and hero ID ranges.

## Command reference

This is the one place that lists every command, grouped by when you run it. Run all of them from the project root. The README explains each step in context. "Needs first" names what must exist before the command works.

### Graph

| Command | What it runs | Needs first | What it does |
|---|---|---|---|
| `make sync` | `uv sync` | uv | Installs the locked environment |
| `make check` | `check-connection` | `.env` | Verifies the Aura connection |
| `make reset` | `reset-db` | `.env` | Deletes all nodes and drops the constraints and indexes |
| `make ingest` | `generate-data`, `render-policies`, `validate-data`, `load-structured`, `build-policy-graph`, `build-groups` | `.env` and an empty graph | Builds the data and loads all graph layers. `build-groups` creates a billed Aura Graph Analytics session. |
| `make rebuild` | `make reset`, then `make ingest` | `.env` | Rebuilds the graph from empty. Use it instead of running `make ingest` twice. |
| `uv run build-groups` | `build-groups` | A built graph | Rebuilds the connected groups without a full reset. It creates a billed Aura Graph Analytics session. |
| `make demo-reset` | `referral_tools --cleanup` | A built graph | Deletes every `FraudReferral` and leaves the rest of the graph alone. It matters only after the referral workflow has written one. |

### Local agent

| Command | What it runs | Needs first | What it does |
|---|---|---|---|
| `make chat` | `chat` | `make rebuild` | Interactive agent CLI |
| `make baseline` | `baseline-rag` | `make rebuild` | Vector-only baseline over the policy chunks |
| `make eval` | `eval-local` | `make rebuild` | Scores the agent on the customer scenarios. See [Evaluation](../README.md#evaluation). |
| `make test` | `pytest` | `make rebuild` | Runs the test suite, including live checks against the graph |
| `make lint` | `ruff check src` | `make sync` | Lints the source |

### Orchestrate: environment and customer demo

| Command | What it runs | Needs first | What it does |
|---|---|---|---|
| `make wxo-env` | `orchestrate/connect_env.sh` | The ADK and the `WO_*` values in `.env` | Adds the environment and logs in. Re-run it when the two-hour login expires. |
| `make wxo-setup` | `wxo-connection`, `wxo-tools`, `wxo-agent`, `wxo-baseline`, in order | `make wxo-env` | Builds the whole customer demo |
| `make wxo-connection` | `orchestrate/create_connection.sh` | `make wxo-env` | Creates the `banking_creds` connection from `.env` |
| `make wxo-tools` | `orchestrate/build_tools.sh` | `make wxo-connection` | Imports the six tools |
| `make wxo-agent` | `orchestrate/build_agent.py`, then `orchestrate agents import` | `make wxo-tools` | Imports `banking_support` |
| `make wxo-baseline` | `orchestrate/build_baseline.sh` | `make wxo-env` | Imports the `banking_policies` knowledge base and `banking_baseline` |
| `make wxo-check` | `orchestrate/check_setup.py` | `make wxo-setup` | Checks the customer demo's objects only |
| `make wxo-list` | `orchestrate/list_demo.py` | `make wxo-env` | Lists the connections, tools, knowledge base and agents that the two demos use and that are saved in the active environment. It leaves out everything else in the tenant. |
| `make wxo-deploy` | `orchestrate agents deploy` | `make wxo-setup`, tested in preview | Publishes `banking_support` and `banking_baseline` to live. It does not publish the staff agents. |

### Orchestrate: staff and fraud demo

| Command | What it runs | Needs first | What it does |
|---|---|---|---|
| `make wxo-staff-setup` | `wxo-staff-connection`, `wxo-staff-tools`, `wxo-policy`, `wxo-staff-agents`, `wxo-supervisor`, in order | `make wxo-setup` | Builds the whole staff demo |
| `make wxo-staff-connection` | `orchestrate/create_staff_connection.sh` | `make wxo-env` and `DEMO_BANKER_ID` in `.env` | Creates the `banker_creds` connection |
| `make wxo-staff-tools` | `orchestrate/build_staff_tools.sh` | `make wxo-staff-connection` | Imports the seven staff tools |
| `make wxo-policy` | `orchestrate agents import` of `banking_policy_agent.yaml` | `make wxo-baseline`, for the knowledge base | Imports `banking_policy` |
| `make wxo-staff-agents` | `orchestrate agents import` of the two specialist YAML files | `make wxo-staff-tools` | Imports `credit_analyst` and `fraud_investigator` |
| `make wxo-supervisor` | `orchestrate agents import` of `bank_supervisor.yaml` | `make wxo-policy` and `make wxo-staff-agents` | Imports `bank_supervisor` |
| `./orchestrate/build_referral_tools.sh` | itself | `banker_creds` and `FRAUD_REVIEWER_EMAIL` | Imports the two referral tools and the `fraud_referral` flow. See [Optional: referral workflow](../README.md#optional-referral-workflow). |

### Evaluation and walkthroughs

| Command | What it runs | Needs first | What it does |
|---|---|---|---|
| `make wxo-eval` | `eval/eval-scripts/wxo_eval.sh` | The setup for the demo you score | Scores the scenarios against Orchestrate agents. See [Evaluation in Orchestrate](../README.md#evaluation-in-orchestrate). |
| `uv run demo-walkthrough` | `demo-walkthrough` | `make wxo-setup` | Runs the eleven-step customer walkthrough. See [Customer demo walkthrough](customer-demo-walkthrough.md). |
| `uv run fraud-demo-walkthrough` | `fraud-demo-walkthrough` | `make wxo-staff-setup` | Runs the eleven-step staff and fraud walkthrough. See [Fraud demo walkthrough](fraud-demo-walkthrough.md). |

### ADK commands

The `orchestrate` commands come from the ADK and act on the active environment.

| Command | What it does |
|---|---|
| `orchestrate env list` | Lists the environments and marks the active one |
| `orchestrate models list` | Lists the models the tenant offers |
| `orchestrate connections list` | Lists the connections and their draft and live settings |
| `orchestrate tools list` | Lists the imported tools |
| `orchestrate agents list` | Lists the agents |
| `orchestrate knowledge-bases status -n banking_policies` | Shows whether the knowledge base is ready |

## Layout

```
graphrag-banking/
├── pyproject.toml                  dependencies and console scripts
├── uv.lock
├── env.sample
├── Makefile
├── docs/
│   ├── customer-demo-walkthrough.md  customer demo script for a presenter
│   ├── fraud-demo-walkthrough.md   staff and fraud demo script for a presenter
│   ├── schema.md                   graph labels, relationships, and indexes
│   ├── reference.md                data, command reference, and this layout
│   ├── troubleshooting.md          environment checks, failures, and removing the demo
│   └── decision_log.md             decisions, model results, and problems found
├── data/                           see the Data section
├── prompts/
│   └── agent_instructions.md
├── eval/
│   ├── scenarios.yaml
│   ├── eval-scripts/               Orchestrate evaluation
│   │   ├── wxo_eval.sh             runs run_agent.py, then score.py (make wxo-eval)
│   │   ├── run_agent.py            sends prompts to an agent and saves the answers
│   │   ├── score.py                scores saved answers with the eval-local checks
│   │   ├── supervisor_check.py     checks the supervisor kept the collaborators' facts
│   │   └── traces.py               fetches a trace's model calls as JSON
│   └── results/                    eval-local and wxo-eval output
├── orchestrate/                    watsonx Orchestrate demo
│   ├── connect_env.sh              adds and activates the Orchestrate environment from .env
│   ├── check_setup.py              checks the demo objects exist and are wired (make wxo-check)
│   ├── list_demo.py                lists the demo objects in the active environment (make wxo-list)
│   ├── create_connection.sh        banking_creds connection from .env
│   ├── build_tools.sh              assembles and imports the six tools
│   ├── build_agent.py              writes the banking_support agent YAML
│   ├── build_baseline.sh           knowledge base and baseline agent
│   ├── baseline_agent.yaml         banking_baseline agent
│   ├── proof_query.cypher          Scenario A subgraph for the Aura console
│   ├── fraud_proof_query.cypher    fraud ring subgraph for the Aura console
│   ├── banking_policy_agent.yaml   banking_policy agent, answers from the knowledge base
│   ├── create_staff_connection.sh  banker_creds connection from .env
│   ├── build_staff_tools.sh        assembles and imports the staff tools
│   ├── credit_analyst_agent.yaml   credit_analyst agent
│   ├── fraud_investigator_agent.yaml  fraud_investigator agent
│   ├── bank_supervisor.yaml        bank_supervisor agent, routes banker questions to the specialists
│   ├── build_referral_tools.sh     assembles and imports the referral tools and the fraud_referral flow
│   ├── referral_proof_query.cypher Scenario J referral subgraph for the Aura console
│   ├── routing_check_supervisor.yaml  temporary supervisor for a routing check, not part of wxo-setup
│   ├── flows/
│   │   └── fraud_referral_flow.py  fraud_referral workflow
│   ├── tools/
│   │   ├── banking_tools.py        Orchestrate wrappers around tools.py
│   │   ├── staff_banking_tools.py  Orchestrate wrappers around staff_tools.py
│   │   └── referral_banking_tools.py  Orchestrate wrappers around referral_tools.py
│   └── build/                      generated by the scripts, git-ignored
├── src/graphrag_banking/
│   ├── config.py                   settings from .env
│   ├── embeddings.py               embed(), shared by tools and ingestion
│   ├── models.py                   neo4j-graphrag Embedder wrapper
│   ├── facts.py                    loads policy_facts.yaml and hero_fixtures.yaml
│   ├── generate_data.py
│   ├── generate_fraud.py           loan fraud data
│   ├── render_policies.py
│   ├── validate_data.py
│   ├── validate_fraud.py           fraud checks, called from validate-data
│   ├── check_connection.py         checks the Aura instance is reachable
│   ├── reset_db.py
│   ├── load_structured.py          structured and rule layers
│   ├── build_policy_graph.py       document layer and vector index
│   ├── build_groups.py             connected groups from Aura Graph Analytics
│   ├── tools.py                    agent tools
│   ├── staff_tools.py              banker-scoped tools for the staff agents
│   ├── referral_tools.py           tools for the fraud referral flow
│   ├── agent.py                    LangGraph agent
│   ├── chat.py
│   ├── baseline_vector_rag.py
│   ├── eval_local.py
│   ├── demo_walkthrough.py         customer demo walkthrough (demo-walkthrough)
│   └── fraud_demo_walkthrough.py   staff and fraud demo walkthrough (fraud-demo-walkthrough)
└── tests/
    ├── fixtures/                   saved supervisor run and trace
    ├── test_graph.py               live checks against the built graph
    ├── test_groups.py
    ├── test_track_b.py             unit tests, no database needed
    ├── test_eval_checks.py         eval checks and supervisor_check.py, no tenant needed
    ├── test_staff_tools.py
    ├── test_referral_tools.py
    ├── test_run_agent_flow.py
    ├── test_demo_walkthrough.py
    └── test_fraud_demo_walkthrough.py
```
