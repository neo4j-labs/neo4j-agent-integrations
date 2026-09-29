# Sample 1: Terraform

Provisions the [overview](../../README.md) stack with the
[Snowflake Terraform provider](https://registry.terraform.io/providers/snowflakedb/snowflake/latest/docs).

| File | Creates |
| --- | --- |
| `main.tf` | provider, database, schema |
| `iam.tf` | role, user grant, database/schema/warehouse grants |
| `neo4j_access.tf` | secret, network rule, external access integration |
| `functions.tf` | model stage and upload, Python UDFs, SQL wrappers, grants |
| `agent.tf` | Cortex agent, usage grant |
| `setup-terraform.sql` | bootstrap for the `TERRAFORM_SVC` service role/user |

## Prerequisites

- Snowflake account with `ACCOUNTADMIN` for the bootstrap
- Terraform >= 1.4
- [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation)
  (`snow`) on `PATH`, for the model upload; override with `SNOW=/path/to/snow`
- Python 3 with `sentence-transformers`, if `shared/model/minilm/` is still empty on first apply

## Setup

1. **Bootstrap the service user.** Put a public key into `setup-terraform.sql`
   and run it as `ACCOUNTADMIN`: creates the `TERRAFORM_SVC` role and service user.

2. **Configure Terraform variables.**

   ```bash
   cd samples/1-terraform
   cp terraform.tfvars.example terraform.tfvars
   # fill in organization, account, user, private key path, neo4j password
   ```

3. **Apply.**

   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

   The first apply downloads `all-MiniLM-L6-v2` into `shared/model/minilm/` and
   uploads it to the `MODEL_STAGE` internal stage. Later applies upload again only
   when the model files change.

## Implementation notes

- Provider `~> 2.21`. Preview resources (`preview_features_enabled` in `main.tf`):
  external access integration, Python and SQL functions.
- The model upload runs `snow stage copy` from a `terraform_data` provisioner:
  the provider has no resource for stage file uploads.
- Both Python UDFs have identical settings (Python 3.13, `neo4j` +
  `sentence-transformers`, the Neo4j external access integration, the secret, the
  model stage import), so the warehouse can reuse one runtime for `QUERY_NEO4J`
  and `GENERATE_EMBEDDINGS`.
- SQL function bodies live in `shared/sql/*.sql`, rendered with `templatefile()`:
  `${query_neo4j}` and `${generate_embeddings}` become the fully qualified UDF
  names at apply time.
- Neo4j credentials are a `snowflake_secret_with_basic_authentication`, read in
  the Python UDF with `_snowflake.get_username_password('cred')`.
