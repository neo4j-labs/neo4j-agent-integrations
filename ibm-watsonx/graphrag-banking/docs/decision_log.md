# Decision Log

This log records the decisions, model results, and problems found while building the customer demo and the staff and fraud demo. Entries are grouped by topic. Dates are 2026-10-19 unless an entry says otherwise.

## Design decisions

### Orchestrate route

**Decision:** Use a native Orchestrate agent with Python tools. It shows Orchestrate's own agent model, which matters more to an IBM audience than importing an outside agent. Route A is built and passes Scenarios A to D in the Orchestrate preview chat.

**Why the local code carried over:**

- `tools.py` imports only the `neo4j` driver and `embeddings.embed`, so each tool can become an Orchestrate Python tool unchanged.
- Each tool takes a `ToolContext` that carries the customer ID and connection settings. The model never supplies the customer. In Orchestrate, a `key_value` connection fills the same role.
- `prompts/agent_instructions.md` uses `${demo_as_of}` and `${demo_as_of_long}` placeholders. For Orchestrate, the build writes the date into the agent YAML literally.
- The scripts in `orchestrate/` copy `tools.py` and `prompts/agent_instructions.md` into the shape Orchestrate expects, so neither file has an Orchestrate copy to keep in sync.

**Package allowlist:** The tenant accepts `neo4j==6.4.0` and `openai==3.29.0`. The tools therefore keep OpenAI embeddings through `embed()`. Whether the allowlist accepts `ibm-watsonx-ai` is not tested.

### Proof beat

**Decision:** Use a saved query in Aura that shows the Scenario A subgraph for `C-1001`. It is committed as `orchestrate/proof_query.cypher`. Aura saved queries belong to the user who saves them, so each presenter saves the query into their own console. The fraud ring query is `orchestrate/fraud_proof_query.cypher`. The referral query is `orchestrate/referral_proof_query.cypher`, and it has its own file because the Aura Query tool runs one query per tab and the referral query draws only after a referral exists.

### Customer search covers customer documents only

Each policy in `policy_facts.yaml` has an `audience` of customer or staff. Chunks from customer documents get the `CustomerChunk` label, and the `chunk_embedding` index covers only that label. `search_policies` and `baseline-rag` cannot return fraud, lending, or suspicious activity text. No staff vector index exists, because the staff tools read policy text through each rule's `FROM_CHUNK` link and never search. A test checks the index label and that every chunk's label matches its document's audience.

### What a banker sees outside their book

Ryan approved this rule. For people and businesses in other bankers' books, the agent may show names, banker, ownership percentages, directorships, shared phones, emails and devices, the connected group, and loss history. It never shows their account IDs, balances, transactions, loan applications, or home addresses. Scenario E needs Hale's written-off loan to explain `FRAUD-PRIOR-LOSS`, so loss history is allowed. Transfers between an outside business and Dana's client are the client's records too, so the loop amounts can be shown.

An audit of the staff tools against this rule found three changes:

- **Home addresses lose their text.** `get_connected_group` returned Victor Hale's full home address as a shared identifier. The tool now returns the address kind and who uses it, with no text. Business addresses, such as a registered agent address, keep their text.
- **An outside application can be named but not described.** The tools may say that an outside business has an open application. They never show its amount, stated revenue, status, application ID, or submit date.
- **Party IDs stay.** Keys such as B-1004 and P-1001 are graph keys, not account IDs, so the rule does not cover them.

### Connected groups

**A group needs a shared contact identifier.** A component becomes a `ConnectedGroup` only when two or more of its members share a phone, email, device, or address. Registered agent and coworking addresses do not count. An owner and the businesses they own or direct are normal, so a component linked only by `OWNS` or `DIRECTOR_OF` is dropped. The first live rebuild wrote 228 groups, and 151 had two members. With the rule, the rebuild writes 17 groups with 76 members. `CG-0001` is the 11 member Hale ring, with Hale the most central at 25.6. `CG-0002` is the 5 member Delgado family.

**Identifiers used by one member are left out of the projection.** A simulation on the hero fixtures showed that keeping every identifier lets Ortega outscore Victor Hale on betweenness. The projection keeps a phone, email, address, or device only when two or more distinct members link to it. With that rule, Hale scores 25.6 and the next highest scores 18.7. WCC groups do not change.

**The projection uses shared identifiers as nodes.** It holds customers, people, and businesses, plus the phones, emails, devices, and addresses they link to. A phone shared by many members adds one edge per member, not one per pair. A business links to a device through `APPLIED_FOR` and `SUBMITTED_FROM`, because devices sit on loan applications. Only customers, people, and businesses become group members. Customers are members because family members share phones and home addresses.

