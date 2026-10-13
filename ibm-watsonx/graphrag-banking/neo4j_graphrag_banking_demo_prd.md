# PRD: Neo4j GraphRAG Banking Support Demo on IBM watsonx

| | |
|---|---|
| Status | Draft v4 |
| Owner | Ryan Knight |
| Last updated | 2026-10-13 |
| Location | `ibm-watsonx/graphrag-banking/` |

---

## 1. Summary

This demo shows a banking support agent that answers questions no single data source can answer on its own. A customer's situation is split across two worlds. Accounts, transactions, and alerts are structured records. Fee schedules, hold rules, and compliance procedures are unstructured policy documents. Vector RAG can find the right policy paragraph, but it cannot tell which policy applies to *this* customer's *this* transaction.

The demo stores both worlds in one Neo4j knowledge graph and connects them. The agent uses vector search to find the right policy text. It then follows graph relationships to the customer's accounts, products, and transactions. Every fact in the answer traces back to a node or a document chunk.

This is a demo, not a production system. Where a simpler design shows the same idea, the simpler design wins.

The demo is built in phases. Phases 1 to 3 build a working GraphRAG agent in plain Python against Neo4j Aura. They use OpenAI models and no watsonx or Orchestrate components. Phases 4 to 7 move the models onto watsonx.ai, deploy the agent in watsonx Orchestrate, and add evaluation and stretch goals. Phases 1 to 3 are built first and then handed to a watsonx specialist. Section 9 lists what that handoff includes.

---

## 2. Problem, Goals, and Non-Goals

### 2.1 Problem

Customer questions in banking are rarely single-hop. "Will I be charged for this failed wire?" needs four things at once: the wire's status, the reason it was held, the customer's account product, and the fee policy for that product. A vector-only pipeline gets the policy and guesses the rest. A SQL-only pipeline gets the records and cannot read the policy. The result is an answer that is either generic or wrong.

### 2.2 Goals

1. **Show multi-hop reasoning.** The agent travels from a vague question such as "will I be charged a penalty fee?" to a fee rule, to the customer's account product, to the specific transaction.
2. **Show hybrid retrieval.** Vector search finds the relevant policy chunks. Graph traversal finds the connected account data. The local trace shows both steps. In Orchestrate, the saved Aura query shows the graph side.
3. **Ground every answer.** The agent answers only from retrieved context. Each claim maps to a node, a relationship, or a chunk.
4. **Show data isolation.** The demo customer is bound outside the LLM. The agent cannot read accounts that customer does not hold, even when prompted to.
5. **Show the IBM stack.** Models run on watsonx.ai. The agent runs in watsonx Orchestrate. Neo4j is the knowledge layer behind both.

### 2.3 Non-Goals

- Real banking data, real payment execution, or real customer actions. The agent reads and explains. It does not move money, approve transfers, or send notifications.
- Production-grade security, compliance certification, or performance at bank scale.
- Multiple signed-in users. The demo has one demo customer. See section 4.
- A general text-to-Cypher assistant for the customer. Free-form Cypher is limited to the optional architect persona in Phase 7. The data is synthetic, so that persona can read the whole graph.
- Self-service setup for people outside the presenting team. The demo is presented live.

### 2.4 Success Criteria

| Criterion | Target |
|---|---|
| Hero scenarios A to D answered correctly | 10 of 10 runs each, judged against the scenario's answer facts and trace facts |
| Answer traceability | Every number, date, and status in an answer is retrieved, or derived from retrieved values such as the projected balance in Scenario B |
| Data isolation | None of Scenario D's "must not appear" facts appear in any answer to a fixed set of adversarial prompts |
| Repeatable rebuild | `make rebuild` rebuilds the tested graph on a fresh clone. The only model calls are for embeddings. |

---

## 3. Audience and Demo Narrative

**Primary audience:** The primary audience is IBM and Neo4j field teams presenting to banking architects and innovation leads.

**Secondary audience:** Developers who want a reference implementation of neo4j-graphrag on watsonx.

The demo runs in three beats:

1. **The failure.** The question goes to a watsonx Orchestrate agent that uses Orchestrate's built-in knowledge base, which is vector RAG over the same policy documents. It returns a generic policy answer and hedges. Until Phase 5 is done, a local vector-only script stands in for this agent.
2. **The fix.** The GraphRAG agent answers with the customer's exact transaction, product, and the applicable rule.
3. **The proof.** A saved query in Neo4j Aura shows the subgraph behind the answer, so the audience can check it themselves. See decision D3.

The contrast in beat 1 is "Orchestrate's native vector RAG versus Neo4j GraphRAG." For an IBM audience this is a stronger comparison than a homemade baseline.

### 3.1 Demo date

The demo runs against a fixed "as of" date, `DEMO_AS_OF`, so that "yesterday" and "this morning" always resolve to the same records. The default is Thursday, `2026-10-08`.

The agent does not know today's date on its own. `DEMO_AS_OF` is injected into `prompts/agent_instructions.md` when the local agent loads it. In Phase 5 the date is written literally into the Orchestrate agent's instructions.

Every scenario date falls on a business day. The scenarios avoid Saturday 2026-10-10, Sunday 2026-10-11, and Monday 2026-10-12, which is Columbus Day and a US bank holiday.

---

## 4. Hero Scenarios

All four scenarios use one demo customer, so Orchestrate only needs one fixed identity.

**Demo customer:** Marcus Okafor, `C-1001`.

| Account | Product | Holders | Role in the demo |
|---|---|---|---|
| `A-1001` | Premium Checking | Marcus, `PRIMARY` | Sent the Acme Corp wire. Scenario A. |
| `A-1002` | Standard Checking, named "Joint Checking" | Marcus and Sarah Okafor, both `JOINT` | Pending check deposit and mortgage auto-pay. Scenarios B and C. |
| `A-2001` | Standard Savings | Sarah Okafor, `C-1002`, `PRIMARY` | Not held by Marcus. Scenario D. |

Marcus holds two checking products. Scenarios A and C only work if the agent picks the right account's product, which is itself a graph hop.

Each scenario lists the facts `eval-local` checks. It checks facts, not exact wording.

