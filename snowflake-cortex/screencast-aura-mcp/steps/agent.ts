// Steps 4-5: create the agent with the MCP server, publish it.
import {expect, test} from '@playwright/test'
import {click, narrate, pace} from 'playwright-recast'
import {zoomDialog} from '../../../tools/screencast/narration.ts'
import {openNavItem, pickDatabaseAndSchema} from '../../screencast/snowsight/catalog.ts'
import {dismissPopups} from '../../screencast/snowsight/popups.ts'
import {AGENT_DISPLAY_NAME, AGENT_NAME, DATABASE, MCP_SERVER, MCP_SERVER_DISPLAY_NAME, SCHEMA} from '../stack.ts'
import type {Ctx} from './context.ts'

export async function createAgent(ctx: Ctx) {
    const {page, step, narrateDuring, markAndSay, fill, shot} = ctx
    await step('4. create the agent (UI)', async () => {
        const createDialog = page.getByRole('dialog', {name: 'Create agent'})
        await narrateDuring("Next, we create the agent in Agent Studio.", async () => {
            await openNavItem(page, 'AI & ML', /^(Agents|Agent Studio)/)
            await click(page.getByRole('button', {name: 'Create agent'}).first())
            await createDialog.waitFor({timeout: 30_000})
        })
        await zoomDialog(page, createDialog)
        await narrateDuring("We put it in our new database and give it a name and a display name.", async () => {
            await click(createDialog.getByRole('button', {name: /Database/}))
            await pickDatabaseAndSchema(page, DATABASE, SCHEMA)
            await fill(createDialog.getByRole('textbox', {name: 'Agent object name'}), AGENT_NAME)
            await fill(createDialog.getByRole('textbox', {name: 'Display name'}), AGENT_DISPLAY_NAME)
        })
        await click(createDialog.getByRole('button', {name: 'Create agent'}))
        await createDialog.waitFor({state: 'hidden', timeout: 60_000})
        // The CoCo panel and the "Agent readiness" tour land a moment later; the
        // wait is hidden too, or the tour shows until it is dismissed.
        await test.step('hidden - dismiss popups', async () => {
            await page.waitForTimeout(3000)
            await dismissPopups(page)
        })

        await narrateDuring("The configuration has its own section for MCP servers.", async () => {
            await click(page.getByRole('tab', {name: 'Configuration'}))
            await click(page.getByRole('radio', {name: 'MCP'}))
            await page.getByRole('heading', {name: 'MCP', level: 1}).waitFor({timeout: 30_000})
            await pace(page, 800)
        })
        // Exact, or 'Neo4j Aura' would also match a server named 'Neo4j Aura (Movies)'.
        const card = page.getByRole('button')
            .filter({has: page.getByText(MCP_SERVER_DISPLAY_NAME, {exact: true})})
            .filter({hasText: MCP_SERVER}).first()
        await markAndSay(card, "It lists every MCP server our role can use, including our Neo4j Aura server.")
        await narrateDuring("We add it, and the agent gets all the tools the server provides.", async () => {
            await click(card.getByRole('button', {name: 'Add to agent'}))
            await card.getByRole('button', {name: 'Remove'}).waitFor({timeout: 30_000})
            await pace(page, 800)
        })
        // The whole MCP tab: the agent's name, its tabs, the MCP section and the added server.
        await shot([page.getByRole('button', {name: 'Back'}), page.getByRole('tablist', {name: 'Agent Details'}), card], 'agent-mcp-server')
        // Adding a server saves the draft by itself.
        await expect(page.getByRole('button', {name: 'Saved'})).toBeVisible({timeout: 60_000})
    })
}

export async function publishAgent(ctx: Ctx) {
    const {page, step, narrateDuring} = ctx
    await step('5. publish the agent (UI)', async () => {
        // No zoom: the dialog is small, and a zoom outlasts the line into the next step.
        const publishDialog = page.getByRole('dialog', {name: 'Publish'})
        await narrateDuring("That's all the agent needs, so we publish it.", async () => {
            await click(page.getByRole('button', {name: 'Publish'}))
            await publishDialog.waitFor({timeout: 30_000})
            await click(publishDialog.getByRole('button', {name: 'Publish'}))
            await publishDialog.waitFor({state: 'hidden', timeout: 60_000})
        })
        await pace(page, 1200)
    })
}