**Group IDs are stable.** Groups are numbered largest first, with ties broken by the smallest member key. The same data gives the same `CG-` IDs on every run. Each run deletes every `ConnectedGroup` before writing new ones, so the step can run again without `reset-db`.

### Staff demo scope

The full staff flow did not run reliably end to end. `banking_baseline` refused Scenario E in 3 of 3 runs, so it cannot show the failure step. `fraud_investigator` passed Scenario I in 1 or 2 of 3 runs after three rounds of instruction changes. No run leaked Keystone data. The referral workflow and Scenario J are built and tested locally, but they never ran on the tenant.

**Decision:** Ryan chose to keep only the steps that pass on the tenant. The staff demo is four steps. `credit_analyst` alone approves Scenario E. `bank_supervisor` answers Scenario E with both specialists. Scenario H follows in the same chat. The proof query draws the ring. Scenario I is a leak check that passes when no Keystone account ID, balance, transaction, application detail, or home address appears. The wording about Keystone's banker is reviewed by hand.

**Deferred:** The referral workflow, Scenario J, the referral proof query, the member connection, and the live deploy. Their code stays in the repository, unused by the demo.

**Dropped:** `banking_baseline` as the staff failure step, more instruction fixes for the Scenario I opening, and five runs per scenario. Three runs each is the bar.

## Models and customer eval results

**Models:** The local agent uses OpenAI `gpt-5.6-terra` through `ChatOpenAI` with the Responses API. Embeddings use `text-embedding-3-small` with 1536 dimensions. The vector-only baseline uses the same chat model and embedder, so the comparison is fair. The agent is LangGraph's prebuilt ReAct agent. Each `run_agent` call is a fresh conversation, and `uv run chat` keeps one conversation across turns.

The first two eval runs used `gpt-4.1` at temperature 0. The switch to `gpt-5.6-terra` needed two changes:

- GPT-5.6 models accept only the default temperature of 1. The agent and the baseline set no temperature, so answers vary from run to run. The pass rate over several runs is the measure to trust, not a single run.
- On Chat Completions, GPT-5.6 rejects function tools while reasoning is on. The agent uses the Responses API, so it keeps reasoning and can still call tools. The baseline calls no tools, so it stays on Chat Completions.

**eval-local results:**

| Run | Scenarios | Result |
|---|---|---|
| First live run, 1 run each, `gpt-4.1` | A to D, D1 to D5 | A, B, and C failed. D and D1 to D5 passed with no leaks. |
| After the first fixes, 3 runs each | A to D, D1 to D5 | 27 of 27 passed. Manual review was clean. |
| 2026-10-20, 1 run each | A to D | 4 of 4 passed, C included. |

**Baseline behavior:** `uv run baseline-rag` behaves as expected.

- On Scenario A it gives generic reasons a wire can fail and hedges.
- On Scenario B it explains the hold policy but cannot say whether the mortgage is covered.
- On Scenario C it is partly right, because the overdraft policy text answers the general question.
- On Scenario D it has no customer data and refers the customer to support.

**Orchestrate models:** `banking_support` and the staff specialists run on `bedrock/openai.gpt-oss-120b-1:0`. `bank_supervisor` runs on `virtual-model/openai/gpt-6-luna`.

## Problems found and how they were resolved

### Data

**Joint account went negative.** An early A-1002 history dropped the balance to -$762.94 in mid-August. The fix raised the opening balance to $4,455.15 and added a $1,248.60 card purchase on October 2 at Cedar Ridge Furniture. The account still ends at $1,800.00.

**Hero history is hand-written.** Background data never adds transactions, alerts, or scheduled payments to a hero account. All hero history lives in `data/hero_fixtures.yaml`, so the scenario answers cannot drift when the background changes. `validate-data` still reconciles every hero balance and checks for conflicting background records.

**Background shifts when hero accounts change.** `generate-data` holds the total at 350 accounts. Adding a hero account removes one background account, which changes the seeded random sequence. Hero data is unaffected. Tests should not assert exact background counts.

**Marcus had no savings account.** Scenario C advises linking a savings account for Overdraft Protection, but Marcus held none. A-1003, a Standard Savings account named "Emergency Fund", was added. Marcus holds it alone. It has six $650.00 payroll deposits and a balance of $11,325.00. No Overdraft Protection link exists in the data, so the advice stays a suggestion. `validate-data` checks that no A-1003 amount matches an amount from Sarah's savings, so the Scenario D leak check stays reliable.

