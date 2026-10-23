# Integrations

This page shows how to set up and run the `fraud_referral` flow in watsonx Orchestrate. The flow is a workflow built with the ADK flow builder. It calls two Neo4j-backed tools, so it shows a graph write inside a process with a human in the loop. The [README](../README.md#optional-referral-workflow) has the short version.

## What the flow does

`fraud_referral` takes an application ID, the red flag rule codes from a fraud check, and a short summary. It runs five steps:

1. A form asks the banker who started the flow to confirm or cancel. Cancel ends the flow and writes nothing.
2. `create_fraud_referral` writes a `FraudReferral` node to Neo4j with status `OPEN`.
3. A message gives the banker the referral ID and the `AML-NO-TIPOFF` reminder.
4. A script looks up the fraud reviewer by email, and a second form assigned to that person offers Accept and Close.
5. `resolve_fraud_referral` sets the status to `ACCEPTED` or `CLOSED`.

Both tools read the `banker_creds` connection. The connection supplies the banker ID, so the model never chooses who submitted a referral. The flow has no connection of its own.

The files are:

| File | Role |
|---|---|
| `orchestrate/flows/fraud_referral_flow.py` | The flow definition |
| `orchestrate/tools/referral_banking_tools.py` | The two Orchestrate tool wrappers |
| `src/graphrag_banking/referral_tools.py` | The Cypher functions the wrappers call |
| `orchestrate/build_referral_tools.sh` | Imports the tools, then the flow |
| `orchestrate/referral_proof_query.cypher` | Draws the referral in the Aura Query tool |

## Before you start

The flow needs the staff demo to exist first, because the tools reuse its connection.

1. Install the ADK. See [Install the ADK](../README.md#install-the-adk).
2. Fill in `.env` and build the graph with `make rebuild`.
3. Log in to the tenant:

   ```bash
   make wxo-env
   ```

   The login lasts two hours. Run it again when a command fails with an authentication error.

4. Create the `banker_creds` connection. This needs `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `DEMO_BANKER_ID`, and `DEMO_AS_OF` in `.env`:

   ```bash
   make wxo-staff-connection
   ```

   `make wxo-staff-setup` also creates the connection, and it builds the staff agents the fraud story uses. It needs the `banking_policies` knowledge base from `make wxo-setup`.

## Set up

### 1. Choose the reviewer

The flow assigns the review form to a tenant user. It looks the user up by email when it runs, so the address must be a real login in this tenant.

For a demo, use your own tenant login. In preview, every form goes to the person who started the flow. You can then play both the banker and the reviewer. The form reaches the reviewer only in a live deploy.

### 2. Export the variable

`build_referral_tools.sh` does not read `.env`. Export the variable in the same shell that runs the script:

```bash
export FRAUD_REVIEWER_EMAIL=<email you log in to the tenant with>
```

Without it, the script stops with `Set FRAUD_REVIEWER_EMAIL to the tenant login for Sam Price`.

### 3. Import the tools and the flow

```bash
./orchestrate/build_referral_tools.sh
```

The script does this in order:

1. It copies `referral_banking_tools.py` and `referral_tools.py` into `orchestrate/build/referral_package/`. The second file is renamed `referral_queries.py`.
2. It checks that `referral_queries.py` does not import `graphrag_banking` at module level, because that import fails inside Orchestrate.
3. It exports the `neo4j` pin from `uv.lock`.
4. It imports the two tools on the `banker_creds` connection.
5. It imports the flow with `orchestrate tools import -k flow`.

The tools go first because the flow refers to them by name.

### 4. Check the import

Open **Active inventory > Agentic workflows** in the dashboard. The list should show **Fraud referral**. Before the import, the list shows `0 workflows`.

You can also list the imported objects from the terminal:

```bash
make wxo-list
```

The **Tools** page shows `create_fraud_referral` and `resolve_fraud_referral`.

## Run it

`bank_supervisor` does not call the flow yet. Its YAML says the referral tool and its instructions come with the referral workflow. To run the flow from the Chat page, an agent must list it as a tool.

The flow is imported as a tool, so an agent lists it by name under `tools:`. For example, add this to the agent YAML and re-import the agent:

```yaml
tools:
  - fraud_referral
```

Then add a routing line to the agent's instructions that tells it to call `fraud_referral` after the banker agrees to a referral. The call needs the application ID, the red flag rule codes, and a summary from the fraud check earlier in the chat. These steps have not been run against this tenant. Treat them as the first thing to test.

With the flow attached, the demo runs like this:

1. Open **Chat** and pick the agent.
2. Ask the fraud question for Ortega Builders. The answer lists the red flags, such as `FRAUD-SHARED-ID` and `FRAUD-CIRCULAR-FLOW`.
3. Ask the agent to refer the application. The confirm form appears in the chat.
4. Choose **Confirm**. A message gives the referral ID and the `AML-NO-TIPOFF` reminder.
5. Submit the review form with **Accept** or **Close**.

Choosing **Cancel** on the confirm form ends the flow and writes nothing.

To show the flow's structure, open it from **Active inventory > Agentic workflows**. The editor shows each step as a node.

## Prove the write in Neo4j

After the referral exists, the graph holds the evidence.

1. Open the Aura Query tool.
2. Paste `orchestrate/referral_proof_query.cypher`.
3. Switch to the graph view.

The query draws the newest referral for `APP-1001`. It shows Dana, the referral, the application and its business, the connected group, each cited red flag rule with its policy text, and the reviewer. It works after the reviewer accepts or closes the referral.

Aura saved queries belong to the user who saves them. Each presenter saves their own copy.

## Run it again

Delete every `FraudReferral` and leave the rest of the graph alone:

```bash
make demo-reset
```

The proof query returns nothing after a reset.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `FRAUD_REVIEWER_EMAIL` is not set | Export it in the shell. The script does not read `.env`. |
| The flow fails at the reviewer lookup | The address is not a login in this tenant. Export a valid address and run `build_referral_tools.sh` again. The address is read when the flow is imported. |
| The flow import fails because a tool is missing | The tools must exist before the flow. Run the whole script, not only the last command. |
| The tool import fails with an authentication error | The login expired. Run `make wxo-env`. |
| The tools return a connection error | The `banker_creds` connection is missing or incomplete. Run `make wxo-staff-connection`. Also check that the Aura instance is not paused. |
| `Agentic workflows` still shows `0 workflows` | Check that the active environment is the tenant you are viewing. Run `orchestrate env list`. |
| The review form never reaches a second person | In preview, every form goes to the person who started the flow. Deploy live to send it to the reviewer. |
| The proof query draws nothing | No referral exists yet, or `make demo-reset` removed it. |

[`docs/troubleshooting.md`](troubleshooting.md) covers the other Orchestrate setup errors.
