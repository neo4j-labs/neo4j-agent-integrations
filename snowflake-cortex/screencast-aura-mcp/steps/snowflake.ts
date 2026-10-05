// Steps 2-3: the API integration and the external MCP server, in SQL.
import {test} from '@playwright/test'
import {click, pace, showUrl} from 'playwright-recast'
import {explainCode, openOrCreateWorksheet, runSelected} from '../../screencast/snowsight/workspace.ts'
import {DATABASE_SQL, integrationSql, mcpServerSql, WORKSHEET_NAME} from '../stack.ts'
import type {Ctx} from './context.ts'

export async function createIntegration(ctx: Ctx) {
    const {page, ws, editor, step, say, introduce} = ctx
    await step('2. create the API integration (SQL)', async () => {
        await test.step('hidden - open Snowsight', async () => {
            await page.goto('https://app.snowflake.com/')
            await page.getByRole('link', {name: 'Projects', exact: true}).waitFor({timeout: 60_000})
        })
        await showUrl(page)
        await say("Now we switch to Snowsight at app.snowflake.com.")
        await click(page.getByRole('link', {name: 'Projects', exact: true}))
        await openOrCreateWorksheet(page, ws, WORKSHEET_NAME)
        await introduce(DATABASE_SQL, "First, we create a database to hold the MCP server.")
        await runSelected(page, ws, editor)

        await introduce(integrationSql(ctx.mcpUrl),
            "Snowflake talks to external MCP servers through an API integration, which an admin creates.")
        await explainCode(page, ws, [
            {match: 'API_PROVIDER', text: "Setting the provider to external MCP makes it an integration for MCP connectors."},
            {match: 'API_ALLOWED_PREFIXES', text: "It can only call URLs that start with our Aura MCP URL."},
            {
                match: 'OAUTH_DYNAMIC_CLIENT',
                text: "With a dynamic client, Snowflake registers itself with Aura's login service, so there's no " +
                    "client ID or secret to copy.",
            },
            {
                match: 'OAUTH_RESOURCE_URL',
                text: "The resource URL tells Snowflake where users sign in.",
            },
        ])
        await runSelected(page, ws, editor)
        await say("The integration stores no credentials. Later, each user signs in to Aura with their own account.")
    })
}

export async function createMcpServer(ctx: Ctx) {
    const {page, ws, editor, step, introduce} = ctx
    await step('3. create the MCP server (SQL)', async () => {
        await introduce(mcpServerSql(ctx.mcpUrl),
            "Next, we create the MCP server object that agents use. It points to the Aura URL and uses our integration.")
        await explainCode(page, ws, [
            {match: 'DISPLAY_NAME', text: "The display name is what users see in Agent Studio and CoWork."},
        ])
        await runSelected(page, ws, editor)
        await pace(page, 800)
    })
}