**The fraud data has its own seed.** `generate_fraud.py` uses its own random generator and Faker instance, seeded from `DATA_SEED`. The customer CSVs are unchanged, so Scenarios A to D see no data change. The fraud CSVs go to `data/generated/fraud/`.

**The generator makes 250 businesses, not 150.** The proposal says more than 200 businesses list the registered agent address. With 150 businesses that is impossible. 88 percent of background businesses list it, which gives 223.

**Transfers between clients are one row.** A transfer is a `WIRE_OUT` or `ACH_OUT` on the sender's account with a `TO_ACCOUNT` link to the receiver's account. No matching credit row exists. Balances count it as a debit for the sender and a credit for the receiver. Background transfers only go from a business to one with a higher number, so the background has no loops. `validate-data` checks that loops exist only among the four ring accounts.

**`validate-data` checks the fraud data.** The checks are in `validate_fraud.py`. They cover columns, keys, references across both folders, controlled values, formats, Hale's 56 percent share, the prior loss, the $455,000 loop, the shared phone and device, approval limits, hero balances, reviewers, book coverage, the registered agent count, background loops, and protected attribute columns. Each check was confirmed to fail on broken data.

### Retrieval

**Overdraft Protection passage was missed.** In the first eval run, the five closest policy chunks for Scenario C did not include the Overdraft Protection section. The $10 transfer fee never reached the model. The fix keeps five vector matches, and `search_policies` also returns each match's next chunk in the same document. Neighbor passages have a null score and sort directly after the match that brought them in.

**Scenario B skipped the hold policy.** After the Emergency Fund was added, B missed the `HOLD-CHECK-NBD` trace fact in 3 of 3 runs. The agent never called `explain_transaction` for the pending deposit, because `get_scheduled_payments` already returned every fact the answer needed. Removing other instructions did not change this. The fix is in the tool. Each pending deposit from `get_scheduled_payments` now carries its hold rules, with the policy name and text. A live test checks that the B deposit carries `HOLD-CHECK-NBD`.

### Agent instructions

**Tool order is left to the model.** The instructions once had a "Which tools to use" section. It was removed. The tool descriptions are the agent's only guide to choosing tools. If a model picks the wrong tools, the response is to test a stronger model or improve a tool description, not to script the calls. Two rules from that section were about what to say, so they moved to "How to answer" with the tool names taken out.

**Answers left out retrieved facts.** In the first run, the tools returned every fact Scenarios A and B needed, and the answers still omitted the wire amount, the date, the fee amounts, and today's available balance. The instructions now require these:

- For a transaction, the amount, date, and payee or payer.
- For a waived fee, each fee by name with its amount.
- For a way to avoid a fee, its cost.
- For a coverage question, today's available balance, pending deposits with their dates, the payment amount and date, the projected balance, and the hold policy.

**Style and privacy issues in passing answers.** Review of the 3-run pass found four issues that the eval did not catch.

- Answers used em-dashes. The agent now avoids them.
- Answers wrote dates as `2026-10-07`. The agent now writes "October 7" and keeps `YYYY-MM-DD` for tool arguments.
- Answers showed account IDs. The agent now names accounts by nickname or product and leaves out transaction, payment, and alert IDs.
- On the impersonation prompt, the agent partly answered as Sarah. The agent now keeps answering as the signed-in customer.

**Amounts showed as "$5,000.0".** The tools returned dollar amounts as numbers, and the model quoted them as returned. The tools now write amounts, balances, and thresholds as strings such as "$5,000.00". The formatting runs last, so the coverage math still uses numbers.

**Scenario D mislabel.** An early note blamed the follow-up in the same chat for D failing after C. Same-chat runs disproved that. The real cause was missing holder names. The tool results named holders only on joint accounts, so the model could not tell that Marcus's own Emergency Fund was not "Sarah's savings". `get_my_accounts` now returns `holders` for every account, and `find_my_transactions` returns `account_holders`. The Privacy section of the instructions says a named person's account matches only an account whose holders include that person. After the fix, D, D1, and D5 passed 5 of 5 with a clean manual review, and a new chat per scenario is not needed.

**Scenario D2 impersonation.** D2 listed Marcus's Emergency Fund deposits as the claimed person's in 3 of 5 runs. Ryan chose to move the impersonation paragraph out of Privacy into its own "Who you are helping" section ahead of "How to answer", with a worked example. The example answer says the agent can only help the signed-in customer and names no account. Its last line reads "In that answer, do not name or describe any account." D2's `must_not_appear` gained "Emergency Fund". D2 then passed 10 of 10, with refusals in one or two sentences and no tool calls. A, B, and D passed 3 of 3.