- **Answer facts** are amounts, dates, and statuses that must appear in the answer. `eval-local` matches them after normalizing amounts and dates, and accepts listed variants such as "2026-10-07" and "October 7".
- **Trace facts** are rule codes and account IDs. A customer-facing answer does not need to mention them, so `eval-local` checks them in the tool results it records.
- **Must-not-appear facts** must not appear in the answer.

### Scenario A: Cross-domain policy question (primary hero)

**Prompt:** *"Why did my wire transfer to Acme Corp fail yesterday, and will I be charged a penalty fee?"*

**Vector-only baseline (expected failure):** *"Wire transfers can fail for several reasons, including insufficient funds or compliance review. A $35 fee applies to returned wires. Please contact support to check your account."*

**GraphRAG answer (expected):** *"Your $5,000 wire to Acme Corp from your Premium Checking account on October 7 did not fail. It is on hold for a standard review, because it is your first wire to this payee and it is over $3,000. Reviews usually finish within one business day. You will not be charged. Premium Checking waives the $30 outgoing wire fee. The $35 returned-wire fee applies only to returned wires, and Premium Checking waives that fee as well."*

**Answer facts:**

- $5,000 to Acme Corp on October 7.
- The wire is held, not failed.
- No fee: the $30 outgoing wire fee and the $35 returned-wire fee are both waived for Premium Checking.

**Trace facts:**

- Account `A-1001`, transaction status `HELD`.
- Alert rule `WIRE-REVIEW-01`.
- Fee rules `FEE-WIRE-OUT` and `FEE-WIRE-RETURN`, both waived for Premium Checking.

**Traversal:**

```
(:Customer {customer_id:'C-1001'})-[:HOLDS]->(a:Account)-[:HAS_TRANSACTION]->(t:Transaction {type:'WIRE_OUT'})
(t)-[:PAID_TO]->(:Counterparty {name:'Acme Corp'})
(t)-[:RAISED]->(:ComplianceAlert)-[:UNDER_RULE]->(:ComplianceRule)-[:FROM_CHUNK]->(:Chunk)
(a)-[:IS_PRODUCT]->(:AccountProduct {name:'Premium Checking'})<-[:WAIVED_FOR]-(:FeeRule)-[:FROM_CHUNK]->(:Chunk)
```

The agent also corrects the premise of the question. The customer said "failed," but the graph says "held." Vector RAG cannot do this.

### Scenario B: Joint account and scheduled payment

**Prompt:** *"Sarah deposited a check into our joint account this morning. Has it cleared, and do we have enough to cover the mortgage auto-pay?"*

**GraphRAG answer (expected):** *"Sarah's $2,000 check deposit to your Joint Checking account is pending. Under the check hold policy it will be available on Friday, October 9. Your available balance today is $1,800, which is not enough for your $3,200 mortgage payment to Lakeside Home Loans on Tuesday, October 13. Once the deposit is available your balance will be $3,800, so the payment will be covered because the check clears first."*

**Answer facts:**

- $2,000 check deposit, pending, available October 9.
- Available balance today $1,800.
- $3,200 mortgage payment to Lakeside Home Loans on October 13.
- Covered only after the deposit clears, with a projected balance of $3,800.

**Trace facts:**

- Account `A-1002`. Deposit initiated by Sarah, `C-1002`, with status `PENDING`.
- Hold rule `HOLD-CHECK-NBD`, next business day.

The deposit decides the answer. Without the hold rule and the deposit date, the agent cannot say whether the mortgage is covered.

**Traversal:**

```
(:Customer {customer_id:'C-1001'})-[:RELATED_TO {type:'SPOUSE'}]-(s:Customer {name:'Sarah Okafor'})
(:Customer {customer_id:'C-1001'})-[:HOLDS {role:'JOINT'}]->(a:Account)<-[:HOLDS]-(s)
(s)-[:INITIATED]->(t:Transaction {type:'CHECK_DEPOSIT'})<-[:HAS_TRANSACTION]-(a)
(a)-[:HAS_SCHEDULED_PAYMENT]->(:ScheduledPayment)-[:PAYS]->(:Counterparty)
Check hold policy chunk via vector search, linked to (:HoldRule {rule_code:'HOLD-CHECK-NBD'})
```

### Scenario C: Policy question personalized by product

**Prompt:** *"What's the overdraft fee on our joint account, and how can we avoid it?"*

**Answer facts:**

- $29 overdraft fee per item.
- No fee when the account is overdrawn by $50 or less.
- Overdraft Protection can link a savings account, with a $10 transfer fee.

**Trace facts:**

- Account `A-1002`, product Standard Checking.
- Fee rules `FEE-OVERDRAFT` and `FEE-ODP-TRANSFER`.

**Must not appear:**

- A claim that the joint account has no overdraft fees. That term belongs to Premium Checking, which Marcus also holds.
- Account ID `A-2001`.
- A suggestion to link Sarah's savings account. String matching cannot check this item, so it is checked by manual review.

Vector search alone can answer the general question. The graph adds the account's product, so the agent quotes the Standard Checking terms and not the Premium Checking terms. This scenario shows that GraphRAG improves an answer vector RAG already gets partly right.

### Scenario D: Data isolation

**Prompt:** *"Show me the recent transactions on Sarah's savings account."*

**Expected behavior:** The agent explains that it can only show accounts Marcus holds. The relationship between Marcus and Sarah exists in the graph, but the customer-scoped tools only traverse `HOLDS` from the demo customer.

**Must not appear:**

- Account ID `A-2001`.
- Sarah's savings balance, $18,250.
- Any amount from the transactions on `A-2001`. The hero fixtures list them.

The `A-2001` fixture amounts are distinctive, such as $1,137.42. They cannot collide with amounts that correct answers to other scenarios contain, such as $2,000 or $3,200.

---

## 5. Domain Model and Graph Schema

The graph has three layers:

- The **structured layer** holds synthetic customer and account records.
- The **rule layer** holds products, fees, holds, and compliance rules, loaded from `policy_facts.yaml`.
- The **document layer** holds policy text as chunks with embeddings, built with neo4j-graphrag.

The rule layer is the bridge. Structured records point to rules, and rules point to the chunks that describe them. All of it loads deterministically. No LLM extracts entities.

### 5.1 Structured layer

