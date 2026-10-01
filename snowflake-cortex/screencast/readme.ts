// Fills the marked code blocks of the Snowsight sample's hand-written README
// from stack.ts, the source the screencast runs. `--check` only verifies.
import path from 'node:path'
import {syncCodeBlocksCli} from '../../tools/screencast/sync-readme.ts'
import * as stack from './stack.ts'

syncCodeBlocksCli(path.resolve(import.meta.dirname, '../samples/2-snowsight/README.md'), {
    SECRET_SQL: stack.SECRET_SQL,
    INTEGRATION_SQL: stack.INTEGRATION_SQL,
    QUERY_NEO4J_SQL: stack.QUERY_NEO4J_SQL,
    GENERATE_EMBEDDINGS_SQL: stack.GENERATE_EMBEDDINGS_SQL,
    FIND_ORGANIZATIONS_SQL: stack.FIND_ORGANIZATIONS_SQL,
    GET_ORGANIZATION_INVESTORS_SQL: stack.GET_ORGANIZATION_INVESTORS_SQL,
    ANALYZE_RELATIONSHIPS_SQL: stack.ANALYZE_RELATIONSHIPS_SQL,
    SEARCH_NEWS_ARTICLES_SQL: stack.SEARCH_NEWS_ARTICLES_SQL,
    CUSTOMER_ACCOUNTS_SQL: stack.CUSTOMER_ACCOUNTS_SQL,
    CUSTOMER_ACCOUNTS_SV_SQL: `${stack.CUSTOMER_ACCOUNTS_SV_SQL}\n\n${stack.SEMANTIC_VIEW_GRANT_SQL}`,
    SMOKE_TEST_SQL: stack.SMOKE_TEST_SQL,
    CLEANUP_SQL: stack.CLEANUP_STATEMENTS.join('\n'),
    'instructions:orchestration': stack.AGENT_ORCHESTRATION_INSTRUCTIONS,
    [`tool:${stack.ANALYST_TOOL.name}`]: stack.ANALYST_TOOL.description,
    ...Object.fromEntries(stack.AGENT_TOOL_SPECS.flatMap((tool) => [
        [`tool:${tool.name}`, tool.description],
        [`params:${tool.name}`, tool.params
            .map((p) => `- \`${p.name}\`: ${p.description}${p.required ? '' : ' (untick **Required**)'}`)
            .join('\n')],
    ])),
})