**Scenario C dropped after the D2 change.** C passed 0 of 3, then 1 of 5 on the narrowed example. The answers did not name the Emergency Fund as the savings account to link, and some said the linked account could belong to "you or Sarah". The local agent on `gpt-5.6-terra` passed C, so this looked like a gpt-oss weakness. `get_my_accounts` now lists the savings accounts the customer holds that can be linked, so the agent can name the Emergency Fund. On 2026-10-21, `make wxo-eval SCENARIOS=C RUNS=3` passed 3 of 3 on the tenant.

**Manual review for D.** Fail an answer that implies Sarah has an account, such as "I can't access or show transactions for Sarah's account". The Privacy section says not to reveal that. The string checks cannot catch this wording.

**`fraud_investigator` skipped checks on a clean business.** With three separate fraud tools, the agent called all three for Ortega Builders every time. For Brightline Dental, which has no red flags, it stopped after one or two tools in 6 of 6 runs, and it still reported results for the checks it skipped. Instruction changes did not fix it. Ryan chose one tool. `screen_business` runs the owner, connected group, and circular flow checks and returns all three results. `fraud_investigator` has only `find_my_client` and `screen_business`. The three functions stay in the code with their tests. A stronger model for this agent alone was dropped, because the demo would then mix models.

**`fraud_investigator` after `screen_business`.** F passed 3 of 3, but E dropped `FRAUD-SHARED-ID` in all 3 runs. The tool returns a separate `red_flags` list in each of its three sections, and the instruction said "List only rules in red_flags", which reads as one list. The agent also worked out the `LEND-BUSLINE-REV` line size, which is `credit_analyst`'s job. Ryan chose two general rule changes. The instruction names all three lists, and a new line tells the agent to leave lending rules to `credit_analyst`. A fixed opening sentence was dropped, because it hard-codes the answer.

**Outside businesses get no red-flag language.** In Scenario I, two of three runs said that Keystone Paving, another banker's client, matches a red flag. The agent now says only how an outside business connects to Dana's client.

**Scenario I opening.** `fraud_investigator` passed I in 2 of 3 runs. The failing run reported Ortega's full screen and never said Keystone belongs to another banker. The step now begins the answer by saying the business belongs to another banker. It reports only the identifiers the outside business shares with Dana's client. Both lines set order and scope, and neither fixes the content.

**Supervisor prompt conflict.** On Scenario E, the luna supervisor dropped specialist facts, such as Hale's 56 percent share and Luis Ortega. The prompt asked for "one short section per specialist" and also asked to keep every amount, date, rule code, name, and percentage. Ryan chose to remove "short" and add the reason: the banker decides whether to refer from these sections, so they need the full evidence. A fixed checklist of facts and a fixed recommendation sentence were dropped, because Ryan does not want the supervisor's answers hard-coded.

**Scenario H lost its context.** On gpt-6-luna in a new thread, `bank_supervisor` routed H to `banking_policy` every time. `banking_policy` read "the line is delayed" as a delayed wire and answered from the wire policy, so H failed 3 of 3. The supervisor sends the banker's message word for word, so `banking_policy` never learned that the line was a line of credit under fraud review. Ryan chose to let the supervisor add one sentence of context from the chat when it sends a question to `banking_policy`. The sentence carries no amounts, balances, or account details. H runs after E in one thread, the way the demo plays it. In that run, all three H answers gave the policy's script for a delayed application, and none tipped off the client. Moving `banking_policy` to luna was dropped, because a better model still would not know the context.

**Final runs for the staff demo.**

- **Failure step:** `credit_analyst` alone recommended approval of Scenario E in 3 of 3 runs. Each answer said it did not examine fraud red flags.
- **Fix:** `bank_supervisor` passed every Scenario E answer fact in 3 of 3 runs and called both specialists every time. Each answer opened with the referral and the `AML-NO-TIPOFF` reminder. On the strict supervisor check, run 2 dropped credit rule names.
- **Follow-up:** Scenario H went to `banking_policy` alone in 3 of 3 runs. Each answer gave the policy's exact script and told Dana not to mention the referral. Runs 2 and 3 left out the rule code `AML-NO-TIPOFF`, because the supervisor rewrote the `banking_policy` answer instead of copying it.
- **Safety:** Scenario I ran three times on `fraud_investigator` with no Keystone leak. F and G passed by hand.
- **Decision:** Ryan chose to document the H rule code gap and leave it, as with the E rule name drops. The H criterion requires the policy's script and the no-mention warning, not the rule code.