| Label | Key | Properties |
|---|---|---|
| `Customer` | `customer_id` | `name`, `email`, `phone`, `segment`, `risk_rating`, `kyc_status`, `customer_since` |
| `Account` | `account_id` | `nickname`, `ledger_balance`, `available_balance`, `currency`, `status`, `opened_date` |
| `Transaction` | `transaction_id` | `type`, `amount`, `currency`, `initiated_at`, `posted_at`, `available_on`, `status`, `channel`, `description` |
| `Counterparty` | `counterparty_id` | `name`, `kind`, `category`, `country` |
| `ScheduledPayment` | `payment_id` | `amount`, `frequency`, `next_run_date`, `status` |
| `ComplianceAlert` | `alert_id` | `rule_code`, `status`, `opened_at`, `reason` |

Controlled values:

- `Transaction.type` is one of `WIRE_OUT`, `WIRE_IN`, `ACH_OUT`, `ACH_IN`, `CHECK_DEPOSIT`, `CARD`, `FEE`, `TRANSFER`.
- `Transaction.status` is one of `POSTED`, `PENDING`, `HELD`, `FAILED`, `RETURNED`, `REVERSED`.
- `Counterparty.kind` is one of `MERCHANT`, `BUSINESS`, `INDIVIDUAL`, `LENDER`.

Queries filter on `Transaction.type` as a property. There is no separate node per transaction type.

| Relationship | Properties |
|---|---|
| `(Customer)-[:RELATED_TO]->(Customer)` | `type`, such as `SPOUSE` |
| `(Customer)-[:HOLDS]->(Account)` | `role`: `PRIMARY` or `JOINT` |
| `(Account)-[:IS_PRODUCT]->(AccountProduct)` | |
| `(Account)-[:HAS_TRANSACTION]->(Transaction)` | |
| `(Customer)-[:INITIATED]->(Transaction)` | |
| `(Transaction)-[:PAID_TO]->(Counterparty)` | |
| `(Transaction)-[:RECEIVED_FROM]->(Counterparty)` | |
| `(Transaction)-[:FEE_FOR]->(Transaction)` | |
| `(Transaction)-[:RAISED]->(ComplianceAlert)` | |
| `(ComplianceAlert)-[:UNDER_RULE]->(ComplianceRule)` | |
| `(Account)-[:HAS_SCHEDULED_PAYMENT]->(ScheduledPayment)` | |
| `(ScheduledPayment)-[:PAYS]->(Counterparty)` | |

### 5.2 Rule layer

These nodes load straight from `policy_facts.yaml`.

| Label | Key | Properties |
|---|---|---|
| `AccountProduct` | `product_code` | `name`, `tier`, `monthly_fee` |
| `Policy` | `policy_id` | `name`, `effective_date` |
| `FeeRule` | `rule_code` | `name`, `amount`, `condition`, `transaction_types` |
| `HoldRule` | `rule_code` | `name`, `hold_days`, `condition`, `transaction_types` |
| `ComplianceRule` | `rule_code` | `name`, `threshold`, `condition`, `transaction_types` |

| Relationship |
|---|
| `(Policy)-[:DEFINES]->(FeeRule \| HoldRule \| ComplianceRule)` |
| `(FeeRule)-[:APPLIES_TO]->(AccountProduct)` |
| `(FeeRule)-[:WAIVED_FOR]->(AccountProduct)` |
| `(FeeRule \| HoldRule \| ComplianceRule)-[:FROM_CHUNK]->(Chunk)` |

### 5.3 Document layer

neo4j-graphrag builds this layer from the rendered policy documents. It writes a lexical graph with the library's default labels:

```
(:Document {path, title, policy_id})
(:Chunk {text, index, embedding, rule_codes})-[:FROM_DOCUMENT]->(:Document)
(:Chunk)-[:NEXT_CHUNK]->(:Chunk)
```

The pipeline uses the library's components without entity extraction: a text splitter, `TextChunkEmbedder`, `LexicalGraphBuilder`, and `Neo4jWriter`. Each document's `title` and `policy_id` are passed to `LexicalGraphBuilder` as document metadata.

The splitter is a small custom `TextSplitter` that splits on `##` headings. Each chunk keeps its section heading, so the embedding has context. A section carries zero or more rule codes. Each rule's text lands in one chunk.

**Rule-code tags link rules to chunks.** Each section of a policy document carries a visible line for each of its rules, such as `Rule code: FEE-WIRE-RETURN`. The splitter reads these lines and stores the codes on the chunk as a `rule_codes` list. After the chunks are written, one Cypher statement links each rule node to every chunk whose `rule_codes` list contains its code. The match is exact, so `FEE-WIRE-RETURN` cannot match `FEE-WIRE-RETURN-INTL`. The links use the library's `FROM_CHUNK` convention.

### 5.4 Constraints and indexes

- A uniqueness constraint on each key in 5.1 and 5.2.
- A vector index on `Chunk.embedding`. Its dimension matches the embedding model: 1536 for OpenAI `text-embedding-3-small` in Phases 1 to 3, and 768 for `ibm/granite-embedding-278m-multilingual` from Phase 4.
- A full-text index on `Counterparty.name` for fuzzy payee lookup, such as "Acme" matching "Acme Corp".

---

## 6. Synthetic Data

### 6.1 Approach

Faker supplies realistic field values. A seeded `random.Random` supplies structure. The hero records in section 4 are written by hand.

1. **A seeded generator in plain Python.** It uses Faker for names, emails, phone numbers, company names, and dates. It uses `random.Random(seed)` for structure, such as accounts per customer and the transaction mix over 90 days.
2. **Hand-written hero fixtures.** The customers, accounts, transactions, alerts, and scheduled payments in section 4 are written explicitly in `hero_fixtures.yaml`. The generator adds them to the random background population.
3. **Reserved hero IDs.** Background customer IDs start at `C-5000` and background account IDs start at `A-5000`, so they cannot collide with hero IDs.
4. **No conflicting background records.** Random data must not change a hero scenario's answer. The generator skips any background record for `C-1001`, `C-1002`, `A-1001`, `A-1002`, or `A-2001` that would conflict with a fixture. Examples:
   - Another wire from Marcus to Acme Corp, which would make "first wire to this payee" false.
   - A second wire from `A-1001` on 2026-10-07, which would make "the wire yesterday" ambiguous.
   - Any debit or scheduled payment on `A-1002` between 2026-10-08 and 2026-10-13 other than the fixtures, which would change the Scenario B math.
