// What the screencast builds. Bodies, tool texts, the model and the cleanup
// come from ../shared/, as in Terraform. Names and function settings mirror
// samples/1-terraform/*.tf, which stays plain HCL.
import fs from 'node:fs'
import path from 'node:path'
import {parse as parseYaml} from 'yaml'

const SHARED_DIR = path.resolve(import.meta.dirname, '../shared')
const shared = (...parts: string[]) => fs.readFileSync(path.join(SHARED_DIR, ...parts), 'utf8').trimEnd()

// Every SQL step uses this worksheet. The first run creates it.
export const WORKSHEET_NAME = 'showcase.sql'

// These match database_name in variables.tf and the schema in main.tf.
export const DATABASE = 'NEO4J_AGENT'
export const SCHEMA = 'NEO4J_AGENT_SCHEMA'
export const FQ_SCHEMA = `${DATABASE}.${SCHEMA}`
// End users get this role. It mirrors snowflake_account_role.user in iam.tf.
export const ROLE_NAME = 'USER'
// These match agent.tf.
export const AGENT_NAME = 'NEO4J_RESEARCH_AGENT'
export const AGENT_DISPLAY_NAME = 'Neo4j research agent'
// The agent needs customer_accounts (health), then get_organization_investors
// per Red account. The answer names Cloudera's and VMware's investors.
export const AGENT_QUESTION = 'Who are the investors of our accounts in Red health?'
// The agent needs customer_accounts (renewals) and query_neo4j (competitors).
// The answer names Slack (Workday, Inc.) and Cloudera (Docker).
export const AGENT_JOIN_QUESTION = 'Which of our accounts renewing in the next 45 days compete with another of our accounts?'

/** Drops everything the screencast creates. cleanup.py runs it too. One statement per entry. */
export const CLEANUP_STATEMENTS = shared('sql', 'cleanup.sql').split('\n').filter((l) => l.trim())

// These match neo4j_access.tf.
export const SECRET_SQL = `\
CREATE OR REPLACE SECRET ${FQ_SCHEMA}.NEO4J_CREDENTIALS
  TYPE     = PASSWORD
  USERNAME = 'companies'
  PASSWORD = 'companies';`

export const INTEGRATION_SQL = `\
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION NEO4J_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES          = (${FQ_SCHEMA}.NEO4J_ACCESS_RULE)
  ALLOWED_AUTHENTICATION_SECRETS = (${FQ_SCHEMA}.NEO4J_CREDENTIALS)
  ENABLED                        = TRUE;`

// Shared by both Python UDFs, like `local.python_udf_common` in functions.tf.
// The MODEL_STAGE import makes the sentence-transformer files visible to the UDF.
const pythonUdfOptions = `\
LANGUAGE PYTHON
RUNTIME_VERSION = 3.13
PACKAGES = ('neo4j', 'sentence-transformers')
IMPORTS  = ('@${FQ_SCHEMA}.MODEL_STAGE/minilm/')
EXTERNAL_ACCESS_INTEGRATIONS = (NEO4J_ACCESS_INTEGRATION)
SECRETS = ('cred' = ${FQ_SCHEMA}.NEO4J_CREDENTIALS)`

export const QUERY_NEO4J_SQL = `\
CREATE OR REPLACE FUNCTION ${FQ_SCHEMA}.QUERY_NEO4J(CYPHER VARCHAR, PARAMS OBJECT DEFAULT {})
RETURNS VARIANT
${pythonUdfOptions}
HANDLER = 'query_neo4j'
COMMENT = 'Executes a read-only Cypher query against the Neo4j database'
AS $$
${shared('functions', 'query_neo4j.py')}
$$;`

export const GENERATE_EMBEDDINGS_SQL = `\
CREATE OR REPLACE FUNCTION ${FQ_SCHEMA}.GENERATE_EMBEDDINGS(INPUT_TEXT VARCHAR)
RETURNS VARIANT
${pythonUdfOptions}
HANDLER = 'generate_embeddings'
COMMENT = 'Embedding function using sentence transformers'
AS $$
${shared('functions', 'generate_embeddings.py')}
$$;`

// Bodies of the SQL functions the agent calls as tools. `LIMIT` is a reserved
// word, so it is double-quoted. The Terraform provider quotes it itself.
const sqlBody = (file: string) => shared('sql', file)
    .replaceAll('${query_neo4j}', `${FQ_SCHEMA}.QUERY_NEO4J`)
    .replaceAll('${generate_embeddings}', `${FQ_SCHEMA}.GENERATE_EMBEDDINGS`)
    .replaceAll('${customer_accounts}', `${FQ_SCHEMA}.CUSTOMER_ACCOUNTS`)
    .replaceAll("'limit': LIMIT", `'limit': "LIMIT"`)

export const FIND_ORGANIZATIONS_SQL = `\
CREATE OR REPLACE FUNCTION ${FQ_SCHEMA}.FIND_ORGANIZATIONS(NAME VARCHAR)
RETURNS VARIANT
COMMENT = 'Finds organizations by name; returns their ids'
AS $$
${sqlBody('find_organizations.sql')}
$$;`

export const GET_ORGANIZATION_INVESTORS_SQL = `\
CREATE OR REPLACE FUNCTION ${FQ_SCHEMA}.GET_ORGANIZATION_INVESTORS(ORGANIZATION_ID VARCHAR)
RETURNS VARIANT
COMMENT = 'Returns investors for a given organization'
AS $$
${sqlBody('get_organization_investors.sql')}
$$;`

