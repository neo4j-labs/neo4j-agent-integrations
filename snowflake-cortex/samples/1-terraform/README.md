# Sample 1: Terraform

This sample creates the [overview](../../README.md) stack with the [Snowflake Terraform provider](https://registry.terraform.io/providers/snowflakedb/snowflake/latest/docs).

| File | What it creates |
| --- | --- |
| `main.tf` | The provider, the database and the schema. |
| `iam.tf` | The `USER` role and its grants on the database, schema and warehouse. |
| `neo4j_access.tf` | The secret, the network rule and the external access integration. |
| `functions.tf` | The model stage and upload, the Python UDFs, the SQL tool functions and their grants. |
| `accounts.tf` | The `CUSTOMER_ACCOUNTS` view, its semantic view and the grant on it. |
| `agent.tf` | The Cortex agent and its usage grant. |
| `setup-terraform.sql` | The `TERRAFORM_SVC` role and service user that Terraform runs as. |

## Prerequisites

- A Snowflake account. You need `ACCOUNTADMIN` once, to run `setup-terraform.sql`.
- Terraform 1.4 or later.
- The [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation) (`snow`) on your `PATH`. Terraform uses it to upload the model. To use another binary, set `SNOW=/path/to/snow`.
- Python 3 with `sentence-transformers`. The first apply needs it to download the model.

## Setup

1. Create the service user. Add your public key to `setup-terraform.sql` and run the script as `ACCOUNTADMIN`.

2. Set the Terraform variables:

   ```bash
   cd samples/1-terraform
   cp terraform.tfvars.example terraform.tfvars
   # Fill in organization, account, user, private key path and Neo4j password.
   ```

3. Apply:

   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

   The first apply downloads `all-MiniLM-L6-v2` into `shared/model/minilm/` and uploads it to the `MODEL_STAGE` stage. Later applies upload it again only if the files change.

## Implementation notes

- The sample needs provider version 2.21. Some resources are preview features, which `main.tf` enables: the external access integration, the Python and SQL functions and the semantic view.
- The provider cannot upload files to a stage. A `terraform_data` provisioner runs `snow stage copy` instead.
- Both Python UDFs use identical settings. This lets the warehouse run them in one Python runtime.
- The SQL function bodies are in `shared/sql/*.sql`. `templatefile()` replaces `${query_neo4j}`, `${generate_embeddings}` and `${customer_accounts}` with fully qualified names.
- `CUSTOMER_ACCOUNTS` is a view over `VALUES`, so no table load is needed. Renewal dates are relative to the current date.
- `CUSTOMER_ACCOUNTS_SV` matches `shared/sql/customer_accounts_semantic_view.sql`, which the Snowsight guide runs.
- The `query_neo4j` tool lets the agent write Cypher. Read the [warning](../../README.md#free-form-cypher) first.
- The provider quotes names, so they are case-sensitive. Argument names, semantic view aliases and expression names are therefore uppercase. Tools call UDFs by argument name, and Cortex Analyst rejects quoted lowercase names.
- The provider shows some changes as in-place updates but does not apply them: renamed UDF arguments, and changed tables, dimensions or metrics of a semantic view. Apply them with `terraform apply -replace=<resource>`.
- The Neo4j login is a `snowflake_secret_with_basic_authentication`. The Python UDF reads it with `_snowflake.get_username_password('cred')`.