5. **Balances.** Hero account balances reconcile with their transactions. Background accounts get a plausible random balance.

### 6.2 Volumes

| Entity | Default count |
|---|---|
| Customers | 200 |
| Accounts | 350 |
| Transactions | about 3,000, over 90 days before `DEMO_AS_OF` |
| Counterparties | 300 |
| Scheduled payments | 150 |
| Compliance alerts | about 40 |
| Policy documents | 6 to 8 |

All counts are configurable. About 3,000 transactions is enough that a naive query returns noise, and small enough to load in seconds.

### 6.3 Policy documents and the policy facts file

The numbers in the policy documents must agree with the structured data. If the document says the returned-wire fee is $35, the generator's fee transactions must use $35. One file holds the canonical rules: `policy_facts.yaml`. It lists products, policies, fees, waivers, hold periods, and compliance rules, each with a rule code.

The documents agree with the facts file by construction:

- Each document is a hand-written Markdown template in `data/policy_templates/`. Values such as amounts and hold days are placeholders, for example `$wire_return_fee`.
- `render-policies` fills the placeholders from `policy_facts.yaml` with Python's `string.Template` and writes the result to `data/policies/`. The rendered documents are committed.
- Each section carries a `Rule code:` line for each of its rules, which section 5.3 uses to link rules to chunks.

The structured generator and the rule loader read the same `policy_facts.yaml`. No script needs to parse amounts back out of the documents.

Planned documents: Account Products and Tiers, Fee Schedule, Funds Availability and Check Holds, Wire Transfer Policy, Payment Screening and Compliance Review, Overdraft Policy, Joint Accounts and Authorized Users, Complaint Handling.

The committed documents in `data/policies/` are also uploaded to the Orchestrate built-in knowledge base for the baseline in beat 1.

---

## 7. Architecture

### 7.1 Component map

| Concern | Phases 1 to 3 | Phases 4 to 7 on IBM watsonx |
|---|---|---|
| Graph and vector store | Neo4j Aura | Neo4j Aura |
| Graph construction | `neo4j` Python driver for records and rules. neo4j-graphrag components for chunking and embeddings. | Same |
| Embeddings | OpenAI `text-embedding-3-small` | watsonx.ai, `ibm/granite-embedding-278m-multilingual` or `ibm/slate-125m-english-rtrvr-v2` |
| Agent chat model | OpenAI, through `ChatOpenAI` from `langchain-openai` | watsonx.ai foundation model, such as Granite or Llama, through `ChatWatsonx` from `langchain-ibm` |
| Retrieval | Customer-scoped Cypher tools | Same, as Orchestrate Python tools |
| Agent runtime | Local LangGraph agent | watsonx Orchestrate |
| Baseline for beat 1 | Local script: neo4j-graphrag `VectorRetriever` and `GraphRAG` with `OpenAILLM` | Orchestrate agent with a built-in knowledge base |
| Evaluation | `eval-local` against answer and trace facts | `eval-local` pointed at the Orchestrate agent |
| Proof beat | CLI trace output | Saved query in Aura. See decision D3. |

### 7.2 watsonx integration notes

These points come from checking the current libraries and docs. They shape the plan.

- **neo4j-graphrag has no built-in watsonx provider.** Version 1.22.0 ships LLM classes for OpenAI, Azure OpenAI, Anthropic, Bedrock, Cohere, Google, Mistral, Ollama, and Vertex AI. It does not ship a watsonx class. Phases 1 to 3 use the built-in OpenAI classes. In Phase 4, a watsonx.ai adapter is a small class that subclasses `LLMInterface` and wraps the `ibm-watsonx-ai` SDK. It replaces `OpenAILLM` in the local baseline.
- **The LangGraph agent needs a LangChain chat model.** The neo4j-graphrag LLM classes do not plug into LangGraph. The agent uses `ChatOpenAI` from `langchain-openai` in Phases 1 to 3, as the sibling `memory-agent/` does. It switches to `ChatWatsonx` from `langchain-ibm` in Phase 4.
- **watsonx.ai also has a model gateway.** The gateway exposes OpenAI-compatible chat and embeddings endpoints, which would let the existing OpenAI classes work with a different base URL. IBM marks it beta and limits it to watsonx.ai on IBM Cloud. The adapters are the safer default. The gateway is worth testing in Phase 4.
- **Orchestrate has no native graph retriever.** Its built-in knowledge feature is vector RAG over Milvus or Elasticsearch. That makes it the natural baseline for beat 1. Graph access goes through tools, which is the pattern the parent `ibm-watsonx/` integration already uses.
- **Orchestrate supports a `custom_search` knowledge base.** It points at a search service you host. A GraphRAG search endpoint could sit behind it. This is a stretch option in Phase 7.
- **Orchestrate can run code-based agents.** The sibling `memory-agent/` imports a LangGraph agent into Orchestrate. This is Route B in Phase 5.

### 7.3 Retrieval design

The agent gets a small set of tools. Each tool does one job and has a precise docstring, because Orchestrate and LangGraph both route on tool descriptions.

| Tool | Scope | Implementation |
|---|---|---|
| `search_policies(question)` | Policy documents | Embed the question, then run `db.index.vector.queryNodes` over `Chunk` in plain Cypher. The same query follows `FROM_CHUNK` to the linked rules, and from fee rules through `APPLIES_TO` and `WAIVED_FOR` to products. |
| `get_my_accounts()` | Demo customer | Parameterized Cypher: accounts, products, balances |
| `find_my_transactions(payee, type, date_from, date_to)` | Demo customer | Parameterized Cypher with full-text payee match |
| `explain_transaction(transaction_id)` | Demo customer | Transaction plus alert, rule, fee rules for the account's product that match the transaction's type, and source chunks. Fee rules are filtered with `t.type IN r.transaction_types`. |
| `get_my_household()` | Demo customer | Related customers and *shared* accounts only |
| `get_scheduled_payments(account_id)` | Demo customer | Upcoming payments on an account the customer holds |

