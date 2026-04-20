# Snowflake Cortex Agents + Neo4j Integration

## Overview

**Snowflake Cortex Agents** provides agent capabilities within Snowflake, processing both structured data (via Cortex
Analyst) and unstructured data (via Cortex Search).

This project provisions a Cortex agent that can research companies against the
Neo4j [companies demo graph](neo4j+s://demo.neo4jlabs.com:7687) through a set
of Python UDFs and SQL wrapper functions, all managed by Terraform.

**Official resources:**
- Website: https://www.snowflake.com/en/data-cloud/cortex
- Documentation: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents

## Architecture

```
Cortex Agent (NEO4J_RESEARCH_AGENT)
    └── SQL wrapper functions (agent tools)
          ├── GET_ORGANIZATION_INVESTORS(company)
          ├── ANALYZE_RELATIONSHIPS(company, limit, max_depth)
          └── SEARCH_NEWS_ARTICLES(company, query, limit)
                └── Python UDFs
                      ├── QUERY_NEO4J(cypher, params)   -> Neo4j bolt driver
                      └── GENERATE_EMBEDDINGS(text)     -> all-MiniLM-L6-v2
```

- `QUERY_NEO4J` connects to Neo4j using credentials stored in a Snowflake
  secret and reached via an external access integration.
- `GENERATE_EMBEDDINGS` loads `all-MiniLM-L6-v2` from an internal stage and
  returns a vector used by the Cypher `db.index.vector.queryNodes` call in
  `SEARCH_NEWS_ARTICLES`.
- The agent spec (`terraform/templates/agent_spec.yaml.tftpl`) exposes the
  three SQL functions as tools.

## Repository layout

```
snowflake-cortex/
├── functions/                       # Python UDF handlers
│   ├── query_neo4j.py
│   └── generate_embeddings.py
├── terraform/
│   ├── main.tf                      # provider, database, schema
│   ├── iam.tf                       # role, user grant, database/schema grants
│   ├── neo4j_access.tf              # secret, network rule, external access integration
│   ├── functions.tf                 # model stage, Python UDFs, SQL wrappers, grants
│   ├── agent.tf                     # Cortex agent wiring
│   ├── variables.tf
│   ├── terraform.tfvars.example
│   ├── sql/                         # bodies of the SQL wrapper functions
│   ├── templates/                   # agent spec YAML
│   ├── scripts/                     # stage upload script
│   └── minilm/                      # downloaded SentenceTransformer files (gitignored)
├── setup-terraform.sql              # bootstrap for the TERRAFORM_SVC service role/user
└── README.md
```

## Prerequisites

- Snowflake account with `ACCOUNTADMIN` privileges for initial setup
- Terraform >= 1.0
- `snowsql` CLI on `PATH` (used to upload the embedding model to the stage;
  override with `SNOWSQL=/path/to/snowsql`)
- Python 3 with `sentence-transformers` if `terraform/minilm/` needs to be
  populated on first apply

## Setup

1. **Bootstrap the service user.** Edit `setup-terraform.sql` with a public
   key and run it as `ACCOUNTADMIN` to create the `TERRAFORM_SVC` role and
   matching service user.

2. **Configure Terraform variables.**

   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # fill in organization, account, user, private key path, neo4j password
   ```

3. **Apply.**

   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

   The first apply downloads `all-MiniLM-L6-v2` into `terraform/minilm/` and
   uploads it to the `MODEL_STAGE` internal stage. Subsequent applies skip
   the upload unless the model files change.

## Running the agent

Once `terraform apply` finishes, the agent is available as
`NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_RESEARCH_AGENT` and can be invoked
through Snowsight or the Cortex Agents REST API. The underlying tools can
also be called directly as SQL functions, e.g.:

```sql
SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GET_ORGANIZATION_INVESTORS('Uniphore');

SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.ANALYZE_RELATIONSHIPS('Uniphore', 2);

SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.SEARCH_NEWS_ARTICLES('Uniphore', 'Roberto Pieraccini', 3);
```

## Implementation notes

- The external access integration is created through `snowflake_execute`
  because the provider does not yet expose it as a first-class resource.
- Python UDFs share a runtime config (Python 3.13, `neo4j` +
  `sentence-transformers`, the Neo4j external access integration, and the
  model stage import) so a single warehouse runtime can be reused across
  `QUERY_NEO4J` and `GENERATE_EMBEDDINGS`.
- SQL function bodies live in `terraform/sql/*.sql` and are rendered with
  `templatefile()`; the `${query_neo4j}` and `${generate_embeddings}`
  placeholders are substituted with fully qualified UDF identifiers at
  apply time.
- Neo4j credentials are stored in a `snowflake_secret_with_basic_authentication`
  resource and read inside the Python UDF via
  `_snowflake.get_username_password('cred')`.

