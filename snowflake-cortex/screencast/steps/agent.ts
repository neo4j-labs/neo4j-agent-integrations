// Steps 10-13: create the agent, add its tools, publish it, ask it.
import {expect, test, type Locator, type Page} from '@playwright/test'
import {click, narrate, pace, waitForNarration} from 'playwright-recast'
import {zoomDialog} from '../../../tools/screencast/narration.ts'
import {openNavItem, pickDatabaseAndSchema} from '../snowsight/catalog.ts'
import {addAnalystTool, addCustomTool, type AgentTool} from '../snowsight/agent-studio.ts'
import {dismissPopups} from '../snowsight/popups.ts'
import {AGENT_DISPLAY_NAME, AGENT_JOIN_QUESTION, AGENT_NAME, AGENT_ORCHESTRATION_INSTRUCTIONS, AGENT_QUESTION, AGENT_TOOL_SPECS, ANALYST_TOOL, SEMANTIC_VIEW, type AgentToolSpec} from '../stack.ts'
import type {Ctx} from './context.ts'

// Spoken while each tool's dialog is filled in; the tools come from the agent spec.
const TOOL_NARRATION: Record<string, Omit<AgentTool, keyof AgentToolSpec>> = {
    find_organizations: {
        narration:
            "Then the custom tools, one per function. Snowsight reads the function's signature and pre-fills " +
            "its parameters, so all we add is what the agent needs to know about them. First, the name search.",
    },
    get_organization_investors: {
        narration: "Next, the investor lookup.",
    },
    analyze_relationships: {
        narration: "This one walks relationship paths.",
        optionalNarration:
            "Limit and max depth already have defaults in the SQL function, so we leave them optional, and the " +
            "agent only has to supply an organization id.",
    },
    search_news_articles: {
        narration:
            "Then the semantic news search, which embeds the agent's topic before it ever reaches the graph.",
    },
    query_neo4j: {
        narration:
            "And the last one gives the agent the most freedom: our bridge function itself, which runs any " +
            "read-only Cypher the agent writes. Its description carries the graph's schema, and that is all the " +
            "agent knows about the graph when it writes a query.",
        removeNarration:
            "Custom tools can't pass objects, so we remove the parameters argument. The function's default " +
            "applies, and the agent writes the values straight into its Cypher.",
    },
}

// The tool whose dialog the guide's screenshot shows: one with parameter rows.
const SCREENSHOT_TOOL = 'get_organization_investors'

const AGENT_TOOLS: AgentTool[] = AGENT_TOOL_SPECS.map((spec) => {
    const narration = TOOL_NARRATION[spec.name]
    if (!narration) throw new Error(`no narration for tool ${spec.name}`)
    return {...spec, ...narration}
})