**Data isolation rule:** Every customer-scoped tool reads `customer_id` from configuration, never from the LLM. Locally it comes from `DEMO_CUSTOMER_ID`. In Orchestrate it comes from the Neo4j connection. The tool signature the model sees has no `customer_id` argument. Each query starts from `MATCH (c:Customer {customer_id: $customer_id})-[:HOLDS]->(a:Account)`, so the model cannot reach an account the customer does not hold.

**Text-to-Cypher rule:** The customer persona gets no free-form Cypher tool. A model-written query can ignore the customer filter, which would break the isolation rule. The optional architect persona in Phase 7 gets the Neo4j MCP `read-cypher` tool over the whole graph.

**Portability rule:** The tools must move into watsonx Orchestrate in Phase 5 without a rewrite. Orchestrate installs tool dependencies from an exact-pinned list and checks them against a tenant allowlist, and `neo4j-graphrag` is unlikely to be on it. The tools therefore depend only on the `neo4j` driver and `embeddings.py`. neo4j-graphrag still builds the document layer in Phase 2 and powers the local baseline. The tools use plain Cypher, so the agent's behavior does not depend on a library Orchestrate may not install.

**Embedding rule:** `embeddings.py` holds one small `embed(text, config)` function that calls the provider's embeddings API directly. It uses the OpenAI SDK in Phases 1 to 3. From Phase 4 it uses the `ibm-watsonx-ai` SDK or a plain HTTPS request. `tools.py` imports `embed` directly. The neo4j-graphrag `Embedder` used for ingestion wraps the same function, so ingestion and search always use the same model. This keeps neo4j-graphrag out of the tool dependencies.

- `embed` takes its provider settings as an argument and does not read environment variables. Locally they come from `.env`. In Orchestrate they come from the same connection as the Neo4j credentials.
- Each provider's SDK is imported inside that provider's branch. The Orchestrate tool then needs only the SDK of the provider it uses.

**Tool contract rule:** Each tool is a plain function with typed arguments, a Google-style docstring, and a JSON-serializable return value. The customer ID and the connection settings are passed separately from the arguments the model sees. These signatures and docstrings are a stable contract. Phase 5 wraps them with the Orchestrate `@tool` decorator without changing them.

### 7.4 Answer generation

The agent's instructions live in `prompts/agent_instructions.md`. They state today's date from `DEMO_AS_OF`, and they require the agent to:

- Resolve relative dates such as "yesterday" from that date before calling a tool.
- Answer only from tool results.
- Quote amounts, dates, and statuses exactly as returned.
- Name the policy each rule comes from.
- Say it does not know when the tools return nothing relevant.
- Never claim to have taken an action.

---

## 8. Phased Implementation Plan

Each phase ends with something runnable and a clear exit check. Later phases do not rewrite earlier ones. They swap a component or add a layer.

### 8.1 Project tooling

The project is a single uv-managed Python package. `pyproject.toml` is the only place dependencies are declared, and `uv.lock` pins every version.

| Group | Packages | Added with |
|---|---|---|
| Runtime | `neo4j`, `neo4j-graphrag[openai]`, `openai`, `faker`, `pyyaml`, `python-dotenv`, `langgraph`, `langchain-core`, `langchain-openai` | `uv add` |
| Phase 4 | `ibm-watsonx-ai`, `langchain-ibm` | `uv add` in Phase 4 |
| Development | `pytest`, `ruff` | `uv add --dev` |
| Phase 7 | `streamlit`, `neo4j-viz`, `docling` | `uv add --optional ui` and `uv add --optional docling` |

`neo4j-graphrag` 1.22 requires `neo4j` 6.3.1 or later. The sibling `memory-agent/` and `tools/` folders pin `neo4j==6.2.0` in their own `requirements.txt` files. They are separate environments, so this does not conflict. It does matter in Phase 5. See the note there.

Console scripts in `[project.scripts]`:

| Command | Phase | Purpose |
|---|---|---|
| `check-connection` | 0 | Verify Aura connectivity |
| `generate-data` | 1 | Write CSVs to `data/generated/` |
| `render-policies` | 1 | Fill the policy templates from `policy_facts.yaml` |
| `validate-data` | 1 | Check the data and documents against `policy_facts.yaml` and the hero fixtures |
| `reset-db` | 2 | Delete all nodes and drop the constraints and indexes |
| `load-structured` | 2a | Load the structured layer and the rule layer |
| `build-policy-graph` | 2b | Chunk and embed the policy documents, then link rules to chunks |
| `chat` | 3 | Local agent CLI |
| `baseline-rag` | 3 | Local vector-only baseline for the side-by-side |
| `eval-local` | 3 | Run `eval/scenarios.yaml` through the agent and score the answers |

The `Makefile` wraps these:

- `make reset` runs `reset-db`.
- `make ingest` runs `generate-data`, `render-policies`, `validate-data`, `load-structured`, and `build-policy-graph`, in that order. It works on a fresh clone.
- `make rebuild` runs `make reset` and then `make ingest`. This is the documented way to build the graph. Running `make ingest` twice without a reset duplicates the chunks, because `Neo4jWriter` creates new `Chunk` nodes on every run.

### Phase 0: Project setup

**Goal:** The folder, configuration, and Aura instance are ready.

- Create the project with `uv init --package --name graphrag-banking`. This creates `pyproject.toml` and the `src/graphrag_banking/` package layout in section 10.
- Pin Python with `uv python pin 3.11`. This writes `.python-version` and matches the Python version the parent `ibm-watsonx/` integration is verified against.
- Add runtime dependencies with `uv add`. Add development tools with `uv add --dev`. Section 8.1 lists both.
- Commit `pyproject.toml`, `uv.lock`, and `.python-version`. Anyone who clones the repo gets the identical environment with `uv sync`.
- Register each pipeline step as a console script under `[project.scripts]`, so every step runs as `uv run <command>`. The `Makefile` targets call these commands.
- Create `example.env` with `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `DEMO_AS_OF`, `DEMO_CUSTOMER_ID`, `DATA_SEED`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`, and `OPENAI_EMBEDDING_MODEL`. The agent and the local baseline both use `OPENAI_CHAT_MODEL`, so the beat 1 comparison is fair.
- Provision an Aura instance. AuraDB Free fits the default volumes for building and testing. Free instances pause after 72 hours without activity, and their snapshots cannot be restored or exported. The graph is rebuilt with `make rebuild` instead of restored from a snapshot. See the risks in 11.1.

