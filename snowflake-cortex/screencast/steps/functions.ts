// Steps 7-9: the model stage, the Python UDFs and the SQL functions the agent calls.
import {test} from '@playwright/test'
import {click, narrate} from 'playwright-recast'
import {zoomDialog} from '../../../tools/screencast/narration.ts'
import {catalogRow, listLoaded, openDatabases} from '../snowsight/catalog.ts'
import {explainCode, fitResultsPane, openOrCreateWorksheet, runSelected} from '../snowsight/workspace.ts'
import {startStageUpload} from '../snowsight/stage.ts'
import {ANALYZE_RELATIONSHIPS_SQL, CUSTOMER_ACCOUNTS_SQL, CUSTOMER_ACCOUNTS_SV_SQL, DATABASE, FIND_ORGANIZATIONS_SQL, GENERATE_EMBEDDINGS_SQL, GET_ORGANIZATION_INVESTORS_SQL, modelFiles, QUERY_NEO4J_SQL, SCHEMA, SEARCH_NEWS_ARTICLES_SQL, SEMANTIC_VIEW_GRANT_SQL, SMOKE_TEST_SQL, WORKSHEET_NAME} from '../stack.ts'
import type {Ctx} from './context.ts'

export async function createModelStage(ctx: Ctx) {
    const {page, step, say, narrateDuring, fill, shot} = ctx
    await step("7. create model stage + upload model (UI)", async () => {
        // The ~90MB upload takes 5-6 minutes, and the `step` wrapper extends the
        // timeout only after a step ends. Running out here would kill the run at
        // its most expensive point, so the budget is generous.
        test.setTimeout(test.info().timeout + 15 * 60_000)

        await say(
            "Our Neo4j instance already stores embeddings alongside the news articles, and those were generated " +
            "with a SentenceTransformer model. To search them we have to embed the incoming query with exactly " +
            "that same model, so the model has to be available inside Snowflake as well.",
        )
        await narrateDuring("To hold the model, we create an internal stage inside our schema.", async () => {
            await openDatabases(page)
            await click(catalogRow(page, 'Database', DATABASE))
            await click(catalogRow(page, 'Schema', SCHEMA))
            await listLoaded(page)
        })
        const stageDialog = page.getByRole('dialog', {name: /Create Stage/})
        await narrateDuring("The create menu offers a stage.", async () => {
            // The submenu's entries render as menuitems or options.
            await click(page.getByRole('button', {name: 'Create', exact: true}))
            await click(page.getByRole('menuitem', {name: 'Stage', exact: true}))
            await click(page.getByRole('menuitem', {name: /Snowflake Managed/})
                .or(page.getByRole('option', {name: /Snowflake Managed/})).first())
            await stageDialog.waitFor({timeout: 30_000})
        })
        await zoomDialog(page, stageDialog)
        await narrateDuring("We'll name it MODEL_STAGE and turn on client-side encryption.", async () => {
            await fill(stageDialog.getByRole('textbox', {name: 'Stage Name'}), 'MODEL_STAGE')
            // Encryption has no default, and Create stays disabled until one is
            // picked. Client-side is terraform's `snowflake_full {}`; the directory
            // table is on by default, like `directory { enable = true }`.
            await click(stageDialog.getByRole('radio', {name: /Client-side encryption/}))
            // The dialog element spans the whole viewport; its content bounds the shot.
            await shot([
                stageDialog.getByText('Create Stage', {exact: true}),
                stageDialog.getByRole('textbox', {name: 'Stage Name'}),
                stageDialog.getByRole('button', {name: 'Create', exact: true}),
            ], 'create-stage')
        })
        await click(stageDialog.getByRole('button', {name: 'Create', exact: true}))
        await stageDialog.waitFor({state: 'hidden', timeout: 60_000})


        // Creating the stage lands on its file view. One upload pass per folder
        // keeps the model's nested layout; only the first is on screen.
        const rootUpload = (await narrateDuring(
            "Now we upload the model files straight from the browser.",
            () => startStageUpload(page, modelFiles().root, 'minilm', {
                // The modal element spans the whole viewport; its content bounds the shot.
                beforeUpload: (modal) => shot([
                    modal.getByText('Upload Your Files', {exact: true}),
                    modal.getByRole('textbox', {name: 'stage path input'}),
                    modal.getByRole('button', {name: 'Upload', exact: true}),
                ], 'upload-files'),
            }),
        ))!

        // Hidden because it is dead air: the transfer, then a stage view that
        // stays busy for half a minute before it accepts the next upload.
        await test.step('hidden - upload the model files', async () => {
            await rootUpload.waitFor({state: 'hidden', timeout: 10 * 60_000})
            for (const folder of modelFiles().subfolders) {
                const upload = await startStageUpload(page, folder.files, folder.stagePath, {quiet: true})
                await upload.waitFor({state: 'hidden', timeout: 5 * 60_000})
            }
            // Let the directory listing catch up, so the shot after the cut
            // shows the files rather than an empty stage.
            await page.getByText('model.safetensors').first()
                .waitFor({timeout: 5 * 60_000})
                .catch(() => {/* listing renders lazily; the next line still holds */})
        })

        await say(
            "The model now lives on the stage, ready for the embedding function to use it.",
        )
        await narrate(undefined)
    })
}