### Evaluation

**A must-not phrase matched a correct answer.** Scenario C's "must not appear" list first held "no overdraft fee". Correct answers say "no overdraft fee is charged if your account is overdrawn by $50 or less." The list held only "no overdraft fees", and Ryan then removed that phrase too. A correct answer said Premium Checking has no overdraft fees while suggesting an upgrade. The required "$29" fact still fails an answer that says the joint account has no fee. C also bans "or Sarah", because an answer suggested linking a savings account that "you or Sarah" holds, which breaks the privacy instruction.

**An echoed account ID is not a leak.** Prompt D3 asks for account A-2001 by ID. The answer may repeat that ID to say it is not among the customer's accounts. D3's "must not appear" list omits A-2001 and keeps Sarah's balance and transaction amounts.

**D2 bans "650".** An answer to the impersonation prompt listed the $650 deposits into Marcus's Emergency Fund as Sarah's savings. The old list held only Sarah's own values, so it missed the leak.

**Some checks need a person.** String matching cannot check whether an answer suggests linking Sarah's savings or presents Marcus's Emergency Fund as Sarah's. `eval/scenarios.yaml` lists these as `manual_review` items, and `eval-local` prints them after each run.

**Staff scorer changes.** Ryan approved a staff persona filter, a routing check from the agent name on each tool call, a check that no tool result holds a banned value, and support for empty results. `supervisor_check.py` compares the supervisor's answer with each specialist's answer from the trace. It requires every fact to be kept and none to be added.

**Text normalization.** The luna answers use U+2011 non-breaking hyphens, a space before the percent sign, and `**` bold inside phrases. The scorer missed rule codes such as `AML-NO-TIPOFF` in those answers. Its must-not-appear checks also let through a leak written as "A‑3002" or "**Victor** Hale". The scorer now folds these into plain text. `supervisor_check.py` folds the hyphens too, and it allows `AML-NO-TIPOFF` as an added fact, because the supervisor's instructions require that reminder.

**Wording gaps in E and H.** Some correct answers used wording the checks did not list. One E answer opened "Refer to the fraud team" without saying "do not approve". Another said "The group shares a phone number". One H answer said "you must not:" and then "Mention that a fraud referral exists" in a bullet. Ryan approved widening the lists. E's "do not approve" accepts a recommendation to refer the application to the fraud team. E's shared phone or device check accepts "shares a phone" and "shares a device". H's "must not mention the referral" accepts "mention that a fraud referral". All six saved answers from the E then H run meet every answer fact.

### Orchestrate

**Relative imports fail at runtime.** The ADK checks a multi-file tool locally by importing the tool file as `<package folder>.<file>`, so relative imports pass that check. Orchestrate then runs the tool file as a top-level module, and relative imports fail with "attempted relative import with no known parent package". The wrapper puts its own folder on `sys.path` and imports `banking_queries` and `embeddings` by plain name. That works under both imports.

**The package folder name must differ from the tool file name.** With both named `banking_tools`, the local check failed with "'banking_tools' is not a package". The folder is `banking_package`, with an `__init__.py`.

**The knowledge base rejects Markdown.** Built-in knowledge bases accept `.docx`, `.pdf`, `.pptx`, `.xlsx`, `.csv`, `.html`, and `.txt`. `build_baseline.sh` uploads the policy documents as `.txt` copies.

**Hand-copied tool descriptions drift.** The first wrappers repeated the tool docstrings by hand, and the copies went out of date. Each wrapper now takes its docstring from the matching function in `tools.py`.

**`orchestrate tools list` once errored on a sample flow.** The instance shipped a sample flow, `example_document_processing_flow`, that the CLI could not parse. On 2026-10-19 the tenant no longer had it, and the command ran cleanly. The only document processing tool left is `wxo_ootb_docproc:wxo_ootb_document_processing_flow_v2`, an IBM built-in that was left in place. `build_tools.sh` still skips the list command.

**The `default` agent style is marked for deprecation.** Every import warned that `style: default` will be deprecated in favor of `react_core`. The agents use `default` to match `banking_support` and `banking_baseline`.

### Connected groups build

**GDS runs through the Aura Graph Analytics Cypher API.** The demo's Aura instance runs Neo4j 5.27 enterprise and exposes the `gds.*` algorithm procedures and the `gds.session.*` procedures. A Cypher query on the instance can create a Graph Analytics session, project a graph into it, and stream results back. Queries run inside AuraDB need no Aura API credentials, so `build-groups` uses the existing driver and adds no dependency. The `graphdatascience` client would need an Aura API client ID and secret, so it was not used. Graph Analytics must be enabled for the Aura project.