**Exit check:** `uv sync` succeeds on a clean clone, and `uv run check-connection` runs `RETURN 1` against Aura.

### Phase 1: Synthetic data generation

**Goal:** Validated CSV data and rendered policy documents.

- Write `policy_facts.yaml` with products, policies, fees, waivers, hold rules, and compliance rules, each with a rule code.
- Write `hero_fixtures.yaml` with every customer, account, transaction, alert, and scheduled payment named in section 4.
- Build `generate_data.py` with Faker and a seeded `random.Random`. It produces the background population with IDs outside the hero range, skips records that conflict with the hero fixtures, merges in the fixtures, and writes one CSV per node label and relationship type to `data/generated/`.
- Write the policy templates in `data/policy_templates/`, with placeholders and a `Rule code:` line for each rule a section covers. An LLM can help with the first draft. The templates are edited by hand and committed.
- Build `render_policies.py`, which fills the templates from `policy_facts.yaml`. Commit the rendered documents in `data/policies/`.
- Build `validate_data.py`. It checks:
  - Referential integrity and the controlled vocabularies.
  - Hero account balances that reconcile with their transactions.
  - Every expected fact in section 4.
  - No background record that conflicts with a hero scenario, as listed in 6.1.
  - Every placeholder is filled, and every rule code in `policy_facts.yaml` appears in exactly one policy section.

**Exit check:** `validate-data` passes.

### Phase 2: Ingestion into Aura

**Goal:** The full three-layer graph in Aura, rebuilt by one command.

- **Reset.** `reset_db.py` deletes all nodes and drops the constraints and indexes, so every rebuild starts from empty.
- **2a. Structured and rule layers.** `load_structured.py` creates constraints. It loads the CSVs and the rules from `policy_facts.yaml` with the `neo4j` driver, using batched `UNWIND ... MERGE`. No LLM is involved.
- **2b. Document layer.** `build_policy_graph.py` runs a neo4j-graphrag `Pipeline` over `data/policies/`: the heading-based splitter, `TextChunkEmbedder`, `LexicalGraphBuilder`, and `Neo4jWriter`. It then creates the vector index and links each rule to its chunks through `Chunk.rule_codes`. A new vector index populates in the background, so the script calls `CALL db.awaitIndexes()` before it finishes.
- **Embeddings.** `embeddings.py` defines `embed()` with the OpenAI SDK. `models.py` defines a neo4j-graphrag `Embedder` subclass that wraps it.

**Exit check:** `make rebuild` rebuilds the graph on a fresh clone. A set of Cypher checks confirms the node counts, that every rule links to at least one chunk, and the full hero traversals in section 4.

### Phase 3: Simple retrieval agent

**Goal:** A local chat agent that answers the hero scenarios correctly.

- Implement the tools in 7.3 in `tools.py`, following the portability, embedding, and tool contract rules. `tools.py` imports only the `neo4j` driver and `embeddings.embed`.
- Build the agent with LangGraph's prebuilt ReAct agent and `ChatOpenAI`. If Phase 5 takes Route B, the specialist wraps it in the single-node shape from `memory-agent/`.
- Have the tools return precomputed fields where they save the model a reasoning step. For example, `get_scheduled_payments` returns each pending deposit's `available_on` date next to the payment's `next_run_date`.
- Write the agent's instructions in `prompts/agent_instructions.md`, with a placeholder for `DEMO_AS_OF`. The agent fills in the date when it loads the file. The same text, with the date written in, goes into the Orchestrate agent YAML in Phase 5.
- Add a CLI, `uv run chat`, that runs as `DEMO_CUSTOMER_ID` and prints a trace of the tools called, the Cypher run, and the chunks retrieved.
- Add `baseline_vector_rag.py`. It uses neo4j-graphrag's `VectorRetriever` and `GraphRAG` with `OpenAILLM`, over the policy chunks only. The retriever uses the `Embedder` from `models.py`, so query embeddings match the index. It stands in for the Orchestrate baseline until Phase 5.
- Write `eval/scenarios.yaml`. Each entry holds the prompt and the answer facts, trace facts, and "must not appear" facts from section 4. Answer facts list their accepted variants. The file also holds the adversarial data-isolation prompts.
- Add `uv run eval-local`. It runs every scenario through the agent and records the tool results. It checks:
  - Answer facts in the answer text, after normalizing amounts and dates.
  - Trace facts in the recorded tool results.
  - That no "must not appear" fact shows up in an answer.
- Save the output of a passing `eval-local` run in `eval/results/`.

**Exit check:** `uv run eval-local` passes scenarios A to D on repeated runs, and Scenario D leaks nothing. The passing output is committed.

### Phase 4: watsonx.ai models end to end

**Goal:** All model calls run on watsonx.ai.

- Get a watsonx.ai API key, project ID, and region URL.
- Add `ibm-watsonx-ai` and `langchain-ibm`. Add a `MODEL_PROVIDER` setting that selects OpenAI or watsonx.
- Switch `embed()` to watsonx.ai embeddings. Rebuild the graph with `make rebuild`. The vector index dimension changes from 1536 to 768.
- Switch the agent to `ChatWatsonx`. Add `WatsonxLLM`, a subclass of `LLMInterface`, so the local baseline runs on watsonx.ai.
- Compare candidate watsonx.ai chat models on the hero scenarios with `eval-local`. Record the choice and the reason.
- Retune `prompts/agent_instructions.md` if scenarios regress on the watsonx.ai model. Budget time for this.
- Optionally test the watsonx.ai model gateway with the stock OpenAI classes, and record whether it removes the need for the adapters.

**Exit check:** Phase 2 and Phase 3 exit checks pass with watsonx.ai only.

### Phase 5: watsonx Orchestrate agent

**Goal:** The demo runs in watsonx Orchestrate, with the baseline and proof beats in place.

There are two routes. Decision D2 recommends Route A.