export async function createPythonUdfs(ctx: Ctx) {
    const {page, ws, editor, step, narrateDuring, introduce} = ctx
    await step("8. create the Python UDFs (SQL)", async () => {
        // Snowflake compiles the environment for a Python UDF at creation time
        // (neo4j + sentence-transformers), which takes a minute per function.
        test.setTimeout(test.info().timeout + 6 * 60_000)

        await narrateDuring(
            "Snowsight's Catalog can create functions, but it only drops a SQL template into a workspace - " +
            "so both Python user-defined functions are written as SQL.",
            async () => {
                await page.getByRole('link', {name: 'Projects', exact: true}).click()
                await openOrCreateWorksheet(page, ws, WORKSHEET_NAME)
            },
        )

        // Normally done by the previous step; repeated for an ONLY_STEPS run that
        // starts here, since this is the statement that needs the room.
        await test.step('hidden - fit the results pane', () => fitResultsPane(page, ws))

        await introduce(QUERY_NEO4J_SQL,
            "The first user-defined function is the bridge to Neo4j. It is a Python function running inside Snowflake, " +
            "and its header is where all the pieces we just built come together.",
        )

        await explainCode(page, ws, [
            {
                match: 'PARAMS OBJECT DEFAULT {}',
                text: "The parameters are optional, so the agent can also call this function with nothing but a " +
                    "Cypher query. We'll use that later.",
            },
            {
                match: "IMPORTS  = ('@",
                text: "The imports line mounts the model stage into the function's file system.",
            },
            {
                match: 'EXTERNAL_ACCESS_INTEGRATIONS',
                text: "The integration is what allows this function to open a connection to the outside world at all.",
            },
            {
                match: "SECRETS = ('cred'",
                text: "And the secret is handed to it under the name cred.",
            },
            {
                match: 'get_username_password',
                text: "At runtime the code asks Snowflake for that secret. The credentials never appear in the source.",
            },
            {
                match: 'neo4j+s://',
                text: "With them it opens an encrypted Neo4j driver against the demo database, once, and keeps " +
                    "it for every later call.",
            },
            {
                match: 'routing_=RoutingControl.READ',
                text: "Every query runs in read mode, so Neo4j itself refuses any write.",
            },
            {
                match: 'if DENIED.search(cypher)',
                text: "Before that, two checks. A deny list stops calls that reach beyond the graph, like loading " +
                    "files or URLs.",
            },
            {
                match: 'execute("EXPLAIN "',
                text: "And EXPLAIN lets Neo4j classify the query without running it: anything but a read is " +
                    "turned away.",
            },
            {
                match: 'records, summary, keys = execute(cypher, params)',
                text: "Only then does it run the Cypher and hand the records back to Snowflake as a variant. A " +
                    "rejection comes back as an error value, which an agent can read and fix its query by.",
            },
        ])

        await narrate(
            "Creating a Python user-defined function also builds its package environment, so this one takes some time.",
        )
        await runSelected(page, ws, editor)

        await introduce(GENERATE_EMBEDDINGS_SQL,
            "The second one loads the Mini-LM model from the stage and turns text into an embedding vector.",
        )
        await explainCode(page, ws, [
            {
                match: 'RUNTIME_VERSION',
                text: "Its header matches the bridge function exactly: the same runtime, packages and imports, " +
                    "and the same secret and integration. With identical settings, Snowflake can reuse one Python " +
                    "runtime in the warehouse for both functions.",
            },
            {
                match: "IMPORTS  = ('@",
                text: "The imports line mounts the model stage here as well, so the Mini-LM files sit right in the " +
                    "function's file system.",
            },
            {
                match: 'snowflake_import_directory',
                text: "It reads the model straight out of the stage directory that the imports line mounted, " +
                    "and keeps it cached between calls.",
            },
            {
                match: 'def generate_embeddings',
                text: "Snowflake hands the function's one argument, INPUT_TEXT, to this handler by position, so " +
                    "it arrives here as input_text.",
            },
        ])
        await runSelected(page, ws, editor)
        await narrate(undefined)
    })
}