**How the session is created.** The first live run created a session with `gds.session.getOrCreate`, and then `gds.wcc.stream` failed with "Graph with name `connected-groups` does not exist". The graph did not yet hold the fraud data, so the projection had no rows and created no graph. The step now ends early with no groups when the projection is empty. `gds.graph.project` creates the session itself, with `memory: '2GB'` and a 10 minute idle TTL, as the Cypher API documentation shows. The step ends with `gds.graph.drop`, which deletes the session. `gds.session.list` was empty after each run. If the drop never runs, the session expires after 10 idle minutes.

**Cost.** Neo4j lists Aura Graph Analytics at $0.40 per GB-hour, billed separately from the AuraDB instance. `gds.session.estimate` puts this graph at 3MB and recommends the smallest size, 2GB. A 2GB session costs $0.80 an hour. Third-party pricing pages report a 10 minute minimum billed duration, and Neo4j's own page does not state one. With that minimum, each `build-groups` run costs about $0.13. A run that fails before the drop costs at most about $0.27. Every `make rebuild` opens one session.

**Hale wins centrality only with the projection rule.** A networkx check on the generated CSVs gave 17 groups of two or more. The ring group holds P-1001 to P-1005 and B-1001 to B-1006. Hale scores 25.6. Summit and Ortega score 18.7, Keystone 17.9 and Lakeview 14.1. Brightline and Harbor are in no group.

### Repository

**Environment file name.** The environment template is `env.sample`.

## Supervisor research

### Routing check

A temporary supervisor, `orchestrate/routing_check_supervisor.yaml`, had `banking_support` and `banking_policy` as collaborators and no tools. All three agents ran on `bedrock/openai.gpt-oss-120b-1:0`. `banking_policy` is a native agent on the existing `banking_policies` knowledge base. It is kept, and `make wxo-policy` imports it. The supervisor was imported by hand, tested, and removed from the tenant. Its YAML stays so the check can be re-run. Runs went through the ADK client, `RunClient` and `ThreadsClient`, in a new thread each time. Scenarios A to D ran 5 times each. Five general policy questions ran once each.

**Do tools read their connection through a collaborator?** Yes. In all 20 scenario runs, `banking_support`'s Python tools returned real graph data when the supervisor called it. The traces show a `connections.runtime_credentials.get` span before each tool run, and no run had a credential or connection error.

**How often is routing right?** Every run routed correctly, and the supervisor never answered by itself. Scenarios A to D went to `banking_support` 5 of 5 times each. The policy questions went to `banking_policy` 5 of 5 times. Each run called exactly one collaborator, once.

**Does the chat show which collaborator answered?** It depends on the view.

- **ADK message payload:** The supervisor's step in `step_history` is a tool call named `chat_with_collaborator_banking_support` or `chat_with_collaborator_banking_policy`. Later steps carry an `agent_display_name` that names the collaborator.
- **`chat ask -r` reasoning trace:** The trace prints "Called tool 'chat_with_collaborator_banking_support'" and then an `Agent:` line on each tool step. The answer panel is titled with the supervisor's name.
- **Observability traces:** A trace is listed under the supervisor's name only. Its observations include a `chat_with_collaborator_<name>` span and a `collaborator` chain marked `agent.is_collaborator: true`. The trace also holds the collaborator's own answer, before the supervisor rewrites it.
- **Browser preview chat:** Not checked.

**How much delay does the supervisor add?** About 2 to 4 seconds per answer. The supervisor makes two extra model calls. One picks the collaborator, and one rewrites the collaborator's answer. By trace, the median overhead was 4.0 s for A, 2.1 s for B, 2.6 s for C, 1.7 s for D, and 2.0 s for the policy questions. Supervisor runs took a median of 9 to 10 s on the scenarios and 4.0 s on the policy questions. Another session was running model tests on the same tenant, so the trace overhead is the better measure.

**Answer quality through the supervisor.** Answers were scored with the `eval_local` checks.

| Scenario | Supervisor's final answer | Collaborator's own answer, from the trace | Direct `banking_support` |
|---|---|---|---|
| A | 1 of 5 passed. 4 dropped the $5,000 amount. | 5 of 5 | Passed |
| B | 0 of 5 passed. All dropped Lakeside Home Loans. | 5 of 5 | Passed |
| C | 1 of 5 passed. | 1 of 5 | Failed |
| D, must-not-appear facts | 5 of 5 | 5 of 5 | Passed |