export async function createAgent(ctx: Ctx) {
    const {page, step, say, narrateDuring, markAndSay, fill, fillInstantly} = ctx
    await step("10. create the agent (UI)", async () => {
        await say(
            "The user-defined functions are in place, so we can build the agent itself - and when we configure " +
            "it, those same functions are what we register as its tools.",
        )
        const createDialog = page.getByRole('dialog', {name: 'Create agent'})
        await narrateDuring("Agents are built in Agent Studio, so let's head there and create a new one.", async () => {
            await openNavItem(page, 'AI & ML', /^(Agents|Agent Studio)/)
            await click(page.getByRole('button', {name: 'Create agent'}).first())
            await createDialog.waitFor({timeout: 30_000})
        })
        await zoomDialog(page, createDialog)
        await narrateDuring("Like everything else, it lives in our database and schema.", async () => {
            await click(createDialog.getByRole('button', {name: /Database/}))
            await pickDatabaseAndSchema(page)
        })
        await narrateDuring(
            "It gets an object name for SQL, and a friendlier display name for the people who use it.",
            async () => {
                await fill(createDialog.getByRole('textbox', {name: 'Agent object name'}), AGENT_NAME)
                await fill(createDialog.getByRole('textbox', {name: 'Display name'}), AGENT_DISPLAY_NAME)
            },
        )
        // Spoken over the agent-creation round trip, which takes a few seconds.
        await narrate(
            "Creating the agent commits its first version. Everything we configure from here edits a draft, " +
            "until we publish it as the next version.",
        )
        await click(createDialog.getByRole('button', {name: 'Create agent'}))
        await createDialog.waitFor({state: 'hidden', timeout: 60_000})

        // Creating the agent pops the CoCo panel and the "Agent readiness" tour
        // over the tab bar; the tour lands a second or two late.
        await pace(page, 3000)
        await test.step('hidden - dismiss popups', () => dismissPopups(page))
        await click(page.getByRole('tab', {name: 'Configuration'}))

        await narrateDuring(
            "The last piece of configuration is the orchestration model. That is the model doing the actual " +
            "reasoning: it reads the question, decides which of our tools to call and with which arguments, and " +
            "turns the records that come back from Neo4j into an answer.",
            async () => {
                await click(page.getByRole('radio', {name: 'Instructions'}))
                // The mark is measured on this tab; let the recording show
                // the tab before the mark appears.
                await page.getByRole('button', {name: /Model Select/}).waitFor({timeout: 30_000})
                await pace(page, 800)
            },
        )
        await markAndSay(
            page.getByRole('button', {name: /Model Select/}),
            "We leave it on auto and let Snowflake pick a suitable model for us.",
        )
        const orchestration = page.getByRole('textbox', {name: /Orchestration/})
        await narrateDuring(
            "The orchestration instructions tell it how our two sources fit together: each account carries " +
            "the id of its organization in the graph, and that id is what it joins on.",
            async () => {
                await orchestration.scrollIntoViewIfNeeded()
                await fillInstantly(orchestration, AGENT_ORCHESTRATION_INSTRUCTIONS)
            },
        )
        // Step 11 reloads the page, which would drop unsaved instructions.
        await click(page.getByRole('button', {name: 'Save', exact: true}))
        await expect(page.getByRole('button', {name: 'Saved'})).toBeVisible({timeout: 60_000})
        await narrate(undefined)
    })
}

export async function addTools(ctx: Ctx) {
    const {page, step, narrateDuring, markAndSay, fill, fillInstantly, openAgentIfShortened, shot} = ctx
    await step("11. add the tools (UI)", async () => {
        test.setTimeout(test.info().timeout + 6 * 60_000)

        // In the session that created them, the functions never show up in the
        // custom tool identifier dropdown; reloading and reopening fixes that.
        await openAgentIfShortened('Configuration', true)
        await narrateDuring(
            "On the tools tab, we connect the agent to our data. Each tool gets a description in plain language, " +
            "and that description is all the agent has to go by when it decides which tool fits a question.",
            () => click(page.getByRole('radio', {name: 'Tools'})),
        )

        // New agents come with the code execution sandbox on; this agent only
        // needs its own tools, and the sandbox lets it write files.
        const codeExecution = page.getByRole('switch', {name: 'Toggle Code Execution tool'})
        if (await codeExecution.isChecked().catch(() => false)) {
            await markAndSay(codeExecution,
                "New agents come with a code execution sandbox switched on. Our agent doesn't need it, so we " +
                "switch it off.")
            // The input sits under a custom-styled label that takes the clicks.
            await click(codeExecution.locator('xpath=ancestor::label[1]'))
            await expect(codeExecution).not.toBeChecked({timeout: 10_000})
            await pace(page, 800)
        }

        await addAnalystTool(page, {...ANALYST_TOOL, semanticView: SEMANTIC_VIEW}, {fill, fillInstantly}, {
            open: "The first tool reads our customer accounts. Structured data goes in through a semantic view, " +
                "and Cortex Analyst writes the SQL.",
            details: "It gets a name and a description, and runs on the user's default warehouse.",
        })

        for (const tool of AGENT_TOOLS) {
            await narrate(tool.narration)
            await addCustomTool(page, tool, {fill, fillInstantly}, tool.name === SCREENSHOT_TOOL
                ? {onIdentifier: (dialog) => shot(dialog, 'custom-tool')}
                : {})
        }

        await narrate("Saving writes the tool definitions into the draft.")
        await click(page.getByRole('button', {name: 'Save', exact: true}))
        await expect(page.getByRole('button', {name: 'Saved'})).toBeVisible({timeout: 60_000})
        await waitForNarration()
    })
}

