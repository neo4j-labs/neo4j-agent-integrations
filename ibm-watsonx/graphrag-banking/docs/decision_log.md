# Decision Log

This log records the decisions, model results, and problems from Phases 0 to 3 and Phase 5. It is the handoff context that PRD section 9.4 asks for. The PRD remains the source of truth for scope and design.

## Decisions

### D2. Phase 5 route

**Status:** Decided. Route A is built and passes Scenarios A to D in the Orchestrate preview chat.

**Decision:** Use Route A, a native Orchestrate agent with Python tools. It shows Orchestrate's own agent model, which matters more to an IBM audience than importing an outside agent.

**What Phase 3 already supports:**

- `tools.py` follows the portability rule. It imports only the `neo4j` driver and `embeddings.embed`, so each tool can become an Orchestrate Python tool unchanged.
- Each tool takes a `ToolContext` that carries the customer ID and connection settings. The model never supplies the customer. Under Route A, a `key_value` connection fills the same role.
- `prompts/agent_instructions.md` uses `${demo_as_of}` and `${demo_as_of_long}` placeholders. For Orchestrate, write the date into the agent YAML literally.

**Q5, partly answered:** The tenant's package allowlist accepts `neo4j==6.4.0` and `openai==3.29.0`. A probe tool that imported both was accepted. The tools therefore keep OpenAI embeddings through `embed()`, and the graph did not need a rebuild for Phase 5. Whether the allowlist accepts `ibm-watsonx-ai` is not tested yet. Phase 4 needs that answer.

**How Route A was built:** README section "watsonx Orchestrate" describes the result. The tools, instructions, and graph are the same as the local agent's. The scripts in `orchestrate/` copy `tools.py` and `prompts/agent_instructions.md` into the shape Orchestrate expects, so neither file has an Orchestrate copy to keep in sync.

### D3. Proof beat

**Status:** Decided. The query is committed as `orchestrate/proof_query.cypher`.

**Decision:** Use a saved query in Aura that shows the Scenario A subgraph for `C-1001`. It works alongside the Orchestrate agent and shows Neo4j's own tools. Aura saved queries belong to the user who saves them, so each presenter saves the committed query into their own console.

**Phase 3 stand-in:** `uv run chat` prints a trace of the tools called, the Cypher run, and the chunks retrieved.

## Phase 3 model and results

**Models:** The agent uses OpenAI `gpt-5.6-terra` through `ChatOpenAI` with the Responses API. Embeddings use `text-embedding-3-small` with 1536 dimensions. The vector-only baseline uses the same chat model and embedder, so the beat 1 comparison is fair.

The first two eval runs used `gpt-4.1` at temperature 0. The switch to `gpt-5.6-terra` needed two changes:

- GPT-5.6 models accept only the default temperature of 1. The agent and the baseline no longer set a temperature, so answers vary from run to run. The 10-run pass rate is the measure to trust, not a single run.
- On Chat Completions, GPT-5.6 rejects function tools while reasoning is on. The agent uses the Responses API, so it keeps reasoning and can still call tools. The baseline calls no tools, so it stays on Chat Completions.

**Agent:** The agent is LangGraph's prebuilt ReAct agent. Each `run_agent` call is a fresh conversation. `uv run chat` keeps one conversation across turns.

**eval-local results:**

| Run | Scenarios | Result |
|---|---|---|
| First live run, 1 run each | A to D, D1 to D5 | A, B, and C failed. D and D1 to D5 passed with no leaks. |
| After the first fixes, 3 runs each | A to D, D1 to D5 | 27 of 27 passed. Manual review was clean. |
| Final pass, 10 runs each | A to D, D1 to D5 | To be filled in after the run. |

The final pass runs on `gpt-5.6-terra` with the current data, which includes Marcus's Emergency Fund. The first two runs used `gpt-4.1` and predate the Emergency Fund.

**Baseline behavior:** `uv run baseline-rag` behaves as PRD section 4 expects.

- On Scenario A it gives generic reasons a wire can fail and hedges.
- On Scenario B it explains the hold policy but cannot say whether the mortgage is covered.
- On Scenario C it is partly right, because the overdraft policy text answers the general question.
- On Scenario D it has no customer data and refers the customer to support.

## Problems found and how they were resolved

### Data

**Joint account went negative.** An early version of the A-1002 history dropped the balance to -$762.94 in mid-August. The fix raised the opening balance to $4,455.15 and added a $1,248.60 card purchase on October 2 at Cedar Ridge Furniture. The account still ends at $1,800.00.

**Hero history is hand-written.** Background data never adds transactions, alerts, or scheduled payments to a hero account. All hero history lives in `data/hero_fixtures.yaml`, so the scenario answers cannot drift when the background changes. `validate-data` still reconciles every hero balance and checks the conflict rules in PRD section 6.1.

**Background shifts when hero accounts change.** `generate-data` holds the total at the PRD's 350 accounts. Adding a hero account removes one background account, which changes the seeded random sequence. Adding Marcus's Emergency Fund moved the background from 2,974 transactions and 50 alerts to 2,969 transactions and 46 alerts. Hero data is unaffected. Tests should not assert exact background counts.

**Marcus had no savings account.** Scenario C advises linking a savings account for Overdraft Protection, but Marcus held none. A-1003, a Standard Savings account named "Emergency Fund", was added. Marcus holds it alone. It has six $650.00 payroll deposits and a balance of $11,325.00. No Overdraft Protection link exists in the data, so the advice stays a suggestion. `validate-data` checks that no A-1003 amount matches an amount from Sarah's savings, so the Scenario D leak check stays reliable.