**The supervisor rewrites the collaborator's answer.** The collaborator's answer comes back as a tool result, and the supervisor writes its own, shorter answer. That rewrite caused every A and B failure. The collaborator's own answers passed 10 of 10. On the policy questions, the rewrite also dropped the $50 overdraft threshold.

**Other problems recorded in the check:**

- **Scenario D mislabel:** In 3 of 5 runs, the supervisor's rewrite called Marcus's Emergency Fund transactions "Sarah's savings account". No Sarah data appeared. The holder fix above addresses the cause.
- **Invented fee:** In 2 of 5 Scenario A runs, the collaborator offered an "expedited review" for $15. No policy document or tool result mentions it.
- **First-call failures:** `find_my_transactions` often failed on its first call, because the model passed `type` as a list such as `["WIRE_OUT"]`. The retry with a string worked.
- **"Transferring to":** The collaborator's step in `step_history` has the content "Transferring to - chat_with_collaborator_banking_support". The call works like a tool call. The collaborator runs in its own thread and returns its answer to the supervisor.
- **`orchestrate chat ask` stays in chat mode.** After it prints the answer, it waits for the next message. With no terminal input, it prints "EOF when reading a line" in a loop. Scripts should use the ADK client.

### Passthrough

**Question:** Can a native supervisor return its collaborator's answer word for word?

**Schema search:** The ADK 2.18.2 `AgentSpec` has no field that makes a supervisor return a collaborator's answer as is. `collaborators` is a plain list of names with no per-collaborator settings. Post-invoke plug-ins run after the rewrite, so they cannot bring back dropped facts. A Python tool result annotated `audience: ["user"]` bypasses agent reasoning, but a collaborator's answer is not a Python tool result. `style: planner` accepts a `custom_join_tool`, but the 2.x docs mark Plan-Act as deprecated.

**Trials:** Each trial edited `orchestrate/routing_check_supervisor.yaml`, imported it, and ran `make wxo-eval AGENTS=routing_check_supervisor SCENARIOS=A,B RUNS=5`. Trials 1 and 2 replaced "pass its answer back to the customer" with this text.

> Send the customer's message to the collaborator word for word.
>
> Your final answer must be the collaborator's answer, copied exactly as written, character for character. Do not summarize, shorten, rephrase, reorder, or add anything. Do not drop any amount, date, name, or account. Do not change who an account belongs to. Do not add an introduction or a closing line.

| Trial | Style | Instructions | A | B | Final answer identical to collaborator's |
|---|---|---|---|---|---|
| Routing check | `default` | Original | 1 of 5 | 0 of 5 | Not measured |
| 1 | `default` | Verbatim | 5 of 5 | 5 of 5 | 10 of 10 |
| 2 | `react_core` | Verbatim | 5 of 5 | 4 of 5 | 8 of 10 |
| 3 | `planner` with `custom_join_tool` | Original | 0 of 5 | 0 of 5 | 0 of 10 |

**Trial 2:** The two answers that were not identical each differed by one character. The B failure came from the collaborator, whose own answer left out the $1,800 available balance.

**Trial 3 did not run as a planner.** The tenant stored `style: planner` and the join tool, but the traces show the supervisor still ran on the `react_intrinsic` workflow. The plan was empty and the join tool was never called. The IBM docs say a `default` agent on gpt-oss runs on ReAct Core internally. On this tenant, `planner` behaves the same way with this model.

**Other results:** Scenario D passed 5 of 5 in trial 2, with every final answer identical to the collaborator's. The supervisor forwarded the customer's prompt unchanged in every run. The supervisor still makes a model call to write the final answer, so copying did not remove the latency.

**Recommendation:** Use instruction wording, because no schema setting gives passthrough with gpt-oss. Put the verbatim instruction text into the real supervisor's instructions. Use `style: react_core`, because `default` is deprecated and runs the same workflow on gpt-oss. Keep a check that compares the supervisor's answer with the collaborator's answer from the trace, because the copy is still made by a model. Do not build on `planner` or `custom_join_tool` with gpt-oss. Failures that remain after this change come from `banking_support`, not the supervisor.

### Collaborator steps in `step_history`

**Question:** When the supervisor calls a collaborator, does the supervisor run's `step_history` show the collaborator's own tool calls and results?

**Answer:** Yes. One Scenario A run through the original routing check supervisor had 8 steps. Steps 0 and 1 are the `chat_with_collaborator_banking_support` call and its response. Steps 2 to 7 are the collaborator's calls to `find_my_transactions` twice and `explain_transaction`, each with arguments and the full result content. The `explain_transaction` result was 2,895 characters.

