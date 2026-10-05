// What the screencast builds. Its own database keeps it apart from sample 2,
// whose cleanup drops NEO4J_AGENT.

// Every SQL step uses this worksheet. The first run creates it.
export const WORKSHEET_NAME = 'aura-mcp.sql'

export const DATABASE = 'NEO4J_MCP'
export const SCHEMA = 'PUBLIC'
export const FQ_SCHEMA = `${DATABASE}.${SCHEMA}`
export const INTEGRATION = 'NEO4J_AURA_MCP_INTEGRATION'
export const MCP_SERVER = 'NEO4J_AURA_MCP'
// CoWork and Agent Studio list the server under this name.
export const MCP_SERVER_DISPLAY_NAME = 'Neo4j Aura'
export const AGENT_NAME = 'NEO4J_MOVIES_AGENT'
export const AGENT_DISPLAY_NAME = 'Neo4j movies agent'
// Needs get-schema, then read-cypher over ACTED_IN and DIRECTED.
export const AGENT_QUESTION = 'Which actors have worked with the most different directors?'

// The guide shows this placeholder; the recording uses AURA_MCP_URL from .env.
export const MCP_URL_PLACEHOLDER = 'https://<INSTANCE_ID>.mcp-instances.neo4j.io'

/** Drops everything the screencast creates. One statement per entry. */
export const CLEANUP_STATEMENTS = [
    `DROP DATABASE IF EXISTS ${DATABASE} CASCADE;`,
    `DROP INTEGRATION IF EXISTS ${INTEGRATION};`,
]

export const DATABASE_SQL = `CREATE DATABASE ${DATABASE};`

// Snowflake reads the protected-resource metadata at OAUTH_RESOURCE_URL, finds
// Aura's authorization server and registers itself there (DCR).
export const integrationSql = (mcpUrl: string) => `\
CREATE API INTEGRATION ${INTEGRATION}
  API_PROVIDER = external_mcp
  API_ALLOWED_PREFIXES = ('${mcpUrl}')
  API_USER_AUTHENTICATION = (
    TYPE = OAUTH_DYNAMIC_CLIENT,
    OAUTH_RESOURCE_URL = '${mcpUrl}'
  )
  ENABLED = TRUE;`

export const mcpServerSql = (mcpUrl: string) => `\
CREATE EXTERNAL MCP SERVER ${FQ_SCHEMA}.${MCP_SERVER}
  WITH DISPLAY_NAME = '${MCP_SERVER_DISPLAY_NAME}'
  URL = '${mcpUrl}'
  API_INTEGRATION = ${INTEGRATION};`

// Not recorded: the screencast runs as ACCOUNTADMIN. What another role needs
// to use the agent; checked with a test role, which sees the agent from the
// first four and the MCP server from the fifth. The integration is for the
// connector's sign-in.
export const grantSql = (role: string, warehouse: string) => `\
GRANT USAGE ON DATABASE ${DATABASE} TO ROLE ${role};
GRANT USAGE ON SCHEMA ${FQ_SCHEMA} TO ROLE ${role};
GRANT USAGE ON WAREHOUSE ${warehouse} TO ROLE ${role};
GRANT USAGE ON AGENT ${FQ_SCHEMA}.${AGENT_NAME} TO ROLE ${role};
GRANT USAGE ON EXTERNAL MCP SERVER ${FQ_SCHEMA}.${MCP_SERVER} TO ROLE ${role};
GRANT USAGE ON INTEGRATION ${INTEGRATION} TO ROLE ${role};`
