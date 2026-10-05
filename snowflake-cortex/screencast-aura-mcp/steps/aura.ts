// Intro and step 1: the Aura instance and its MCP URL.
import {test} from '@playwright/test'
import {click, pace, showUrl} from 'playwright-recast'
import {zoomDialog} from '../../../tools/screencast/narration.ts'
import type {Ctx} from './context.ts'

export async function intro(ctx: Ctx) {
    const {page, step, say} = ctx
    await step('intro', async () => {
        await test.step('hidden - open the Aura console', async () => {
            await page.goto('https://console.neo4j.io/')
            const instance = page.getByRole('button', {name: 'More instance actions'}).first()
            await instance.or(page.getByRole('heading', {name: /Log in|Welcome/i})).first().waitFor({timeout: 60_000})
            if (!await instance.isVisible()) throw new Error('The Aura session expired; run npm run aura-login')
            // 'Try the new instance explorer' covers the instance card.
            await page.getByRole('complementary').getByRole('button', {name: 'Skip'}).click({timeout: 5_000})
                .catch(() => {/* not shown */})
            await pace(page, 2000)
        })
        await say(
            "In this video, we connect a Cortex agent in Snowflake to a Neo4j Aura database over MCP. " +
            "Aura runs the MCP server for us, so there's nothing to deploy.",
        )
        await showUrl(page)
        await say("We start in the Aura console at console.neo4j.io.")
    })
}

export async function findMcpUrl(ctx: Ctx) {
    const {page, step, say, narrateDuring, markAndSay, shot} = ctx
    await step('1. find the MCP URL (Aura)', async () => {
        await say("This is our Aura database. It contains the Movies sample data.")
        // The drawer's role=dialog element itself counts as hidden; its content does not.
        const inspect = page.getByRole('dialog').filter({hasText: 'MCP URL'})
            .getByRole('button', {name: 'Close'}).locator('xpath=..')
        await narrateDuring("Every Aura database has its own MCP server. We find its address under Inspect.", async () => {
            await click(page.getByRole('button', {name: 'More instance actions'}).first())
            await click(page.getByRole('menuitem', {name: 'Inspect'}))
            await inspect.waitFor({timeout: 30_000})
            await pace(page, 800)
        })
        // The drawer is full height; the header and the Overview tab hold everything.
        const overview = [inspect.getByRole('button', {name: 'Close'}).first(), inspect.getByRole('tabpanel', {name: 'Overview'})]
        await zoomDialog(page, overview[1]!)
        await markAndSay(
            inspect.getByText(/mcp-instances\.neo4j\.io/).first(),
            "This is the MCP URL. Don't mix it up with the connection URI or the Query API URL above it.",
        )
        await shot(overview, 'aura-mcp-url')
        await say(
            "Aura signs users in with OAuth, which is exactly what Snowflake's MCP connectors expect. " +
            "So the two work together directly.",
        )
        await click(inspect.getByRole('button', {name: 'Close'}).first())
    })
}
