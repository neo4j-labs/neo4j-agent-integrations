// Steps 6-7: connect the MCP server in CoWork with the user's Aura login, ask the agent.
import {test, type Locator, type Page} from '@playwright/test'
import {click, narrate, pace, showUrl, waitForNarration} from 'playwright-recast'
import {blurText} from '../../../tools/screencast/blur.ts'
import {saveAuraState} from '../aura-state.ts'
import {AGENT_DISPLAY_NAME, AGENT_QUESTION, MCP_SERVER_DISPLAY_NAME} from '../stack.ts'
import type {Ctx} from './context.ts'
import {coworkUrl, dismissCoWorkPopups, openCoWork} from './session.ts'

// Aura's login in its popup: Auth0's "Continue with Neo4j Aura", then Neo4j's
// own sign-in, which the saved Google session passes, then the consent. The
// renderer composites the popup into the video; a line spoken while it is on
// screen holds it there, so each screen is narrated before its click.
async function completeAuraLogin(auth: Page, ctx: Ctx) {
    // In order of appearance. `shot` names the guide's screenshot of the screen.
    const screens: {button: RegExp, shot?: string, line?: string}[] = [
        // Social buttons' names start with their icon's alt text, e.g. "Connection icon".
        {
            button: /Continue with Neo4j Aura$/, shot: 'aura-login',
            line: "Aura's sign-in page opens in a popup, and we continue with our Neo4j Aura account.",
        },
        {button: /(Continue with Google|Sign in with Google|Log in with Google)$/i},
        {
            button: /^(Accept|Allow|Authorize|Continue)$/i, shot: 'aura-consent',
            line: "The first time, Aura asks whether Snowflake may access our account, so we click Accept.",
        },
    ]
    const done = new Set<RegExp>()
    const deadline = Date.now() + 90_000
    while (Date.now() < deadline) {
        if (auth.isClosed() || /ai\.snowflake\.com/.test(auth.url())) return
        for (const screen of screens) {
            if (done.has(screen.button)) continue
            const button = auth.getByRole('button', {name: screen.button}).or(auth.getByRole('link', {name: screen.button})).first()
            if (!await button.isVisible().catch(() => false)) continue
            // From the prompt's heading to its button. Auth0's markup has no element
            // that spans both: the one holding them ends above the buttons.
            if (screen.shot) await ctx.shot([auth.getByRole('heading').first(), button], screen.shot).catch(() => {/* best effort */})
            // A remembered Auth0 session skips straight to the consent, so the
            // URL goes with whichever screen comes first.
            if (done.size === 0) await showUrl(auth)
            if (screen.line) await ctx.say(screen.line)
            done.add(screen.button)
            await click(button).catch(() => {/* navigated away */})
            break
        }
        // Google's account chooser lists the account by its address (blurred).
        if (/accounts\.google\.com/.test(auth.url())) {
            await auth.getByRole('link', {name: /@/}).first().click({timeout: 2_000}).catch(() => {/* not the chooser */})
        }
        await auth.waitForTimeout(1000).catch(() => {/* closed */})
    }
    throw new Error(`Aura login did not finish, stuck at ${auth.url()}`)
}

export async function connectMcpServer(ctx: Ctx) {
    const {page, step, say, narrateDuring, markAndSay, shot} = ctx
    await step('6. connect to Aura (CoWork)', async () => {
        // The CoWork sign-in and Aura's login round trip on top of the step budget.
        test.setTimeout(test.info().timeout + 2 * 60_000)
        // The lines play over CoWork, not over the agent page left behind.
        await openCoWork(ctx, coworkUrl(page.url()))
        await showUrl(page)
        await say(
            "Users chat with the agent in Snowflake CoWork at ai.snowflake.com. Before the agent can use " +
            "the MCP server, each user connects it once with their own Aura account.",
        )
        await narrateDuring("We find the connection under Capabilities, on the MCP Connectors tab.", async () => {
            await click(page.getByRole('button', {name: 'Capabilities'}))
            await click(page.getByRole('tab', {name: 'MCP Connectors'}))
            await page.getByRole('heading', {name: 'MCP Connectors'}).waitFor({timeout: 30_000})
            await pace(page, 800)
        })
        const card = page.getByRole('button')
            .filter({has: page.getByText(MCP_SERVER_DISPLAY_NAME, {exact: true})}).first()
        await markAndSay(card, "Here's our Neo4j Aura server. It isn't connected yet.")
        await shot(card, 'cowork-connect')

        await say("We click Connect and sign in with the same account we use for the Aura console.")
        const popup = page.waitForEvent('popup', {timeout: 10_000}).catch(() => null)
        await click(card.getByRole('button', {name: 'Connect'}))
        const auth = await popup
        // A popup has none of the page's init scripts; its consent screen greets the user by name.
        if (auth) await blurText(auth, ctx.blur)
        await completeAuraLogin(auth ?? page, ctx)
        // The popup usually closes itself right after the consent.
        if (auth && !auth.isClosed()) await auth.waitForEvent('close', {timeout: 60_000}).catch(() => {/* closed meanwhile */})
        await card.getByRole('button', {name: 'Disconnect'}).waitFor({timeout: 60_000})
        // The login renewed the Aura session; keeping it spares the next run an aura-login.
        await saveAuraState(page.context())
        await markAndSay(card, "Now the server is connected. Snowflake stores the token for this user only.")
    })
}