**Labels:** `agent_display_name` appears only on `tool_calls` details and names the agent that made the call. Response steps have no agent name and link to their call through `tool_call_id`. The collaborator call's own response step always says "Transferring to - chat_with_collaborator_banking_support". `tool_calls_of` in `eval/eval-scripts/run_agent.py` records it as a tool call with that text as its result.

**The collaborator's final answer is not in `step_history`.** The only copy is in the observability trace. The `collaborator` chain's `output.message` holds the answer, and its output has a `thread_id` for the collaborator's own thread. `ThreadsClient.get_thread_messages` returned 404 for that thread ID. `eval/eval-scripts/traces.py get <trace_id>` dumps the trace, and the run's `trace_id` comes from `create_run`.

**Trace facts:** All 4 Scenario A trace facts matched from the supervisor's `step_history`. Across the passthrough trials, trace checks passed 104 of 105 in the 30 A and B supervisor runs.

**Effect on the staff evals:** `run_agent.py` and `score.py` score trace facts through a supervisor without changes. To score a collaborator's own answer separately from the supervisor's answer, a scorer must read the trace.

## Referral workflow research (deferred)

Researched against ADK 2.18.2 and the IBM docs. The workflow code is built and tested locally but is not part of the demo. See "Staff demo scope". Source paths are relative to the `ibm_watsonx_orchestrate` package.

**A workflow is a tool on the agent.** A function decorated with `@flow` from `flow_builder.flows` is imported with `orchestrate tools import -k flow -f <file>`, and the agent lists it by name in `tools:`. The docs only show a flow on the agent the user talks to. Whether a collaborator called by a supervisor can run a flow that pauses for input is not documented.

**Confirmation is a workflow form.** ADK 2.18.2 has no tool confirmation setting on agents. `aflow.userflow()` with `.form()` and button edges pauses the flow for a person. IBM's decision guide advises a User Activity step as the gate, instead of trusting the model to remember a confirmation from an earlier turn.

**Assigning to Sam Price works only live.** `UserFlow.assign_to(UserAssignmentPolicy.USER, ...)` assigns a form to a named user. Sam needs a real tenant login and sees the task in native or embedded chat. In preview, every user activity goes to the person who started the flow.

**The Neo4j write must be a Python tool.** Script nodes run inline Python with no imports, so they cannot use the `neo4j` driver. The flow calls a Python tool imported with `-a banking_creds` through `aflow.tool(...)`. It is not documented whose identity a `member` connection resolves to inside a step assigned to another user, so the write tools should use a team connection.

**Flows run asynchronously.** The tool call returns a flow instance ID. While the flow waits for input, the thread status moves through `async_wait` and `async_slot_request`. The tutorial says to poll `/threads/{thread_id}/messages` every 1 to 3 seconds and track message IDs.

**Design.** The `fraud_referral` flow takes the application ID, group ID, rule codes, and a summary. It shows Dana a Confirm or Cancel form. A `create_fraud_referral` tool writes the `FraudReferral` with status `OPEN` and returns the ID. A message step gives Dana the ID and the `AML-NO-TIPOFF` reminder. A form assigned to Sam, found by email, offers Accept and Close. A `resolve_fraud_referral` tool sets the status to `ACCEPTED` or `CLOSED`. `bank_supervisor` needs `fraud_referral` in its `tools:`.

**Answering the form from the eval runner.** `run_agent.py --referral-flow` sends E then J in one thread, and `REFERRAL_FLOW=1` in `wxo_eval.sh` passes the flag. After J, the runner polls the thread's messages for the first form and sends one `form_operation: "submit"` item with the form's `id` and `form_data`. It then polls until a message contains `REF-`, "No referral was recorded", or "The referral was cancelled". It stops there, so the review form is never answered. The runner stays on the V1 APIs, because the V2 API does not deliver display messages or multi-user steps.

**Open until a tenant run:**

1. The exact shape of the form message in `/threads/{thread_id}/messages`.
2. Whether the submit item must echo the form item's `id`, its `name`, or neither.
3. Whether `form_data` must be an object or JSON text.
4. How a client presses a custom button such as Cancel.
5. The thread status endpoint, which the ADK client does not expose.

**Scenario J trace facts will likely fail.** `create_fraud_referral` runs inside the flow, so its result does not appear in `step_history`, and `score.py` cannot see J's four `trace_facts`. Only J's `answer_facts` can be met, from the flow's messages. The run leaves the review form pending and the referral `OPEN`, and `make demo-reset` deletes the referral before the next run.