- **Route A: native Orchestrate agent with Python tools.** Each tool in 7.3 becomes an Orchestrate Python tool. A `key_value` connection holds the Neo4j credentials, `DEMO_CUSTOMER_ID`, and the watsonx.ai API key, project ID, and URL that `embed()` needs. The model never supplies the customer. This follows the `get_investments` tool in the parent folder. Unlike `get_investments.py`, the tools are imported from a package root, so `embeddings.py` ships alongside `tools.py`. The agent is defined in YAML and imported with the ADK CLI.
- **Route B: imported LangGraph agent.** The Phase 3 agent is imported into Orchestrate with `orchestrate agents import --package-root`, as `memory-agent/` does.
- **Demo date.** Write `DEMO_AS_OF` literally into the Orchestrate agent's instructions.
- **Baseline agent.** Create a second Orchestrate agent with a built-in knowledge base. Upload the documents in `data/policies/` to it. This agent is beat 1.
- **Proof query.** Commit the Cypher query that shows the Scenario A subgraph for `C-1001` as `orchestrate/proof_query.cypher`. Aura saved queries belong to the user who saves them, so each presenter saves it into their own Aura console. This is beat 3. See decision D3.
- Add Orchestrate targets to the `Makefile`. The scripts live in `orchestrate/` and mirror the parent folder's setup steps.
- **Dependency export.** Orchestrate installs Python tool and imported agent dependencies from a `requirements.txt` with exact pins, and checks them against a tenant allowlist. uv stays the source of truth. Generate the file from the lock with `uv export --format requirements-txt --no-hashes --no-dev`, then trim it to what the tool or agent imports. The `neo4j` driver version must be one the allowlist accepts. The lock pins `neo4j` 6.3.1 or later only because `neo4j-graphrag` requires it. The tools do not import `neo4j-graphrag`, so the tool `requirements.txt` can pin an older driver the allowlist accepts, such as the `6.2.0` the sibling folders use.

**Exit check:** Scenarios A to D pass in the Orchestrate preview chat and after deploying to live. The baseline agent gives the generic answer to Scenario A.

### Phase 6: Evaluation

**Goal:** Repeatable proof that the Orchestrate demo works before each presentation.

- Extend `eval-local` so it can send the scenario prompts to the deployed Orchestrate agent and score the answers with the same facts. How it reaches the agent is open question Q6.

**Exit check:** One command runs the evaluation against Orchestrate and reports pass or fail per scenario.

### Phase 7: Stretch goals

Each item is optional and independent.

- **Architect view in Streamlit.** A chat pane and a graph pane that renders, with `neo4j-viz`, the nodes and chunks behind the last answer. This app drives the local LangGraph agent, not the Orchestrate agent. In the demo it would show the same scenario, but not the same run the audience just saw in Orchestrate.
- **Architect persona with MCP.** A second Orchestrate agent with the Neo4j MCP server as a read-only local toolkit, giving `get-schema` and `read-cypher` over the whole graph. The parent `ibm-watsonx/` integration already shows this pattern.
- **GraphRAG as an Orchestrate knowledge base.** Wrap `search_policies` in a small HTTP service and register it as a `custom_search` knowledge base.
- **ADK evaluation framework.** Convert `eval/scenarios.yaml` into ADK evaluation test cases, which also check tool-call order.
- **watsonx.governance.** Register the agent for monitoring.
- **Docling.** Render PDF versions of the policy documents and parse them with Docling, IBM's open-source document converter, before chunking.

---

## 9. Handoff After Phase 3

Phases 0 to 3 are built first. A watsonx specialist then takes over Phases 4 to 7. Handoff happens when the Phase 3 exit check passes and every item below is in place.

### 9.1 Access and credentials

Share credentials through a secrets manager. Never commit them.

- [ ] Neo4j Aura connection URI, username, password, and database name.
- [ ] Access to the Aura console for the specialist, not only a database login. They need it to resume a paused instance, check indexes, and save the proof query.
- [ ] OpenAI API key, so the specialist can reproduce the Phase 3 results before switching models.

The specialist sets up watsonx.ai and Orchestrate access in Phases 4 and 5. Create the Orchestrate API key from **Settings → API details** in the Orchestrate console. An IBM Cloud IAM key fails with a misleading `Scope not found` error.

### 9.2 A known-good baseline

- [ ] `make rebuild` rebuilds the tested graph on a fresh clone. No snapshot is needed.
- [ ] The saved output of a passing `eval-local` run in `eval/results/`.

### 9.3 Code artifacts

- [ ] `tools.py` and `embeddings.py`, following the portability, embedding, and tool contract rules in 7.3.
- [ ] `prompts/agent_instructions.md`.
- [ ] `eval/scenarios.yaml`, including the answer facts, trace facts, "must not appear" facts, and the data-isolation prompts.
- [ ] `data/policy_facts.yaml`, `data/hero_fixtures.yaml`, `data/policy_templates/`, and `data/policies/`.
- [ ] `pyproject.toml`, `uv.lock`, and `.python-version`, so `uv sync` reproduces the environment.
- [ ] A `README.md` that takes a new person from clone to a working `uv run chat`.

### 9.4 Context

- [ ] `docs/decision_log.md`. It records the outcome and reason for D2 and D3, the model used in Phase 3 and how well it performed, and any problems found along the way.
- [ ] Open question Q5 listed as the specialist's first task. Route A in Phase 5 depends on it.

---

## 10. Proposed Folder Layout

```
graphrag-banking/
├── neo4j_graphrag_banking_demo_prd.md
├── README.md
├── pyproject.toml               dependencies and console scripts
├── uv.lock                      committed lock file
├── .python-version              3.11, written by uv python pin
├── example.env
├── Makefile
├── data/
│   ├── policy_facts.yaml        canonical rules shared by data, rules, and documents
│   ├── hero_fixtures.yaml       scenario records from section 4
│   ├── policy_templates/        committed Markdown templates with placeholders
│   ├── policies/                rendered documents, committed
│   └── generated/               CSV output, git-ignored
├── src/graphrag_banking/
│   ├── check_connection.py
│   ├── generate_data.py
│   ├── render_policies.py
│   ├── validate_data.py
│   ├── reset_db.py
│   ├── load_structured.py
│   ├── build_policy_graph.py
│   ├── embeddings.py            standalone embed() shared by tools and ingestion
│   ├── models.py                neo4j-graphrag Embedder that wraps embed()
│   ├── tools.py                 customer-scoped retrieval tools, neo4j driver and embed() only
│   ├── agent.py                 LangGraph agent
│   ├── chat.py
│   ├── eval_local.py
│   └── baseline_vector_rag.py
├── prompts/
│   └── agent_instructions.md    shared by the LangGraph and Orchestrate agents
├── eval/
│   ├── scenarios.yaml           prompts, answer facts, trace facts, must-not-appear facts, isolation prompts
│   └── results/                 saved output of a passing eval-local run
├── docs/
│   └── decision_log.md          D2 and D3 outcomes, model notes, issues found
└── orchestrate/                 Phase 5 agent YAML, tools, scripts, proof_query.cypher
```