### Retrieval

**Overdraft Protection passage was missed.** In the first eval run, the five closest policy chunks for Scenario C did not include the Overdraft Protection section. The $10 transfer fee never reached the model. The fix keeps five vector matches. `search_policies` now also returns each match's next chunk in the same document. Neighbor passages have a null score and sort directly after the match that brought them in.

**Scenario B skipped the hold policy.** After the Emergency Fund was added, B missed the `HOLD-CHECK-NBD` trace fact in 3 of 3 runs. The agent never called `explain_transaction` for the pending deposit. `get_scheduled_payments` already returned every fact the answer needed, so the model had no reason to ask why the deposit was held. Removing other instructions did not change this. The fix is in the tool, not the instructions. Each pending deposit from `get_scheduled_payments` now carries its hold rules, with the policy name and text. The query is shared with `explain_transaction`. A live test checks that the B deposit carries `HOLD-CHECK-NBD`.

### Agent instructions

**Tool order is left to the model.** The instructions once had a "Which tools to use" section that told the agent which tools to call and in what order. It was removed. The tool descriptions are the agent's only guide to choosing tools. If a model picks the wrong tools, the response is to test a stronger model or improve a tool description, not to script the calls.

Two rules in that section were about what to say, not which tool to call. They moved to "How to answer" with the tool names taken out. One quotes fee terms only for the product of the account the customer means. The other lists the facts a coverage answer must state. A smoke run without the coverage rule dropped today's $1,800 available balance from Scenario B.

**Answers left out retrieved facts.** In the first run, the tools returned every fact Scenarios A and B needed. The answers still omitted the wire amount, the date, the fee amounts, and today's available balance. The instructions now require the agent to state these:

- For a transaction, the amount, date, and payee or payer.
- For a waived fee, each fee by name with its amount.
- For a way to avoid a fee, its cost.
- For a coverage question, today's available balance, pending deposits with their dates, the payment amount and date, the projected balance, and the hold policy.

**Style and privacy issues in passing answers.** Review of the 3-run pass found four issues that the eval did not catch. The instructions now cover each one.

- Answers used em-dashes. The agent now avoids them.
- Answers wrote dates as `2026-10-07`. The agent now writes "October 7" and keeps `YYYY-MM-DD` for tool arguments.
- Answers showed account IDs. The agent now names accounts by nickname or product. It also leaves out transaction, payment, and alert IDs.
- On the impersonation prompt, the agent partly answered as Sarah. The agent now keeps answering as the signed-in customer and says it can only help that customer.

**Amounts showed as "$5,000.0".** The tools returned dollar amounts as numbers, and `gpt-5.6-terra` quoted them as returned. The tools now write amounts, balances, and thresholds as strings such as "$5,000.00". The formatting runs last, so the coverage math still uses numbers.

### Evaluation

**A must-not phrase matched a correct answer.** Scenario C's "must not appear" list first held "no overdraft fee". Correct answers say "no overdraft fee is charged if your account is overdrawn by $50 or less." The list now holds only "no overdraft fees", the wording of the Premium Checking claim.

**An echoed account ID is not a leak.** Prompt D3 asks for account A-2001 by ID. The answer may repeat that ID to say it is not among the customer's accounts. D3's "must not appear" list therefore omits A-2001 and keeps Sarah's balance and transaction amounts.

**Some checks need a person.** String matching cannot check whether an answer suggests linking Sarah's savings or presents Marcus's Emergency Fund as Sarah's. `eval/scenarios.yaml` lists these as `manual_review` items. `eval-local` prints them after each run.

### Orchestrate (Phase 5)

**Relative imports fail at runtime.** The ADK checks a multi-file tool locally by importing the tool file as `<package folder>.<file>`, so relative imports pass that check. Orchestrate then runs the tool file as a top-level module, and relative imports fail with "attempted relative import with no known parent package". The wrapper puts its own folder on `sys.path` and imports `banking_queries` and `embeddings` by plain name. That works under both imports. The ADK documentation does not say which import style multi-file tools need. The ADK source shows the local import, in `extract_python_tools`.

**The package folder name must differ from the tool file name.** With both named `banking_tools`, the local check failed with "'banking_tools' is not a package". The folder is now `banking_package`, with an `__init__.py`.

**The knowledge base rejects Markdown.** Built-in knowledge bases accept `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.csv`, `.html`, and `.txt`. `build_baseline.sh` uploads the policy documents as `.txt` copies.

**Hand-copied tool descriptions drift.** The first wrappers repeated the tool docstrings by hand. When Phase 3 removed the "Which tools to use" section and improved the descriptions, the Orchestrate copies were already out of date. Each wrapper now takes its docstring from the matching function in `tools.py`.

**A follow-up in the same chat reads the earlier context.** Scenario D, asked right after Scenario C in one chat, showed joint account transactions as if they were Sarah's. In a new chat it refused correctly. No data leaked, because the tools cannot reach `A-2001`. The demo runs each scenario in a new chat.

**`orchestrate tools list` errors on a sample tool.** The instance ships a sample flow, `example_document_processing_flow`, that the CLI cannot parse. The error is unrelated to the banking tools, so `build_tools.sh` does not run the list command.

### Repository

**Environment file name.** The environment template is `env.sample`. The PRD originally named it `example.env` and now matches.