export async function createToolFunctions(ctx: Ctx) {
    const {page, ws, editor, step, say, introduce} = ctx
    await step("9. create the agent tool functions (SQL)", async () => {
        test.setTimeout(test.info().timeout + 9 * 60_000)

        await say(
            "On top of those two user-defined functions we define small SQL functions, each wrapping one fixed " +
            "Cypher query. These are what the agent gets as tools, and it can only ask what we planned for, " +
            "which keeps it predictable. They all identify organizations by their id: names repeat in this " +
            "graph, ids don't, and the id is indexed.",
        )

        await introduce(FIND_ORGANIZATIONS_SQL,
            "The first one turns a company name from a question into ids.",
        )
        await explainCode(page, ws, [
            {
                match: 'CONTAINS toLower($name)',
                text: "It matches the name loosely ...",
            },
            {
                match: 'o.id as organization_id',
                text: "... and returns each match with its id, a short summary and how connected it is, so the " +
                    "agent can pick the right one.",
            },
        ])
        await runSelected(page, ws, editor)

        await introduce(GET_ORGANIZATION_INVESTORS_SQL,
            "The next one answers who backed a company.",
        )
        await explainCode(page, ws, [
            {
                match: 'MATCH (o:Organization {id: $organization_id})',
                text: "It looks the organization up by its id ...",
            },
            {
                match: 'HAS_INVESTOR',
                text: "... and follows its HAS_INVESTOR relationships, one hop. Investors can be people or other " +
                    "companies, and each comes back with its own id.",
            },
        ])
        await runSelected(page, ws, editor)

        await introduce(ANALYZE_RELATIONSHIPS_SQL,
            "The third one is where a graph really pays off: it looks for how two organizations are connected, " +
            "even when nothing connects them directly.",
        )
        await explainCode(page, ws, [
            {
                match: 'MATCH path =',
                text: "This is a quantified path pattern: it starts at our organization and repeats a single hop, " +
                    "over any relationship in any direction, up to as many times as the caller allows, until it " +
                    "lands on another organization.",
            },
            {
                match: 'relationships(path)',
                text: "And for every organization it finds we get back the chain of relationships that leads " +
                    "there, together with how far away it is, which is something you would really not enjoy " +
                    "writing in SQL.",
            },
        ])
        await runSelected(page, ws, editor)

        await introduce(SEARCH_NEWS_ARTICLES_SQL,
            "The fourth one is the semantic news search, and it is the one that uses both of our Python " +
            "functions at once.",
        )
        await explainCode(page, ws, [
            {
                match: 'GENERATE_EMBEDDINGS(TOPIC)',
                text: "Right here at the bottom, the embedding function turns the topic into a vector with the " +
                    "model we just staged, and that vector goes into the Cypher query as a parameter.",
            },
            {
                match: 'MENTIONS',
                text: "The Cypher first uses the graph to narrow the search to articles that mention this " +
                    "organization, and to their text chunks.",
            },
            {
                match: 'vector.similarity.cosine',
                text: "Then Neo4j scores each of those chunks against the topic's vector and keeps the closest " +
                    "ones. So Snowflake does the embedding, the graph picks the company's news, and Neo4j ranks " +
                    "it by meaning.",
            },
        ])
        await runSelected(page, ws, editor)

        await introduce(SMOKE_TEST_SQL,
            "Let's put the chain to the test, with one query that travels from Snowflake all the way into the graph.",
        )
        // The results grid is a canvas; the row-count chip is the only readable
        // marker of the result.
        await runSelected(page, ws, editor)
        await ws.getByRole('button', {name: /^1 row$/}).waitFor({timeout: 60_000})
        await say("Snowflake asked Neo4j, and Neo4j answered with the organization's id.")

        await introduce(CUSTOMER_ACCOUNTS_SQL,
            "Now for data that lives in Snowflake: a small view of customer accounts, standing in for a CRM table.",
        )
        await explainCode(page, ws, [
            {
                match: 'column2 AS ORGANIZATION_ID',
                text: "Each account carries the id of its organization in the graph. That is what the agent joins " +
                    "on, not the name.",
            },
            {
                match: 'DATEADD(day',
                text: "Renewal dates count from today, so they never go stale.",
            },
        ])
        await runSelected(page, ws, editor)

        await introduce(CUSTOMER_ACCOUNTS_SV_SQL,
            "For the agent to query this data, we don't need a function per table. A semantic view describes it, " +
            "and Cortex Analyst turns the agent's questions into SQL against it.",
        )
        await explainCode(page, ws, [
            {
                match: 'accounts.health AS HEALTH',
                text: "Dimensions name the columns, and their comments tell Analyst what each one means. Nothing " +
                    "here knows about Neo4j: how these ids map to the graph goes into the agent's tool description.",
            },
            {
                match: 'accounts.total_arr',
                text: "A metric, total revenue, lets it answer questions like how much revenue is at risk.",
            },
        ])
        await runSelected(page, ws, editor)
        await introduce(SEMANTIC_VIEW_GRANT_SQL,
            "Our users' role needs read access to the semantic view, and only to it, not to the view underneath.",
        )
        await runSelected(page, ws, editor)

        await narrate(undefined)
    })
}
