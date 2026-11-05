# Troubleshooting and Cleanup

This page covers the environment checks, the common failures, and how to remove the demo from your tenant.

## Validate your environment

Run these checks in order. Each one depends on the step before it.

Check that Aura answers `RETURN 1`:

```bash
make check
```

Check that the ADK is installed:

```bash
orchestrate --version
```

Log in to the instance:

```bash
make wxo-env
```

Check that `WO_ENV_NAME` is marked active:

```bash
orchestrate env list
```

Check that the tenant offers the agent model:

```bash
orchestrate models list | grep bedrock/openai.gpt-oss
```

After `make wxo-setup`, check that each customer object exists:

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

Show `banking_creds` for draft and live:

```bash
orchestrate connections list
```

Show the six tools from `tools.py`:

```bash
orchestrate tools list
```

Show `banking_support` and `banking_baseline`:

```bash
orchestrate agents list
```

Show that the knowledge base is ready:

```bash
orchestrate knowledge-bases status -n banking_policies
```

`make wxo-check` covers the customer demo only. To check the staff demo, use the list commands in [Build both demos](../README.md#build-both-demos).

If a check fails, see [Troubleshooting](#troubleshooting).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `orchestrate: command not found` | Install the ADK. See [Install the ADK](../README.md#install-the-adk). If it is installed, run `uv tool update-shell` and open a new terminal. |
| A command fails with an authentication or token error | The login expired. Run `make wxo-env`. |
| `make wxo-env` fails with `Error getting IBM_IAM Token` | The auth type does not match the API key. Set `WO_AUTH_TYPE` in `.env`, run `orchestrate env remove -n <env>`, then run `make wxo-env` again. |
| `WO_<KEY> is not set in .env` from `connect_env.sh` | Fill in that value in `.env`, then re-run `make wxo-env`. |
| `<KEY> is not set in .env` from `create_connection.sh` | Fill in that value in `.env`, then re-run `make wxo-connection`. |
| `<KEY> is not set in .env` from `create_staff_connection.sh` | Fill in that value in `.env`, then re-run `make wxo-staff-connection`. |
| `FRAUD_REVIEWER_EMAIL` is not set, from `build_referral_tools.sh` | Export it in the shell with the tenant login for Sam Price. The script does not read `.env`. |
| The tool import rejects `neo4j` or `openai` | The tenant's package allowlist does not include the pinned version. Compare the pins in `orchestrate/build/requirements.txt` with the allowlist. For the staff tools, the file is `orchestrate/build/staff_requirements.txt`. |
| `bank_supervisor` has no collaborators, or its import fails | Import `banking_policy`, `credit_analyst`, and `fraud_investigator` first. Run `make wxo-supervisor` after `make wxo-staff-agents`. See [How the setup works](../README.md#how-the-setup-works). |
| The proof query draws no connected group | The `build-groups` step did not run. Run `uv run build-groups` to rebuild the groups without a full reset. It creates a billed Aura Graph Analytics session while it runs. |
| `banking_baseline` answers without any policy content | The knowledge base is still processing. Check `orchestrate knowledge-bases status -n banking_policies` and wait until it is ready. |
| The tools return Neo4j connection errors | The AuraDB Free instance may be paused. Resume it from the Aura console. |

## Removing the demo

Remove the agents first, because they reference the tools and the knowledge base.

Remove `banking_support`:

```bash
orchestrate agents remove --name banking_support --kind native
```

Remove `banking_baseline`:

```bash
orchestrate agents remove --name banking_baseline --kind native
```

Remove the knowledge base:

```bash
orchestrate knowledge-bases remove --name banking_policies
```

Remove the six tools:

```bash
for tool in search_policies get_my_accounts find_my_transactions \
            explain_transaction get_my_household get_scheduled_payments; do
  orchestrate tools remove --name "$tool"
done
```

Remove the connection:

```bash
orchestrate connections remove --app-id banking_creds
```

If you built [Demo One](../README.md#orchestrate-demo-one-staff-and-fraud), remove its objects first. `banking_policy` reads `banking_policies`, so it must go before the knowledge base. Skip the referral tools and flow if you did not import them.

Remove the four staff agents:

```bash
for agent in bank_supervisor credit_analyst fraud_investigator banking_policy; do
  orchestrate agents remove --name "$agent" --kind native
done
```

Remove the staff tools:

```bash
for tool in find_my_client get_application check_lending_rules \
            get_beneficial_owners get_connected_group find_circular_flows \
            screen_business create_fraud_referral resolve_fraud_referral \
            fraud_referral; do
  orchestrate tools remove --name "$tool"
done
```

Remove the staff connection:

```bash
orchestrate connections remove --app-id banker_creds
```

This leaves the Aura graph in place. To empty the database too, run this command:

```bash
make reset
```