export async function publishAgent(ctx: Ctx) {
    const {page, step, narrateDuring, openAgentIfShortened} = ctx
    await step("12. publish the agent (UI)", async () => {
        await openAgentIfShortened()
        const publishDialog = page.getByRole('dialog', {name: 'Publish'})
        await narrateDuring("Our agent is ready, so let's publish it.", async () => {
            await click(page.getByRole('button', {name: 'Publish'}))
            await publishDialog.waitFor({timeout: 30_000})
        })
        await zoomDialog(page, publishDialog)
        await narrateDuring(
            "Publishing commits the draft as a new version, and the latest version is what apps and the REST " +
            "API talk to.",
            async () => {
                await click(publishDialog.getByRole('button', {name: 'Publish'}))
                await publishDialog.waitFor({state: 'hidden', timeout: 60_000})
            },
        )
        await pace(page, 1500)
    })
}

// The answer streams in and the page grows around it (suggestions, buttons):
// mark it only once "Stop" is gone and "Show Traces" works.
async function waitForAnswer(page: Page, text: RegExp): Promise<Locator> {
    const answer = page.getByText(text).last()
    await answer.waitFor({timeout: 4 * 60_000})
    await page.getByRole('button', {name: 'Stop'}).waitFor({state: 'hidden', timeout: 4 * 60_000})
    await expect(page.getByRole('button', {name: 'Show Traces'}).last()).toBeEnabled({timeout: 60_000})
    await pace(page, 1500)
    await answer.scrollIntoViewIfNeeded()
    await pace(page, 500)
    return answer
}

// Opens a trace section, by its index in the span, in fullscreen. Fullscreen
// shows all of it instead of a clipped preview.
async function openFullscreen(page: Page, section: number): Promise<Locator> {
    await click(page.getByRole('button', {name: 'Open in fullscreen'}).nth(section))
    const dialog = page.getByRole('dialog', {name: 'Open in fullscreen'})
    await dialog.waitFor({timeout: 30_000})
    await pace(page, 800)
    return dialog
}

async function closeFullscreen(page: Page, dialog: Locator) {
    await click(dialog.getByRole('button', {name: 'Close dialog'}))
    await dialog.waitFor({state: 'hidden', timeout: 30_000})
    await pace(page, 600)
}

// The Analyst's SQL and what it returned: the SQL Execution span's "SQL
// Query" section, then "SQL Results" in fullscreen.
async function showSqlSpan(page: Page, markAndSay: Ctx['markAndSay'], span: Locator, lines: {sql: string, results: string}) {
    await click(span)
    await pace(page, 1200)
    const sql = page.getByText('SQL Query', {exact: true}).locator('xpath=following::code[1]')
    await sql.scrollIntoViewIfNeeded()
    await markAndSay(sql, lines.sql, {zoom: 1.3})
    const results = await openFullscreen(page, 2)
    await narrate(lines.results)
    await waitForNarration()
    await closeFullscreen(page, results)
}

// Snowsight shows a tool argument as its JSON-encoded string on one clipped
// line (\n, \u003e). For the video only, the open dialog shows it decoded
// and wrapped: same text, readable.
async function showDecodedArgument(dialog: Locator, value: Locator) {
    await value.evaluate((el) => {
        const raw = el.textContent ?? ''
        try {
            el.textContent = JSON.parse(raw)
        } catch {
            return
        }
        Object.assign((el as HTMLElement).style, {
            whiteSpace: 'pre-wrap', overflow: 'visible', textOverflow: 'clip', fontFamily: 'monospace',
        })
    })
    await dialog.page().waitForTimeout(300)
}

