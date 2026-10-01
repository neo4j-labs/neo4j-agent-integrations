// Steps 4-6: the Neo4j secret, the network rule and the external access integration.
import {test} from '@playwright/test'
import {click, narrate} from 'playwright-recast'
import {zoomDialog} from '../../../tools/screencast/narration.ts'
import {openNavItem, pickDatabaseAndSchema} from '../snowsight/catalog.ts'
import {openOrCreateWorksheet, runSelected} from '../snowsight/workspace.ts'
import {dismissPopups} from '../snowsight/popups.ts'
import {INTEGRATION_SQL, SECRET_SQL, WORKSHEET_NAME} from '../stack.ts'
import type {Ctx} from './context.ts'

export async function createSecret(ctx: Ctx) {
    const {page, ws, editor, step, say, introduce} = ctx
    await step("4. create secret (SQL)", async () => {
        // Navigate before speaking, so the line plays over its own statement.
        await page.getByRole('link', {name: 'Projects', exact: true}).click()
        await openOrCreateWorksheet(page, ws, WORKSHEET_NAME)
        await introduce(SECRET_SQL,
            "Next we create the secret that holds the Neo4j username and password our user-defined functions " +
            "will pull at runtime.",
        )
        await say("The secret can currently only be created with this SQL statement.")
        await runSelected(page, ws, editor);
    })
}

export async function createNetworkRule(ctx: Ctx) {
    const {page, step, narrateDuring, fill, shot} = ctx
    await step("5. create network rule (UI)", async () => {
        const ruleDialog = page.getByRole('dialog', {name: 'New network rule'})
        await narrateDuring(
            "By default, Snowflake can't reach the outside world. A network rule opens a path to our Neo4j instance.",
            async () => {
                await openNavItem(page, 'Governance & security', /^Network policies/)
                await click(page.getByRole('link', {name: 'Network Rules'}))
                // The "New rules" popover lands a moment after the page.
                await test.step('hidden - dismiss popups', async () => {
                    await page.getByText('Snowflake default network rules').first()
                        .waitFor({timeout: 4_000}).catch(() => {/* not shown this time */})
                    await dismissPopups(page)
                })
                await click(page.getByRole('button', {name: 'Network Rule', exact: true}))
                await ruleDialog.waitFor({timeout: 30_000})
            },
        )
        await zoomDialog(page, ruleDialog)
        await narrateDuring("The rule lives in our schema, and it describes a host and a port.", async () => {
            await ruleDialog.getByRole('textbox', {name: 'Network rule name'}).fill('NEO4J_ACCESS_RULE')
            await ruleDialog.getByRole('button', {name: /Database/}).click()
            await pickDatabaseAndSchema(page)
            await click(ruleDialog.getByRole('button', {name: /Type/}))
            await click(page.getByRole('option', {name: 'Host Port'}))
        })
        await narrateDuring("We allow exactly one address: the Neo4j demo instance on port 7687.", async () => {
            await fill(ruleDialog.getByRole('textbox', {name: /Host:port/i}), 'demo.neo4jlabs.com:7687')
            await click(ruleDialog.getByRole('button', {name: 'Add'}))
            await shot(ruleDialog, 'network-rule')
        })
        await click(ruleDialog.getByRole('button', {name: 'Create'}))
    })
}

export async function createIntegration(ctx: Ctx) {
    const {page, ws, editor, step, say, introduce} = ctx
    await step("6. create external access integration (SQL)", async () => {
        await page.getByRole('link', {name: 'Projects', exact: true}).click()
        await openOrCreateWorksheet(page, ws, WORKSHEET_NAME)
        await introduce(INTEGRATION_SQL,
            "The external access integration ties the rule and the secret together so user defined functions can use them.",
        )

        await runSelected(page, ws, editor)
        await say(
            "We have now configured the entire connectivity layer: we created a database with a schema and, with " +
            "the help of an external access integration, wired both a network rule and the credentials to " +
            "access our Neo4j instance. Next, we’ll look at how to deploy our own embedding model, define " +
            "user-defined functions, and set up an agent.",
        )
        await narrate(undefined)
    })
}
