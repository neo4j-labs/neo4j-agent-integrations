# Customer Demo Walkthrough

This is the presenter script for Demo Two, the customer support demo. Marcus Okafor (`C-1001`) asks why his wire transfer to Acme Corp failed and whether he will be charged a penalty fee. `banking_baseline` answers from the policy documents alone, with generic reasons a wire can fail. `banking_support` follows the graph links and says the wire is held, not failed, and that Premium Checking waives both wire fees. The expected answers for the other scenarios are in [The hero scenarios](../README.md#the-hero-scenarios).

The staff and fraud demo has its own script in [fraud-demo-walkthrough.md](fraud-demo-walkthrough.md).

Finish [Orchestrate Demos Setup](../README.md#orchestrate-demos-setup) first.

## Run it

```bash
uv run demo-walkthrough
```

The walkthrough calls Orchestrate itself, with the `orchestrate` CLI and the ADK client. For each step it prints where the step runs, the exact command, and the output. It does no setup. It only inspects what [Orchestrate Demos Setup](../README.md#orchestrate-demos-setup) loaded and asks the agents the scenario prompts.

### Steps 1-3: What Orchestrate holds

Lists what the setup created. Step 1 runs `orchestrate connections list --verbose`, filtered to `banking_creds`. It shows draft and live with credentials entered, and never shows the values. Step 2 runs `orchestrate agents list --kind native --verbose`, then `orchestrate tools list --verbose`. `banking_baseline` has no tools and one knowledge base, and `banking_support` has six tools, each bound to `banking_creds`. Step 3 runs `orchestrate knowledge-bases status -n banking_policies --verbose`. The knowledge base is ready and holds twelve documents.

Run these steps alone:

```bash
uv run demo-walkthrough --steps 1-3
```

### Step 4: The failure

Asks Scenario A of `banking_baseline` with `echo q | orchestrate chat ask -n banking_baseline -r "<prompt>"`. The answer is generic, because it comes from the policy text alone.

Run this step alone:

```bash
uv run demo-walkthrough --steps 4
```

### Step 5: The fix

Asks Scenario A of `banking_support` with the same command. The answer names the held wire and the waived fees. The step prints the chat's thread ID, which step 6 uses.

Run this step alone:

```bash
uv run demo-walkthrough --steps 5
```

### Steps 6-8: The trace

Step 6 finds the trace of the step 5 chat with `orchestrate observability traces search --last 30m --session-id <thread ID>`. Step 7 saves the trace's observations as JSON with `eval/eval-scripts/traces.py`, which calls the observability API with the ADK client. Step 8 summarises the model calls in that JSON and makes no call to Orchestrate.

Run these steps alone:

```bash
uv run demo-walkthrough --steps 6-8
```

To start at step 6, pass the thread ID from step 5:

```bash
uv run demo-walkthrough --steps 6-8 --thread-id <thread ID>
```

### Step 9: Scenarios B to D

Asks Scenarios B to D of `banking_support`, each in a new chat, with `orchestrate chat ask`.

Run this step alone:

```bash
uv run demo-walkthrough --steps 9
```

### Step 10: Scoring

Runs and scores Scenarios A to D on `banking_support` with `eval/eval-scripts/run_agent.py`, then `score.py`.

Run this step alone:

```bash
uv run demo-walkthrough --steps 10
```

### Step 11: The proof

Runs `orchestrate/proof_query.cypher` against Aura with the neo4j driver. The query is read-only. The step prints each path: from Marcus to the held wire, its compliance alert and rule, and the fee rules waived for Premium Checking, each with its policy text.

Run this step alone:

```bash
uv run demo-walkthrough --steps 11
```

## Runner options

| Flag | Effect |
|---|---|
| `--steps` | Runs only some steps, for example `--steps 1-3` or `--steps 4,5` |
| `--skip-scoring` | Skips step 10, which sends four more prompts and takes a minute or two |
| `--agent`, `--baseline-agent` | Names the agent with tools and the knowledge base agent. The defaults are `banking_support` and `banking_baseline`. |
| `--thread-id` | Gives step 6 a `banking_support` thread ID when you skip step 5 |
| `--trace-id` | Gives step 7 a trace ID when you skip step 6 |
| `--out-dir` | Where to write the trace dump and the scoring runs. The default is a new temporary folder. |

The script exits with status 1 if any scenario fails scoring in step 10. The model's wording varies from run to run, so the answers differ each time. Scenario C checks that the answer names Marcus's Emergency Fund as the account to link for Overdraft Protection. `get_my_accounts` lists the savings accounts the customer holds that can be linked, so the agent can name it. On 2026-10-21, `make wxo-eval SCENARIOS=C RUNS=3` passed 3 of 3 runs on the tenant, and `eval-local` passed 3 of 3. A run on 2026-10-21 passed steps 1 to 9, and in step 10 scenarios A, B, and D passed.