export async function askAgent(ctx: Ctx) {
    const {page, step, say, narrateDuring, markAndSay, fill, openAgentIfShortened, shot} = ctx
    await step("13. ask the agent (UI)", async () => {
        test.setTimeout(test.info().timeout + 10 * 60_000)

        await openAgentIfShortened()
        const chatBox = page.getByRole('textbox', {name: 'Chat text area'})
        await narrateDuring("Let's ask it something that needs both Snowflake and the graph.", async () => {
            await click(page.getByRole('tab', {name: 'Preview'}))
            await test.step('hidden - dismiss popups', () => dismissPopups(page))
            await fill(chatBox, AGENT_QUESTION)
        })
        await click(page.getByRole('button', {name: 'Send message'}))

        // Analyst SQL, then one Neo4j call per account: ~20-30s, narrated over the wait.
        await narrate(
            "It is planning now. Account health lives in Snowflake, investors live in the graph, so it has to " +
            "combine tools, and read what comes back from each before it answers.",
        )
        await waitForAnswer(page, /Diane Greene/)
        await say("Cloudera and VMware are our Red accounts, and here are their investors, straight from the graph.")

        // An icon button: its label only appears on hover.
        const showTraces = page.getByRole('button', {name: 'Show Traces'}).first()
        await narrateDuring("The trace shows exactly how it got there.", async () => {
            await showTraces.hover()
            await pace(page, 1200)
        })
        await click(showTraces)
        // Spans in call order: semantic context, planning, the Analyst SQL, one
        // Custom Tool per Red account, the answer.
        await showSqlSpan(page, markAndSay, page.getByRole('button', {name: 'Select SQL Execution'}).first(), {
            sql: "First, Cortex Analyst turned the question into SQL on our semantic view.",
            results: "Snowflake returned the Red accounts, each with the id of its organization in the graph.",
        })

        await click(page.getByRole('button', {name: 'Select Custom Tool'}).first())
        await pace(page, 1200)
        await markAndSay(
            page.getByText('get_organization_investors', {exact: true}).first(),
            "Then it called get_organization_investors, once for each Red account.",
            {zoom: 1.4},
        )
        await markAndSay(
            page.getByText('organization_id:', {exact: true}).first(),
            "The organization id comes from the Snowflake result, not from our question. That is the join.",
        )

        const rawResult = page.getByRole('code').first()
        // The marks are drawn into the video only, so this shot is clean.
        await shot([
            // The labels' column on the left, the tool name on the right, the result below.
            page.getByText('Request ID', {exact: true}).first(),
            page.getByText('get_organization_investors', {exact: true}).first(),
            rawResult,
        ], 'trace')

        const results = await openFullscreen(page, 1)
        await narrate(
            "And this is everything Neo4j sent back: every investor with its own id, name and type, before the " +
            "model turned it into a sentence.",
        )
        // Scroll through the record while the line plays.
        const code = results.getByRole('code').first()
        await code.hover()
        for (let i = 0; i < 6; i++) {
            await page.mouse.wheel(0, 180)
            await pace(page, 700)
        }
        await waitForNarration()
        await closeFullscreen(page, results)

        await narrateDuring(
            "Now a question that none of the fixed queries covers.",
            async () => {
                await click(page.getByRole('button', {name: 'Hide traces'}).last())
                await fill(chatBox, AGENT_JOIN_QUESTION)
            },
        )
        await click(page.getByRole('button', {name: 'Send message'}))
        await narrate(
            "The renewals are in Snowflake, the competitors are in the graph, and no fixed tool finds " +
            "competitors. So it reads the accounts first, and then writes its own Cypher.",
        )
        await waitForAnswer(page, /Workday/)
        await say("Slack competes with Workday, and Cloudera with Docker. All four are our accounts.")

        const joinTraces = page.getByRole('button', {name: 'Show Traces'}).last()
        await narrateDuring("Let's see the Cypher it wrote.", async () => {
            await joinTraces.hover()
            await pace(page, 1200)
        })
        await click(joinTraces)
        // The second run's spans: the Analyst SQL, then query_neo4j.
        await showSqlSpan(page, markAndSay, page.getByRole('button', {name: 'Select SQL Execution'}).last(), {
            sql: "Again Analyst writes the SQL first, this time for the accounts renewing in the next 45 days.",
            results: "Three accounts, with their organization ids.",
        })
        await click(page.getByRole('button', {name: 'Select Custom Tool'}).last())
        await pace(page, 1200)
        await markAndSay(
            page.getByText('query_neo4j', {exact: true}).first(),
            "This call went to query_neo4j, our bridge function.",
            {zoom: 1.4},
        )
        const args = await openFullscreen(page, 0)
        const cypher = args.getByText(/MATCH/).first()
        await showDecodedArgument(args, cypher)
        await markAndSay(
            cypher,
            "And this is the query the agent wrote, from nothing but the schema in the tool's description, with " +
            "the organization ids from Snowflake already filled in. The bridge function made sure it was a read " +
            "before running it.",
            {zoom: 1.3},
        )
        await closeFullscreen(page, args)

        await say(
            "And that closes the loop. We started out with an empty Snowflake account, gave it a secure way to " +
            "reach our Neo4j instance, brought our own embedding model along so we can search the vectors that " +
            "are already in the graph, and then wrapped that graph in functions an agent is able to call. What " +
            "we have now is an agent that answers questions from a live graph and joins them with data in " +
            "Snowflake, and we never had to leave Snowsight to build it.",
        )
        await narrate(undefined)
    })
}
