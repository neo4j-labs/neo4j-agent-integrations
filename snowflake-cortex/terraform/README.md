# Snowflake Cortex Terraform Setup

Provisions a Snowflake database, schema, role, Neo4j external access
integration, Python + SQL UDFs, and a Cortex agent wired to those UDFs.

## Prerequisites

- Snowflake account with `ACCOUNTADMIN`/`SYSADMIN` privileges
- A service user with the `TERRAFORM_SVC` role and a JWT key pair configured
- Terraform >= 1.0
- `snowsql` CLI on `PATH` (used by the stage upload provisioner;
  override with `SNOWSQL=/path/to/snowsql`)
- Python 3 with `sentence-transformers` if `minilm/` needs to be downloaded

## Layout

```
terraform/
├── main.tf              # provider, versions, database, schema, locals
├── iam.tf               # role, user grant, database/schema grants
├── neo4j_access.tf      # secret, network rule, external access integration
├── functions.tf         # model stage, Python UDFs, SQL wrappers, grants
├── agent.tf             # Cortex agent that exposes the SQL wrappers as tools
├── variables.tf
├── terraform.tfvars.example
├── sql/                 # bodies of the SQL wrapper functions (templatefile)
├── templates/           # agent spec YAML (templatefile)
├── scripts/             # stage upload script (templatefile)
└── minilm/              # downloaded SentenceTransformer files (gitignored)
```

## Usage

```bash
cp terraform.tfvars.example terraform.tfvars   # then fill in values

terraform init
terraform plan
terraform apply
```

The first apply downloads the `all-MiniLM-L6-v2` model into `minilm/` and
uploads it to the `MODEL_STAGE` stage. Subsequent applies skip the upload
unless the model files change.

## Notes

- The external access integration is created with `snowflake_execute` because
  the provider does not yet expose it as a first-class resource.
- SQL function bodies live in `sql/*.sql` and are rendered with
  `templatefile()`; the placeholder `${query_neo4j}` (and
  `${generate_embeddings}` in `search_news_articles.sql`) is substituted with
  the fully-qualified UDF identifier.
- The agent spec lives in `templates/agent_spec.yaml.tftpl`; tool names and
  function identifiers are injected at apply time.