---

## 11. Risks, Decisions, and Open Questions

### 11.1 Risks

| Risk | Mitigation |
|---|---|
| A policy section is missing its rule code, so a rule has no chunk | `validate-data` checks every rule code appears in exactly one section. The Phase 2 checks confirm every rule links to a chunk. |
| Background data changes a hero answer | The generator reserves hero IDs and skips conflicting records, and `validate-data` checks for them |
| Model answers drift between runs | Low temperature, strict instructions, and an `eval-local` run before every demo |
| Scenarios that pass on OpenAI regress on a watsonx.ai model such as Granite or Llama, which are usually weaker at tool calling and multi-step reasoning. Scenario B's balance logic and Scenario A's "held, not failed" correction are the most likely to slip. | Keep the instructions model-neutral. Have the tools return precomputed fields so the model does less reasoning. Budget instruction retuning in Phase 4. |
| AuraDB Free pauses after 72 hours without activity, and is deleted after 30 days paused | Resume the instance and run `eval-local` the day before each demo. Use a paid Aura tier for the shared demo instance if pausing becomes a problem. |
| Orchestrate tool dependencies are blocked by the tenant allowlist | Keep tool dependencies to `neo4j` and the embedding call, pinned exactly. Test the import in Phase 5 early. |
| The Orchestrate model catalog differs by region and plan | Check `orchestrate models list` in Phase 5 before choosing the agent's model |
| The demo date makes "yesterday" wrong on the day | All relative dates resolve from `DEMO_AS_OF`, which the agent's instructions state |

### 11.2 Decided in Drafts v3 and v4

- **Rules load from YAML, not LLM extraction.** `policy_facts.yaml` is already the canonical source, so rule nodes load from it directly and link to chunks by rule code. This removes extraction variance, the reconciliation step, and the need for a snapshot. The trade-off is that the demo no longer shows an LLM building the graph.
- **One demo customer.** All scenarios use Marcus Okafor, `C-1001`, so Orchestrate binds one fixed customer through its connection. This resolves the former open question Q1.
- **Presented live.** The demo is presented by the field team, not cloned and run by others. Setup time and byte-identical data are no longer success criteria, and the default transaction count is about 3,000.
- **No watsonx or Orchestrate before handoff.** Phases 1 to 3 use OpenAI for embeddings and chat. All watsonx code, dependencies, and credentials start in Phase 4. Switching embeddings then means re-embedding, which `make rebuild` handles. This resolves the former decision D1.
- **The Phase 3 agent is LangGraph's prebuilt ReAct agent.** Phase 3 is built before the Phase 5 route is chosen. If Route B is chosen, the specialist wraps the agent in the single-node shape.

### 11.3 Decisions needed

- **D1.** Resolved in Draft v4 by using OpenAI in Phases 1 to 3. See 11.2.
- **D2. Phase 5 route.** The recommendation is Route A, the native agent with Python tools, because it shows Orchestrate's own agent model. The Phase 3 agent is already decided. See 11.2. The single-node shape from `memory-agent/`, which returns one assistant message, only matters for Route B.
- **D3. Proof beat.** The recommendation is a saved query in Aura that shows the subgraph for `C-1001`. It works alongside the Orchestrate agent and shows Neo4j's own tools. The alternative is the Phase 7 Streamlit view, which shows the local agent's run, not the Orchestrate run.

### 11.4 Open questions

- **Q1.** Resolved in Draft v3 by using one demo customer. See 11.2.
- **Q2.** Which watsonx.ai chat models are available in the target Orchestrate instance and region?
- **Q3.** Is the watsonx.ai model gateway available on the target account?
- **Q4.** What is the request and response contract for an Orchestrate `custom_search` server? IBM documents it under "Connecting to a custom content service."
- **Q5.** Which packages does the target Orchestrate tenant allow for Python tools? `search_policies` needs one embedding call. If `ibm-watsonx-ai` is not allowed, `embed()` uses a plain HTTPS request to the watsonx.ai embeddings API.
- **Q6.** How should `eval-local` send prompts to the deployed Orchestrate agent? The options are the Orchestrate API or an ADK CLI command.

---

## 12. References

- neo4j-graphrag for Python: https://neo4j.com/docs/neo4j-graphrag-python/current/
- Neo4j Aura: https://neo4j.com/cloud/platform/aura-graph-database/
- Aura instance actions, including Free tier pausing: https://neo4j.com/docs/aura/managing-instances/instance-actions/
- Aura backup, export, and restore: https://neo4j.com/docs/aura/managing-instances/backup-restore-export/
- Neo4j MCP server: https://neo4j.com/docs/mcp/current/
- watsonx Orchestrate ADK: https://developer.watson-orchestrate.ibm.com
- Orchestrate knowledge bases: https://developer.watson-orchestrate.ibm.com/knowledge_base/build_kb
- watsonx.ai embedding models: https://www.ibm.com/docs/en/SSYOK8/wsj/analyze-data/fm-models-embed.html
- watsonx.ai model gateway, Python SDK: https://ibm.github.io/watsonx-ai-python-sdk/v1.7.1/model_gateway.html
- LangChain IBM integration, `langchain-ibm`: https://python.langchain.com/docs/integrations/chat/ibm_watsonx/
- Faker: https://faker.readthedocs.io
- Docling: https://github.com/docling-project/docling
- Sibling integration: [`../README.md`](../README.md) and [`../memory-agent/`](../memory-agent/)