export const ANALYZE_RELATIONSHIPS_SQL = `\
CREATE OR REPLACE FUNCTION ${FQ_SCHEMA}.ANALYZE_RELATIONSHIPS(ORGANIZATION_ID VARCHAR, "LIMIT" NUMBER DEFAULT 20, MAX_DEPTH INT DEFAULT 2)
RETURNS VARIANT
COMMENT = 'Analyzes relationship paths between organizations'
AS $$
${sqlBody('analyze_relationships.sql')}
$$;`

export const SEARCH_NEWS_ARTICLES_SQL = `\
CREATE OR REPLACE FUNCTION ${FQ_SCHEMA}.SEARCH_NEWS_ARTICLES(ORGANIZATION_ID VARCHAR, TOPIC VARCHAR, "LIMIT" NUMBER DEFAULT 20)
RETURNS VARIANT
COMMENT = 'Finds news about an organization that has content about the given topic'
AS $$
${sqlBody('search_news_articles.sql')}
$$;`

// This matches snowflake_view.customer_accounts in accounts.tf.
export const CUSTOMER_ACCOUNTS_SQL = `\
CREATE OR REPLACE VIEW ${FQ_SCHEMA}.CUSTOMER_ACCOUNTS
COMMENT = 'Sample CRM accounts; ORGANIZATION_ID is Organization.id in Neo4j'
AS
${sqlBody('customer_accounts.sql')};`

// This matches snowflake_semantic_view.customer_accounts and its grant in accounts.tf.
export const SEMANTIC_VIEW = 'CUSTOMER_ACCOUNTS_SV'
export const CUSTOMER_ACCOUNTS_SV_SQL = `\
CREATE OR REPLACE SEMANTIC VIEW ${FQ_SCHEMA}.${SEMANTIC_VIEW}
  ${sqlBody('customer_accounts_semantic_view.sql')}
  COMMENT = 'Customer accounts for Cortex Analyst';`

// A separate statement, because the editor runs one at a time. The guide shows
// it under the semantic view.
export const SEMANTIC_VIEW_GRANT_SQL = `GRANT SELECT ON SEMANTIC VIEW ${FQ_SCHEMA}.${SEMANTIC_VIEW} TO ROLE "${ROLE_NAME}";`

export const SMOKE_TEST_SQL = `SELECT ${FQ_SCHEMA}.FIND_ORGANIZATIONS('Neo4j') AS organizations;`

// The embedding UDF's model. Snowsight's upload dialog takes one folder per
// pass, so Terraform's layout is rebuilt folder by folder. Empty folders such
// as `2_Normalize/` are skipped.
const MODEL_DIR = path.join(SHARED_DIR, 'model', 'minilm')
const filesIn = (dir: string) => fs.readdirSync(dir, {withFileTypes: true})
    .filter((e) => e.isFile())
    .map((e) => e.name)
    .sort((a, b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1)
    .map((name) => path.join(dir, name))

// Read on use, because the model is gitignored and readme.ts in CI never needs it.
export function modelFiles() {
    if (!fs.existsSync(MODEL_DIR)) throw new Error(`${MODEL_DIR} missing; the Terraform sample downloads it`)
    return {
        root: filesIn(MODEL_DIR),
        subfolders: fs.readdirSync(MODEL_DIR, {withFileTypes: true})
            .filter((e) => e.isDirectory())
            .map((e) => ({stagePath: `minilm/${e.name}`, files: filesIn(path.join(MODEL_DIR, e.name))}))
            .filter((folder) => folder.files.length > 0),
    }
}

// Read from the agent spec that Terraform deploys. A parameter outside
// `required` gets an unticked "Required" box, and the SQL default applies.
export type ToolParam = {name: string, description: string, required: boolean}
export type AgentToolSpec = {
    name: string,
    /** The SQL function in the tool dialog's identifier list */
    identifier: RegExp,
    description: string,
    params: ToolParam[],
}

type AgentSpec = {
    instructions: {orchestration: string},
    tools: {tool_spec: {
        name: string,
        type: string,
        description: string,
        input_schema?: {properties: Record<string, {description: string}>, required?: string[]},
    }}[],
}

const AGENT_SPEC = parseYaml(shared('agent', 'agent_spec.yaml.tftpl')) as AgentSpec

export const AGENT_ORCHESTRATION_INSTRUCTIONS = AGENT_SPEC.instructions.orchestration.trimEnd()

// Custom tools, one per SQL function or UDF.
export const AGENT_TOOL_SPECS: AgentToolSpec[] = AGENT_SPEC.tools
    .map(({tool_spec: t}) => t)
    .filter((t) => t.type === 'generic')
    .map((t) => ({
        name: t.name,
        // Dropdown options read '<DB>.<SCHEMA>.<NAME>(<argument types>)'.
        identifier: new RegExp(`\\.${t.name.toUpperCase()}\\(`),
        description: t.description.trimEnd(),
        params: Object.entries(t.input_schema?.properties ?? {}).map(([name, p]) => ({
            name,
            description: p.description,
            required: t.input_schema?.required?.includes(name) ?? false,
        })),
    }))

// The Cortex Analyst tool over the semantic view.
const analyst = AGENT_SPEC.tools.map(({tool_spec: t}) => t).find((t) => t.type === 'cortex_analyst_text_to_sql')
if (!analyst) throw new Error('agent spec has no cortex_analyst_text_to_sql tool')
export const ANALYST_TOOL = {name: analyst.name, description: analyst.description.trimEnd()}
