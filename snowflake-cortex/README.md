# Snowflake Cortex Agents + Neo4j Integration

A Cortex agent that researches companies in the Neo4j `companies` demo graph
(`neo4j+s://demo.neo4jlabs.com:7687`) through Python UDFs and SQL wrapper functions.

- [Cortex Agents documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)

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

- `QUERY_NEO4J` connects to Neo4j with credentials from a Snowflake secret,
  through an external access integration.
- `GENERATE_EMBEDDINGS` loads `all-MiniLM-L6-v2` from an internal stage; its
  vector is what `SEARCH_NEWS_ARTICLES` scores the company's news chunks
  against with `vector.similarity.cosine`.
- The agent spec (`shared/agent/agent_spec.yaml.tftpl`) exposes the three SQL
  functions as tools.

## Samples

| Sample | What |
| --- | --- |
| [1-terraform](samples/1-terraform/README.md) | Provisions the whole stack with Terraform |
| [2-snowsight](samples/2-snowsight/README.md) | Builds the same stack by hand in Snowsight |

Both use the same Python handlers, SQL bodies and agent tools from `shared/`.

Sample 2 as a video:

[![Watch the video](https://img.youtube.com/vi/QWc3SBc5sUE/maxresdefault.jpg)](https://youtu.be/QWc3SBc5sUE)

## Repository layout

```
snowflake-cortex/
├── shared/                  # used by all samples
│   ├── functions/           # Python UDF handlers
│   ├── sql/                 # SQL wrapper bodies (agent tools)
│   ├── agent/               # agent spec template
│   └── model/minilm/        # all-MiniLM-L6-v2 files (downloaded, gitignored)
└── samples/
    ├── 1-terraform/         # Terraform config, bootstrap SQL
    └── 2-snowsight/         # Snowsight guide, screenshots
```

## Running the agent

The agent is `NEO4J_AGENT.NEO4J_AGENT_SCHEMA.NEO4J_RESEARCH_AGENT`, callable from
Snowsight or the Cortex Agents REST API. Its tools also work as plain SQL functions:

```sql
SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.GET_ORGANIZATION_INVESTORS('Uniphore');

SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.ANALYZE_RELATIONSHIPS('Uniphore', 10, 2);

SELECT NEO4J_AGENT.NEO4J_AGENT_SCHEMA.SEARCH_NEWS_ARTICLES('Uniphore', 'Roberto Pieraccini', 3);
```
