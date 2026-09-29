# Sample 2: Snowsight

Build the [overview](../../README.md) stack by hand in Snowsight: a Cortex Agent whose tools query the Neo4j `companies` demo graph. [Sample 1](../1-terraform/README.md) deploys the same with Terraform.

[![Watch the video](https://img.youtube.com/vi/QWc3SBc5sUE/maxresdefault.jpg)](https://youtu.be/QWc3SBc5sUE)

## What you build

| Step | Object | Kind |
| --- | --- | --- |
| [1](#1-database-and-schema) | `NEO4J_AGENT`, `NEO4J_AGENT_SCHEMA` | database, schema (everything below lives in it) |
| [2](#2-role) | `USER` | role for the people who chat with the agent |
| [4](#4-secret) | `NEO4J_CREDENTIALS` | secret: the Neo4j login |
| [5](#5-network-rule) | `NEO4J_ACCESS_RULE` | network rule: egress to Neo4j |
| [6](#6-external-access-integration) | `NEO4J_ACCESS_INTEGRATION` | integration (account level): rule + secret for UDFs |
| [7](#7-model-stage) | `MODEL_STAGE` | stage with the `all-MiniLM-L6-v2` model |
| [8](#8-python-udfs) | `QUERY_NEO4J`, `GENERATE_EMBEDDINGS` | Python UDFs: Cypher over Bolt, text to vector |
| [9](#9-tool-functions) | `GET_ORGANIZATION_INVESTORS`, `ANALYZE_RELATIONSHIPS`, `SEARCH_NEWS_ARTICLES` | SQL functions: the agent's tools |
| [10](#10-agent) | `NEO4J_RESEARCH_AGENT` | Cortex agent |

## Before you start

- Snowflake account, role `ACCOUNTADMIN`, a warehouse (X-Small is enough).
- Neo4j: the public demo database `neo4j+s://demo.neo4jlabs.com:7687`, login `companies`/`companies`.
- The model files, in `./minilm`:

  ```bash
  pip install sentence-transformers
  python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2').save('./minilm')"
  ```

- A workspace SQL file for the SQL (**Projects > Workspaces > + Add new > SQL file**), with the warehouse selected.

Each UI step has an **SQL instead** block: use one or the other.

## 1. Database and schema

1. **Catalog > Databases > + Database**, name `NEO4J_AGENT`, **Create**.
2. Open `NEO4J_AGENT`, **+ Schema**, name `NEO4J_AGENT_SCHEMA`, **Create**.

SQL instead:

```sql
CREATE DATABASE IF NOT EXISTS NEO4J_AGENT;
CREATE SCHEMA IF NOT EXISTS NEO4J_AGENT.NEO4J_AGENT_SCHEMA;
```

## 2. Role

Chat users get their own role instead of `ACCOUNTADMIN`.

1. **Governance & security > Users & roles**, tab **Roles**, **+ Role**, name `USER`, **Create Role**.
2. Click the `USER` row, **Grant to User**, pick your user, **Grant**.
3. Reload Snowsight: role pickers show `USER` only after a reload.

SQL instead:

```sql
CREATE ROLE IF NOT EXISTS "USER";
GRANT ROLE "USER" TO USER <your_user>;  -- SELECT CURRENT_USER();
```

## 3. Grants

1. **Catalog > Databases > NEO4J_AGENT**, tab **Access**, **+ Privilege**: role `USER`, privilege `USAGE`, **Grant privileges**.
2. Tab **Overview**, open `NEO4J_AGENT_SCHEMA`, tab **Access**, **+ Privilege**: role `USER`, privileges `USAGE` and `USAGE - FUTURE FUNCTION` (type to filter), **Grant privileges**.
3. The agent's tools run on the user's default warehouse: grant `USAGE` on it too (on the warehouse's privileges, or in SQL below).

![Grant dialog: role USER with USAGE and USAGE - FUTURE FUNCTION](images/grant-dialog.png)

The future grant covers every function created in the schema later, including the helpers `QUERY_NEO4J` and `GENERATE_EMBEDDINGS`. The Terraform sample grants only the three tool functions.

SQL instead:

```sql
GRANT USAGE ON DATABASE NEO4J_AGENT TO ROLE "USER";
GRANT USAGE ON SCHEMA NEO4J_AGENT.NEO4J_AGENT_SCHEMA TO ROLE "USER";
GRANT USAGE ON FUTURE FUNCTIONS IN SCHEMA NEO4J_AGENT.NEO4J_AGENT_SCHEMA TO ROLE "USER";
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE "USER";
```

Check:

```sql
SHOW GRANTS TO ROLE "USER";
SHOW FUTURE GRANTS IN SCHEMA NEO4J_AGENT.NEO4J_AGENT_SCHEMA;
```

## 4. Secret

SQL only; Snowsight has no dialog for secrets. `companies`/`companies` is the demo database's public login.

<!-- code: SECRET_SQL -->
```sql
CREATE OR REPLACE SECRET NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_CREDENTIALS
  TYPE     = PASSWORD
  USERNAME = 'companies'
  PASSWORD = 'companies';
```
<!-- /code -->

## 5. Network rule

Snowflake blocks outbound traffic by default; the rule allows one host and port.

1. **Governance & security > Network policies**, tab **Network Rules**, **+ Network Rule**.
2. Name `NEO4J_ACCESS_RULE`, location `NEO4J_AGENT.NEO4J_AGENT_SCHEMA`, type **Host port**, mode **Egress** (default).
3. **Host:port** `demo.neo4jlabs.com:7687`, then click **+**: the host must appear in the list below.
4. **Create**.

![New network rule dialog with demo.neo4jlabs.com:7687 in the host list](images/network-rule.png)

SQL instead:

```sql
CREATE NETWORK RULE NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_ACCESS_RULE
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('demo.neo4jlabs.com:7687');
```

For your own Neo4j, change the host here and the URI and database name in [`QUERY_NEO4J`](#8-python-udfs).

## 6. External access integration

SQL only. The integration binds rule and secret: a UDF reaches only the hosts and secrets its integration allows. Account-level object; needs `ACCOUNTADMIN` or `CREATE INTEGRATION`.

<!-- code: INTEGRATION_SQL -->
```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION NEO4J_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES          = (NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_ACCESS_RULE)
  ALLOWED_AUTHENTICATION_SECRETS = (NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_CREDENTIALS)
  ENABLED                        = TRUE;
```
<!-- /code -->

## 7. Model stage

The graph's article chunks carry `embedding_sbert` vectors from `all-MiniLM-L6-v2` (384 dimensions); search queries need the same model inside Snowflake.

1. **Catalog > Databases > NEO4J_AGENT > NEO4J_AGENT_SCHEMA**, **Create > Stage > Snowflake Managed**.
2. Name `MODEL_STAGE`, **Directory table** on, **Client-side encryption** (can't be changed later; **Create** stays disabled until one is picked), **Create**.
3. **Upload Files**: the files directly in `minilm/`, path `minilm`, **Upload** (about 90 MB).
4. Again with `minilm/1_Pooling/config.json`, path `minilm/1_Pooling`: the dialog takes one folder per upload. `2_Normalize/` is empty.

![Create Stage dialog: MODEL_STAGE, directory table on, client-side encryption](images/create-stage.png)

![Upload dialog with the model files and the path minilm](images/upload-files.png)

SQL instead, with the [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation) for the upload (run next to `minilm/`):

```sql
CREATE STAGE NEO4J_AGENT.NEO4J_AGENT_SCHEMA.MODEL_STAGE
  ENCRYPTION = (TYPE = 'SNOWFLAKE_FULL')
  DIRECTORY = (ENABLE = TRUE);
```

```bash
snow stage copy minilm @NEO4J_AGENT.NEO4J_AGENT_SCHEMA.MODEL_STAGE/minilm --recursive --overwrite --no-auto-compress
```

Upload uncompressed: gzipped model files can't be loaded.

Check: the list includes `minilm/model.safetensors` and `minilm/1_Pooling/config.json`.

```sql
LIST @NEO4J_AGENT.NEO4J_AGENT_SCHEMA.MODEL_STAGE/minilm;
```

## 8. Python UDFs

Run both statements in the workspace. Each builds its package environment, which takes about a minute.

`QUERY_NEO4J(cypher, params)` runs Cypher against Neo4j and returns the records as `VARIANT`.

<!-- code: QUERY_NEO4J_SQL -->
```sql
CREATE OR REPLACE FUNCTION NEO4J_AGENT.NEO4J_AGENT_SCHEMA.QUERY_NEO4J(CYPHER VARCHAR, PARAMS OBJECT)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = 3.13
PACKAGES = ('neo4j', 'sentence-transformers')
IMPORTS  = ('@NEO4J_AGENT.NEO4J_AGENT_SCHEMA.MODEL_STAGE/minilm/')
EXTERNAL_ACCESS_INTEGRATIONS = (NEO4J_ACCESS_INTEGRATION)
SECRETS = ('cred' = NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_CREDENTIALS)
HANDLER = 'query_neo4j'
COMMENT = 'Executes a cypher query against the Neo4j database'
AS $$
from neo4j import GraphDatabase
import socket
import _snowflake

# Snowflake reuses the UDF's process across calls, so one driver (and pool) serves them all.
# No teardown hook exists; the connection closes with the process.
_driver = None

def get_driver():
    global _driver
    if _driver is None:
        credentials = _snowflake.get_username_password('cred')
        _driver = GraphDatabase.driver(
            "neo4j+s://demo.neo4jlabs.com:7687",
            auth=(credentials.username, credentials.password)
        )
    return _driver

def query_neo4j(cypher, params):
    from neo4j.time import DateTime, Date, Time, Duration

    def serialize_neo4j(obj):
        if isinstance(obj, (DateTime, Date, Time, Duration)):
            return obj.iso_format()
        if isinstance(obj, list):
            return [serialize_neo4j(i) for i in obj]
        if isinstance(obj, dict):
            return {k: serialize_neo4j(v) for k, v in obj.items()}
        return obj

    try:
        records, summary, keys = get_driver().execute_query(
            cypher,
            parameters_=params,
            database_="companies"
        )
        return [serialize_neo4j(record.data()) for record in records] if records else []
    except (socket.gaierror, ValueError) as e:
        return {"error": f"Could not resolve Neo4j address: {str(e)}"}
    except Exception as e:
        return {"error": f"Neo4j query failed: {str(e)}"}
$$;
```
<!-- /code -->

- `EXTERNAL_ACCESS_INTEGRATIONS`: without it, every outbound connection is blocked.
- `SECRETS = ('cred' = ...)`: the code reads the login with `get_username_password('cred')`; it never appears in the source.
- `IMPORTS`: the model stage. Only `GENERATE_EMBEDDINGS` needs it; identical settings let both UDFs share one Python runtime.
- `neo4j+s://demo.neo4jlabs.com:7687` and `database_="companies"`: change both for your own Neo4j. The driver is created once per Python process.

`GENERATE_EMBEDDINGS(query)` loads the model from the stage and returns a 384-element vector.

<!-- code: GENERATE_EMBEDDINGS_SQL -->
```sql
CREATE OR REPLACE FUNCTION NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GENERATE_EMBEDDINGS(QUERY VARCHAR)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = 3.13
PACKAGES = ('neo4j', 'sentence-transformers')
IMPORTS  = ('@NEO4J_AGENT.NEO4J_AGENT_SCHEMA.MODEL_STAGE/minilm/')
EXTERNAL_ACCESS_INTEGRATIONS = (NEO4J_ACCESS_INTEGRATION)
SECRETS = ('cred' = NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_CREDENTIALS)
HANDLER = 'generate_embeddings'
COMMENT = 'Embedding function using sentence transformers'
AS $$
import os
import sys

# Snowflake reuses the UDF process across calls; load the model once.
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        # noinspection PyTypeChecker
        import_dir: str = sys._xoptions.get('snowflake_import_directory')
        model_path = os.path.join(import_dir, 'minilm/')
        _model = SentenceTransformer(model_path)
    return _model


def generate_embeddings(input_text: str) -> list:
    model = get_model()
    embedding = model.encode(input_text)
    return embedding.tolist()
$$;
```
<!-- /code -->

- `snowflake_import_directory`: where `IMPORTS` puts the stage files; the model loads from its `minilm/` once per process.

Check:

```sql
SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.QUERY_NEO4J('RETURN 1 AS ok', OBJECT_CONSTRUCT());  -- [{"ok": 1}]
SELECT ARRAY_SIZE(NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GENERATE_EMBEDDINGS('graph databases'));  -- 384
```

## 9. Tool functions

An agent calls functions, not Cypher. Each of these fixes one query and exposes only its parameters.

`GET_ORGANIZATION_INVESTORS(company)`: an organization's investors, one `HAS_INVESTOR` hop.

<!-- code: GET_ORGANIZATION_INVESTORS_SQL -->
```sql
CREATE OR REPLACE FUNCTION NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GET_ORGANIZATION_INVESTORS(COMPANY VARCHAR)
RETURNS VARIANT
COMMENT = 'Returns investors for a given organization'
AS $$
NEO4J_AGENT.NEO4J_AGENT_SCHEMA.QUERY_NEO4J(
    'MATCH (o:Organization {name: $company})
     RETURN o.name as name,
            [(o)-[:HAS_INVESTOR]->(p:Person) | p.name] as investor
     LIMIT 1',
    {'company': COMPANY}
)
$$;
```
<!-- /code -->

`ANALYZE_RELATIONSHIPS(company, limit, max_depth)`: organizations within `max_depth` hops, with the relationship chain and distance.

<!-- code: ANALYZE_RELATIONSHIPS_SQL -->
```sql
CREATE OR REPLACE FUNCTION NEO4J_AGENT.NEO4J_AGENT_SCHEMA.ANALYZE_RELATIONSHIPS(COMPANY VARCHAR, "LIMIT" NUMBER DEFAULT 20, MAX_DEPTH INT DEFAULT 2)
RETURNS VARIANT
COMMENT = 'Analyzes relationship paths between organizations'
AS $$
NEO4J_AGENT.NEO4J_AGENT_SCHEMA.QUERY_NEO4J(
    CONCAT('MATCH path = (o1:Organization {name: $company})-[]-{1,', MAX_DEPTH, '}(o2:Organization)
    WHERE o1 <> o2
    RETURN DISTINCT o2.name as organization,
           [r in relationships(path) | type(r)] as relationships,
           length(path) as distance
    ORDER BY distance
    LIMIT $limit'),
    {'company': COMPANY, 'limit': "LIMIT"}
)
$$;
```
<!-- /code -->

- `-[]-{1,n}`: a quantified path pattern, any relationship, either direction, up to `MAX_DEPTH` hops. `CONCAT` writes the bound into the query: Cypher takes no parameter there.
- `"LIMIT"`: a reserved word, so quoted in the signature and wherever used. The agent still calls it `limit`.

`SEARCH_NEWS_ARTICLES(company, query, limit)`: the company's news chunks, ranked by similarity to `query`.

<!-- code: SEARCH_NEWS_ARTICLES_SQL -->
```sql
CREATE OR REPLACE FUNCTION NEO4J_AGENT.NEO4J_AGENT_SCHEMA.SEARCH_NEWS_ARTICLES(COMPANY VARCHAR, QUERY VARCHAR, "LIMIT" NUMBER DEFAULT 20)
RETURNS VARIANT
COMMENT = 'Find news about the given <company> that has content about the given <query>'
AS $$
NEO4J_AGENT.NEO4J_AGENT_SCHEMA.QUERY_NEO4J('
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)-[:HAS_CHUNK]->(c:Chunk)
    WHERE c.embedding_sbert IS NOT NULL
    WITH DISTINCT a, c, vector.similarity.cosine(c.embedding_sbert, $embedding) AS score
    RETURN a.title as title,
           a.date as date,
           c.text as text,
           score
    ORDER BY score DESC
    LIMIT $limit',
    {
      'company': COMPANY,
      'limit': "LIMIT",
      'embedding': NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GENERATE_EMBEDDINGS(QUERY)
    })
$$;
```
<!-- /code -->

- The graph narrows the search to chunks of articles that `MENTIONS` the company; `vector.similarity.cosine` ranks them against `GENERATE_EMBEDDINGS(QUERY)`.

Check the chain from Snowflake to Neo4j:

<!-- code: SMOKE_TEST_SQL -->
```sql
SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GET_ORGANIZATION_INVESTORS('Neo4j') AS investors;
```
<!-- /code -->

```sql
-- [{"investor": ["Rod Johnson"], "name": "Neo4j"}]
SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.ANALYZE_RELATIONSHIPS('Neo4j', 5, 2);
-- [{"distance": 1, "organization": "Adobe", "relationships": ["HAS_SUPPLIER"]}, ...]
SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.SEARCH_NEWS_ARTICLES('Neo4j', 'funding', 2);
-- [{"date": ..., "score": 0.61, "text": ..., "title": ...}, ...]
```

## 10. Agent

1. **AI & ML > Agents > Create agent**.
2. Database and schema `NEO4J_AGENT.NEO4J_AGENT_SCHEMA`, agent object name `NEO4J_RESEARCH_AGENT` (part of the REST URL), display name `Neo4j research agent`, **Create agent**.
3. **Configuration > Instructions**: leave **Model** on `auto`. It picks the tool and its arguments and writes the answer.

The agent stays a draft until you publish it (step 12).

## 11. Tools

The agent picks a tool by its description alone: enter the texts below as they are.

For each tool, **Configuration > Tools > Custom tools > + Add**:

1. **Resource type** `function` (default: procedure).
2. **Database & Schema** `NEO4J_AGENT.NEO4J_AGENT_SCHEMA`, then **Custom tool identifier**: this pre-fills one parameter row per argument.
3. **Name** and **Description** from its section below; **Warehouse** stays **User's default**; **Query timeout** `60`.
4. A description per parameter; untick **Required** where marked. The SQL defaults then apply.
5. **Add**.

When all three are added: **Save** (saves the draft).

![Add custom tool dialog: resource type function, database, schema and identifier](images/custom-tool.png)

### `get_organization_investors` (identifier `GET_ORGANIZATION_INVESTORS`)

<!-- code: tool:get_organization_investors -->
```text
Returns the investors for a given company name from the Neo4j database. Accepts a company name and returns the
company and its investors as an array.

USAGE SCENARIOS:
- Retrieving investor information for company profile pages or reports
- Performing due diligence research on company ownership and investment relationships
- Supporting automated investor relationship mapping and analysis workflows
```
<!-- /code -->

<!-- text: params:get_organization_investors -->
- `company`: The name of the company
<!-- /text -->

### `analyze_relationships` (identifier `ANALYZE_RELATIONSHIPS`)

<!-- code: tool:analyze_relationships -->
```text
Analyzes relationship paths between organizations in the Neo4j database.
Accepts a company name, limit, and max_depth, and returns related organizations, relationship types, and path distances.

USAGE SCENARIOS:
- Mapping organizational networks
- Exploring indirect connections between companies
- Supporting due diligence and risk analysis
```
<!-- /code -->

<!-- text: params:analyze_relationships -->
- `company`: The name of the company
- `limit`: Maximum number of results to return (untick **Required**)
- `max_depth`: Maximum path length to search (untick **Required**)
<!-- /text -->

### `search_news_articles` (identifier `SEARCH_NEWS_ARTICLES`)

<!-- code: tool:search_news_articles -->
```text
Finds news articles about a given company that are relevant to a provided query, using semantic search over article content.

USAGE SCENARIOS:
- Retrieving news coverage for a company filtered by topic
- Supporting research and media monitoring workflows
```
<!-- /code -->

<!-- text: params:search_news_articles -->
- `company`: The name of the company
- `query`: The search query or topic
- `limit`: Maximum number of articles to return (untick **Required**)
<!-- /text -->

## 12. Publish

1. **Publish**, confirm with **Publish**. Apps and the REST API use the published version.
2. Let `USER` use the agent: agent tab **Access**, or in SQL:

```sql
GRANT USAGE ON AGENT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_RESEARCH_AGENT TO ROLE "USER";
SHOW AGENTS IN SCHEMA NEO4J_AGENT.NEO4J_AGENT_SCHEMA;
```

## 13. Try it

1. Tab **Preview**, ask `Who are the investors of Neo4j?` The answer takes 20 to 40 seconds and names **Rod Johnson**.
2. Hover the icon under the answer until **Show Traces** appears, click it, select the **Custom Tool** span:
   - **Name**: `get_organization_investors`
   - **Input > Arguments**: `company: "Neo4j"`, taken from the question
   - **Output > Results > Raw Results**: the record from the smoke test in step 9

![Trace of the Custom Tool span: tool name, arguments and raw result](images/trace.png)

More questions: `What organizations are connected to Neo4j through indirect relationships?`, `What recent news is there about Neo4j's funding?`. To check the grants, switch to role `USER` (account menu, **Switch role**) and ask again.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `USER` missing from a role picker | Role list cached: reload Snowsight |
| Function missing from **Custom tool identifier** | Object list cached: reload the page, reopen the dialog |
| `{"error": "Could not resolve Neo4j address: ..."}` | Network rule or integration: host must match the URI in `QUERY_NEO4J` |
| `{"error": "Neo4j query failed: ..."}` with an auth message | Secret: username or password |
| `GENERATE_EMBEDDINGS` fails to load the model | Files missing on the stage, or uploaded gzipped |

`QUERY_NEO4J` returns errors as `{"error": ...}` values, not as SQL errors.

## Clean up

<!-- code: CLEANUP_SQL -->
```sql
DROP DATABASE IF EXISTS NEO4J_AGENT CASCADE;
DROP INTEGRATION IF EXISTS NEO4J_ACCESS_INTEGRATION;
DROP ROLE IF EXISTS "USER";
```
<!-- /code -->
