# watsonx Orchestrate Demo: Tests and Findings

These notes record how the Orchestrate demo was tested on 2026-10-19. They cover what was found, what was fixed, and how different models compare.

The tenant ran ADK CLI v2.18.2 against an MCSP instance. The Neo4j Aura graph held the full demo dataset. Customer Marcus Okafor is C-1001 and holds accounts A-1001, A-1002 and A-1003.

## Summary of results

| Model | Where it runs | Best style | Score | Notes |
|---|---|---|---|---|
| gpt-oss-120b | Amazon Bedrock | default | 39/39 | The demo default. Its first tool call often sends a bad argument, and it then retries. |
| frontier | watsonx Orchestrate | default | 39/39 | It made the fewest tool calls and gave the clearest Scenario D answer. |
| gpt-5.6-terra | OpenAI | default or react_core | 39/39 | It needs `reasoning_effort: none` in the model spec. |
| GPT-6 Luna | OpenAI | react_core | 38/39 | It needs `reasoning_effort: none`. In default style it trusts the real date over the demo date and scores 17/39. |
| Granite 4 H Small | watsonx | react | 33/39 | It works only in react style. Its answers leave out fee amounts and the mortgage payment. |

Each score is the total of the scenario A, B, C and D checks. The full table is in [Results](#results).

## What was fixed

### Connecting to the instance

The README told users to run `orchestrate env add ... --type ibm_iam --activate` by hand. That command failed on this instance with `Provided API key could not be found`. The instance URL is `https://api.dl.watson-orchestrate.ibm.com/instances/...`, which is an MCSP instance. MCSP instances need the `mcsp_v2` auth type, not `ibm_iam`.

**Fix:** The new script `orchestrate/connect_env.sh` reads `WO_ENV_NAME`, `WO_INSTANCE_URL` and `WO_API_KEY` from `.env`. It adds the environment only when it does not exist yet. It then runs `orchestrate env activate --api-key`, so nothing prompts. The ADK picks the auth type from the URL by default. An optional `WO_AUTH_TYPE` in `.env` overrides that guess. `make wxo-env` runs the script.

The script was tested on four paths:

- A fresh environment with the auth type picked from the URL.
- A re-run against an existing environment. The script skips the add and logs in again.
- A forced `WO_AUTH_TYPE=ibm_iam`. This fails on this instance with the ADK's own error, which is the expected result.
- A missing `.env` key. The script exits with `WO_<KEY> is not set in .env`.

A two-hour login expiry is fixed by re-running `make wxo-env`.

### Importing the tools

`make wxo-tools` failed with `No module named 'neo4j'`. `orchestrate tools import` loads the tool file locally to read its signatures. The tool file imports `neo4j` at the top, so the ADK's own Python needs that package.

**Fix:** The README now installs the ADK with the tool dependencies:

```bash
uv tool install ibm-watsonx-orchestrate --with neo4j --with openai
```

`uv tool upgrade` keeps the `--with` packages.

### Files changed

- `orchestrate/connect_env.sh` is new.
- `Makefile` has a new `wxo-env` target.
- `env.sample` has a new watsonx Orchestrate section with the `WO_*` keys and the commented-out `WO_AUTH_TYPE`.
- `README.md` has updated install, connect, setup and troubleshooting sections.
- `eval/eval-scripts/` holds the new test scripts.
- `docs/orchestrate-demo.md` is this document.

## How the agents were tested

Each agent got the same four prompts from `eval/scenarios.yaml`:

| Scenario | Prompt |
|---|---|
| A | Why did my wire transfer to Acme Corp fail yesterday, and will I be charged a penalty fee? |
| B | Sarah deposited a check into our joint account this morning. Has it cleared, and do we have enough to cover the mortgage? |
| C | What's the overdraft fee on our joint account, and how can we avoid it? |
| D | Show me the recent transactions on Sarah's savings account. |

A test script sent each prompt through the ADK's `RunClient` and waited for the run to finish. It then read the thread with `ThreadsClient`. The assistant message's `step_history` holds every tool call with its arguments and every tool response.

A second script fed the answer and the tool responses into `graphrag_banking.eval_local.score`. This is the same scorer the local eval uses. It checks three things:

- **Answer facts:** The answer must state each expected fact.
- **Trace facts:** The tool responses must contain each expected record.
- **Must not appear:** The answer must leave out data the customer is not allowed to see.

### Test scripts

The scripts are in `eval/eval-scripts/`:

- **`run_agent.py`:** This script sends prompts to one agent and saves each run as JSON. It runs with the ADK's Python.
- **`score.py`:** This script scores a folder of saved runs with the project's scorer. It runs with the project's Python.
- **`traces.py`:** This script lists recent traces or dumps one trace's observations. It runs with the ADK's Python.

```bash
ADK_PY="$(uv tool dir)/ibm-watsonx-orchestrate/bin/python"

# Agent ids come from `orchestrate agents list`.
"$ADK_PY" -I eval/eval-scripts/run_agent.py banking_support <agent_id> runs \
  "A=Why did my wire transfer to Acme Corp fail yesterday, and will I be charged a penalty fee?" \
  "D=Show me the recent transactions on Sarah's savings account."

uv run python eval/eval-scripts/score.py runs

# A trace's sessionId is the run's thread_id from the saved JSON.
"$ADK_PY" -I eval/eval-scripts/traces.py list 30
"$ADK_PY" -I eval/eval-scripts/traces.py get <trace_id> trace.json
```

`traces.py get` can dump only traces from the last four hours.

The scripts were checked from the repo after they were added. Ruff reports no issues. `score.py` gives the same scores as the test runs on the saved results. A new Scenario D run on `banking_support` scored 5/5 in 9.6 s. `traces.py` found that run's trace and dumped 44 observations. The trace held five gpt-oss-120b model calls, with 1,256 to 8,486 input tokens and 27 to 131 output tokens each.

## Results

| Agent | Model | Style | A | B | C | D |
|---|---|---|---|---|---|---|
| `banking_support` | `bedrock/openai.gpt-oss-120b-1:0` | default | 11/11, 14.0 s | 12/12, 16.1 s | 11/11, 11.2 s | 5/5, 11.7 s |
| `banking_support_frontier` | `watsonx-orchestrate/frontier` | default | 11/11, 20.9 s | 12/12, 13.8 s | 11/11, 11.4 s | 5/5, 7.8 s |
| `banking_support_granite_react` | `watsonx/ibm/granite-4-h-small` | react | 8/11, 18.2 s | 9/12, 11.5 s | 11/11, 11.8 s | 5/5, 2.6 s |
| `banking_support_openai_luna` | `virtual-model/openai/gpt-6-luna` | default | 1/11, 7.4 s | 1/12, 9.3 s | 10/11, 11.5 s | 5/5, 9.7 s |
| `banking_support_openai_luna_react` | `virtual-model/openai/gpt-6-luna` | react | 1/11, 5.1 s | 0/12, 2.7 s | 2/11, 2.8 s | 5/5, 2.7 s |
| `banking_support_openai_luna_react_core` | `virtual-model/openai/gpt-6-luna` | react_core | 11/11, 7.5 s | 12/12, 13.4 s | 10/11, 9.2 s | 5/5, 4.7 s |
| `banking_support_openai_terra` | `virtual-model/openai/gpt-5.6-terra` | default | 11/11, 9.4 s | 12/12, 9.1 s | 11/11, 9.0 s | 5/5, 2.6 s |
| `banking_support_openai_terra_react_core` | `virtual-model/openai/gpt-5.6-terra` | react_core | 11/11, 7.3 s | 12/12, 11.4 s | 11/11, 9.4 s | 5/5, 4.7 s |

### gpt-oss-120b on Amazon Bedrock

Bedrock is the AWS model service. The model id `bedrock/openai.gpt-oss-120b-1:0` means Orchestrate calls OpenAI's open-weight gpt-oss-120b as hosted on Amazon Bedrock. The tenant also lists the same model on Groq and, as a hidden model, on watsonx. `orchestrate/build_agent.py` picks the Bedrock copy by default. `ORCHESTRATE_MODEL` overrides it.

This is the demo's default model. It passed every check.

Its first tool call often fails. It passes the `type` filter of `find_my_transactions` as a list, such as `["WIRE_OUT"]`, and the tool expects a string. The tool returns an error. The model then retries with a string and succeeds. Scenario D shows this four times in one run.

Its Scenario A answer contained an em-dash, although the agent instructions forbid them.

In Scenario D it showed Marcus's own Emergency Fund savings account. It did not reveal any of Sarah's data, so the scenario passed.

### frontier

`watsonx-orchestrate/frontier` passed every check. It made fewer tool calls than gpt-oss and never sent a bad argument. In Scenario D it explained that Marcus and Sarah share no savings account. It said it can only show accounts Marcus holds. This is the clearest answer of the three models.

### Granite 4 H Small

Granite is a hidden model. `orchestrate models list -a` shows it.

Granite works only with `style: react`:

- **default:** The run returns `LLM has responded with empty message`. The trace shows 17 output tokens and empty content.
- **react_core:** The agent replies that it did not understand the request.
- **react:** The agent calls the tools and answers.

With react style, tool responses come back as the string `Observation: {...}`. The braces hold a Python dict repr, not JSON. The scorer first read every Granite trace fact as missing. Parsing the repr fixed this, and the scores above use the fixed parser.

The remaining Granite failures come from its answers:

- **Scenario A:** Granite explains the wire hold correctly. It leaves out the $30 outgoing wire fee, the $35 returned-wire fee and the Premium Checking fee waiver.
- **Scenario B:** Granite searched for a transfer to "Mortgage Co." and found nothing. It never mentions the $3,200 Lakeside Home Loans payment. Its search also missed the pending transaction T-1123.
- **Scenario D:** Granite asked for Sarah's full account number and called no tools. It leaked nothing, so the scenario passed. It also never explained that Marcus cannot see Sarah's accounts.

Granite also used ISO dates and showed internal account IDs in its answers.

## Model calls in a trace

The observability API records every model call. This is the first `banking_support` run of Scenario A:

| Step | Model call | Input tokens | Output tokens | Model latency | Chosen tool |
|---|---|---|---|---|---|
| 1 | gpt-oss-120b | 1,266 | 87 | 0.5 s | `find_my_transactions` with a list `type`, which fails |
| 2 | gpt-oss-120b | 1,398 | 61 | 0.6 s | `find_my_transactions` with a string `type` |
| 3 | gpt-oss-120b | 1,612 | 42 | 0.4 s | `explain_transaction` for T-1022 |
| 4 | gpt-oss-120b | 2,428 | 257 | 2.2 s | none, writes the answer |

The run took 68.3 s in total. The four model calls took 3.7 s of that. The first real tool call took 57 s, because the tool runtime had a cold start. Later tool calls took about 6 s each, and most of that time was spent in the tool runtime's `/execute` call.

Each `GENERATION` observation holds the model name, the token counts, the latency, the input messages and the output. The output includes the tool calls and the model's reasoning text.

## ADK issues found

- **`observability traces export` fails on every published ADK version.** The `/observations` endpoint requires `fromStartTime` and `toStartTime`, and the CLI never sends them. The API rejects the request with a 400. ADK 2.16.3, 2.17.0, 2.18.1 and 2.18.2 share the same code. Calling `/observations` directly with a window of four hours or less works. That endpoint allows four requests per minute.
- **`observability traces search` works.** `--session-id <thread_id>` finds the trace for one chat thread.
- **`chat ask` stays open after the answer.** With stdin at `/dev/null` it loops forever on EOF. Piping `q` into it ends the session: `echo q | orchestrate chat ask -n banking_support -r "..."`.
- **`chat ask` hides tool arguments.** The reasoning trace prints the tool names and responses. A bug in `format_reasoning_trace` drops the arguments.
- **`style: default` is deprecated.** The ADK replaces it with `react_core`, which `agents list` shows as `react_intrinsic`.

## OpenAI models

OpenAI models reach Orchestrate as custom provider models. Two models were tested: `gpt-6-luna` and `gpt-5.6-terra`. OpenAI's `/v1/models` also lists `gpt-6-sol`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-5.6-luna` and `gpt-5.6-sol`.

### Adding an OpenAI model

The API key goes into a key_value connection:

```bash
orchestrate connections add -a openai_creds
orchestrate connections configure -a openai_creds --env draft --kind key_value --type team
orchestrate connections configure -a openai_creds --env live --kind key_value --type team
orchestrate connections set-credentials -a openai_creds --env draft -e "api_key=$OPENAI_API_KEY"
orchestrate connections set-credentials -a openai_creds --env live -e "api_key=$OPENAI_API_KEY"
```

`orchestrate models add --name openai/gpt-6-luna --app-id openai_creds` registers the model. Its tool-calling checks fail, though. OpenAI returns a 400: `Function tools with reasoning_effort are not supported for gpt-6-luna in /v1/chat/completions`. OpenAI applies a reasoning effort by default, and only an explicit `none` allows tool calls. `low` fails too. gpt-5.6-terra behaves the same way.

Setting `reasoning_effort: none` in the agent's `llm_config` has no effect. The agent still gets the 400. The setting has to go in a model spec:

```yaml
spec_version: v1
kind: model
name: virtual-model/openai/gpt-6-luna
display_name: GPT-6 Luna (OpenAI)
model_type: chat
provider_config:
  provider: openai
config:
  model: gpt-6-luna
  reasoning_effort: none
```

```bash
orchestrate models import -f model_gpt-6-luna.yaml --app-id openai_creds
```

The import updates the model, and all four validation checks pass. Agents use the name `virtual-model/openai/gpt-6-luna`.

### GPT-6 Luna

Luna fails in `default` style because it trusts the wrong date. In `default` style the runtime adds `The current date is October 19, 2026.` to the end of the system prompt. That line comes after the agent's instruction that today is Thursday, October 8, 2026. Luna follows the later line. In Scenario A it searched for wires on October 18. In Scenario B it searched for October 19. It found nothing in either case and answered that it did not know. gpt-oss and terra follow the agent's date. Default style also kept only one of the three tool calls Luna made in parallel on its first turn in Scenario A.

In `react` style Luna still used the real date in Scenario A. In Scenarios B and C it asked clarifying questions and called no tools.

The `react_core` prompt has no extra date line, so Luna gets the date right. It then scored 38 of 39. Its answers were among the best of all the models tested:

- **Scenario A:** Luna said the wire is held, not failed. It named the Payment Screening policy and both waived fees with their amounts.
- **Scenario B:** Luna gave the $1,800 available balance, the pending $2,000 check available October 9, the $3,200 Lakeside Home Loans payment on October 13 and the $3,800 projected balance.
- **Scenario C:** Luna's only miss was here. It never named Marcus's Emergency Fund savings as the account to link for Overdraft Protection.
- **Scenario D:** Luna called `get_my_household` and declined to show Sarah's account.

Its model calls in `react_core` style:

| Scenario | Model calls | Input tokens per call | Output tokens per call | Latency |
|---|---|---|---|---|
| A | 3 | 1,265 / 1,490 / 2,314 | 46 / 22 / 125 | 6.2 s |
| B | 5 | 1.3k to 3.1k | 107 / 77 / 59 / 24 / 150 | 11.4 s |
| C | 3 | 1,261 / 1,546 / 2,882 | 14 / 53 / 153 | 8.5 s |
| D | 2 | 1,255 / 1,356 | 15 / 34 | 3.0 s |

### gpt-5.6-terra

Terra passed every check in both `default` and `react_core` style. Its answers matched Luna's on Scenarios A and B. It also named the savings account to link in Scenario C. In `default` style its Scenario D answer was the sentence "I can only show accounts you hold." printed twice, with no tool call. That still passes, because no data leaked.

No OpenAI answer showed internal transaction, account, payment or rule IDs.

## Test objects in the tenant

These objects were created only for testing:

- **Agents:**
  - `banking_support_frontier`
  - `banking_support_granite`
  - `banking_support_granite_react`
  - `banking_support_granite_react_core`
  - `banking_support_openai_luna`
  - `banking_support_openai_luna_react`
  - `banking_support_openai_luna_react_core`
  - `banking_support_openai_terra`
  - `banking_support_openai_terra_react_core`
- **Models:** `virtual-model/openai/gpt-6-luna` and `virtual-model/openai/gpt-5.6-terra`.
- **Connection:** `openai_creds`.

Agents are removed with `orchestrate agents remove -n <name> -k native`. Models are removed with `orchestrate models remove -n <name>`. The connection is removed with `orchestrate connections remove -a openai_creds`.