// Streams in; done once the text has stopped changing for a few seconds.
async function waitForAnswer(page: Page, main: Locator) {
    let last = ''
    let stableSince = Date.now()
    const deadline = Date.now() + 4 * 60_000
    while (Date.now() < deadline) {
        const text = await main.innerText()
        if (text !== last) {
            last = text
            stableSince = Date.now()
        } else if (Date.now() - stableSince > 6_000) {
            return
        }
        await page.waitForTimeout(1000)
    }
    throw new Error('the answer did not settle within 4 minutes')
}

// The collapsed call groups of the answer, top to bottom: buttons holding only
// a label paragraph, between the question and the answer's own buttons. The
// follow-up suggestions below those look the same, but clicking one would ask
// a new question.
async function callGroups(page: Page, main: Locator): Promise<Locator[]> {
    const top = (await main.getByText(AGENT_QUESTION, {exact: true}).last().boundingBox())?.y
    const bottom = (await main.getByRole('button', {name: 'Helpful'}).last().boundingBox())?.y
    if (top === undefined || bottom === undefined) return []
    const candidates = main.getByRole('button').filter({has: page.locator('p')})
    const groups: {y: number, locator: Locator}[] = []
    for (let i = 0; i < await candidates.count(); i++) {
        const button = candidates.nth(i)
        const box = await button.boundingBox()
        const label = (await button.innerText()).trim()
        if (!box || box.y <= top || box.y >= bottom || label.length < 12) continue
        groups.push({y: box.y, locator: button})
    }
    return groups.sort((a, b) => a.y - b.y).map((g) => g.locator)
}

// CoWork shows the read-cypher arguments as JSON with the query on one clipped
// line. For the video only, the block shows the query alone, wrapped: same
// text, readable.
async function showQuery(code: Locator): Promise<Locator> {
    await code.evaluate((el) => {
        // The decoded text no longer matches the locator that found the block.
        el.setAttribute('data-screencast-query', '')
        try {
            const query = JSON.parse(el.textContent ?? '').query
            if (typeof query !== 'string') return
            el.textContent = query
        } catch {
            return
        }
        Object.assign((el as HTMLElement).style, {whiteSpace: 'pre-wrap', overflow: 'visible', textOverflow: 'clip'})
    })
    await code.page().waitForTimeout(300)
    return code.page().locator('[data-screencast-query]').last()
}

export async function askAgent(ctx: Ctx) {
    const {page, step, say, narrateDuring, markAndSay, fill, shot} = ctx
    await step('7. ask the agent (CoWork)', async () => {
        test.setTimeout(test.info().timeout + 5 * 60_000)
        const main = page.getByRole('main', {name: 'Main content'})
        await narrateDuring("Now we start a new chat and select our movies agent.", async () => {
            await click(page.getByRole('button', {name: 'New chat'}))
            await test.step('hidden - dismiss popups', () => dismissCoWorkPopups(ctx))
            // The picker is labelled with the selected agent, so it is found by position.
            await main.getByRole('textbox').waitFor({timeout: 30_000})
            await click(main.getByRole('button', {name: 'Add attachments or select sources'})
                .locator('xpath=following::button[1]'))
            await click(page.getByRole('menuitemradio', {name: AGENT_DISPLAY_NAME}))
        })
        await narrateDuring("Then we ask a question that only the Neo4j database can answer.", () => fill(main.getByRole('textbox'), AGENT_QUESTION))
        await page.keyboard.press('Enter')
        await narrate(
            "The agent doesn't know the data model yet, so it first reads the schema through the MCP server " +
            "and then writes its own Cypher query.",
        )
        // Cut: the answer takes 30 s and more, and the polling keeps the render
        // from speeding the wait up. The line plays over the question.
        await waitForNarration()
        await test.step('hidden - wait for the answer', () => waitForAnswer(page, main))
        await say("And here's the answer, straight from our Aura database.")

        // The calls fold into one or more groups, each labelled with its first
        // call's description.
        const groups = await callGroups(page, main)
        if (groups.length === 0) throw new Error('no MCP call groups in the answer')
        await groups[0]!.scrollIntoViewIfNeeded()
        await markAndSay(groups[0]!, "Here, CoWork lists the calls the agent made to the MCP server.")
        await narrateDuring("First it read the schema, then it ran a query.", async () => {
            for (const group of groups) await click(group)
            await main.getByText('View', {exact: true}).last().waitFor({timeout: 10_000})
            await pace(page, 800)
        })
        // The number and order of calls vary per answer. The Cypher is in the
        // last read-cypher call, the one whose arguments have a "query".
        const json = main.locator('code, pre').filter({hasText: '"query"'}).last()
        const views = main.getByText('View', {exact: true})
        for (let i = await views.count() - 1; i >= 0 && !await json.isVisible(); i--) {
            await click(views.nth(i))
            await json.waitFor({timeout: 3_000}).catch(async () => {
                await click(main.getByText('Hide', {exact: true}).last())
            })
        }
        await json.waitFor({timeout: 5_000})
        const cypher = await showQuery(json)
        await markAndSay(cypher,
            "This is the Cypher query the agent sent to the MCP server. It wrote it from the schema alone.", {zoom: 1.3})
        await shot([groups[0]!, cypher], 'cowork-cypher')
        await say(
            "That's the whole setup: one integration, one MCP server and one agent. There are no functions " +
            "or secrets, and every user accesses Neo4j with their own account.",
        )
        await narrate(undefined)
    })
}
