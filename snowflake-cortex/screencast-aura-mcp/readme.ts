// Fills the marked code blocks of sample 3's hand-written README from
// stack.ts, the source the screencast runs. `--check` only verifies.
import path from 'node:path'
import {syncCodeBlocksCli} from '../../tools/screencast/sync-readme.ts'
import * as stack from './stack.ts'

syncCodeBlocksCli(path.resolve(import.meta.dirname, '../samples/3-aura-mcp/README.md'), {
    DATABASE_SQL: stack.DATABASE_SQL,
    INTEGRATION_SQL: stack.integrationSql(stack.MCP_URL_PLACEHOLDER),
    MCP_SERVER_SQL: stack.mcpServerSql(stack.MCP_URL_PLACEHOLDER),
    GRANT_SQL: stack.grantSql('<ROLE>', '<WAREHOUSE>'),
    CLEANUP_SQL: stack.CLEANUP_STATEMENTS.join('\n'),
    AGENT_QUESTION: stack.AGENT_QUESTION,
})
