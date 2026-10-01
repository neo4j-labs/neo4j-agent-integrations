// Steps 1-3: database and schema, the end-user role, its grants.
import {expect, test} from '@playwright/test'
import {click, pace} from 'playwright-recast'
import {zoomDialog} from '../../../tools/screencast/narration.ts'
import {catalogRow, listLoaded, openDatabases, openGrantDialog, openNavItem, pickPrivileges, pickRole, submitGrant} from '../snowsight/catalog.ts'
import {DATABASE, ROLE_NAME, SCHEMA} from '../stack.ts'
import type {Ctx} from './context.ts'

export async function createDatabaseAndSchema(ctx: Ctx) {
    const {page, step, narrateDuring, fill} = ctx
    await step("1. create database + schema (UI)", async () => {
        await expect(page.getByRole('link', {name: 'Catalog'})).toBeVisible()

        await narrateDuring(
            "Let's start with a database for our showcase. We find it in the catalog, under databases.",
            () => openDatabases(page),
        )
        const dbDialog = page.getByRole('dialog', {name: /New Database/})
        await narrateDuring("The plus button in the corner creates a new one.", async () => {
            await click(page.getByRole('button', {name: 'Database', exact: true}))
            await dbDialog.waitFor({timeout: 30_000})
        })
        await zoomDialog(page, dbDialog)
        await narrateDuring("We'll call it NEO4J_AGENT.", async () => {
            await fill(dbDialog.getByRole('textbox', {name: 'Name'}), DATABASE)
            await click(dbDialog.getByRole('button', {name: 'Create'}))
            await dbDialog.waitFor({state: 'hidden', timeout: 60_000})
        })
        await pace(page, 800)

        const schemaDialog = page.getByRole('dialog', {name: /New Schema/})
        await narrateDuring(
            "Inside this database, we add a schema. That is where our functions and the agent will live.",
            async () => {
                await click(catalogRow(page, 'Database', DATABASE))
                await click(page.getByRole('button', {name: /^Schema$/}))
                await schemaDialog.waitFor({timeout: 30_000})
            },
        )
        await zoomDialog(page, schemaDialog)
        await narrateDuring("We'll name it NEO4J_AGENT_SCHEMA.", async () => {
            await fill(schemaDialog.getByRole('textbox', {name: 'Name'}), SCHEMA)
            await click(schemaDialog.getByRole('button', {name: 'Create'}))
            await schemaDialog.waitFor({state: 'hidden', timeout: 60_000})
        })
        await pace(page, 800)
    })
}

export async function createRole(ctx: Ctx) {
    const {page, step, narrateDuring, fill} = ctx
    await step("2. create the end-user role (UI)", async () => {
        await narrateDuring(
            "Right now, everything belongs to ACCOUNTADMIN, the admin role we are signed in with.",
            async () => {
                await openNavItem(page, 'Governance & security', /^Users & roles/)
                await page.getByRole('row').nth(1).waitFor({timeout: 30_000})
                await pace(page, 800)
            },
        )
        const roleDialog = page.getByRole('dialog', {name: /New Role/})
        await narrateDuring(
            "The people who will chat with our agent shouldn't need that much power, so we give them a role of their own.",
            async () => {
                await click(page.getByRole('tab', {name: 'Roles'}))
                await click(page.getByRole('button', {name: 'Role', exact: true}))
                await roleDialog.waitFor({timeout: 30_000})
            },
        )
        await zoomDialog(page, roleDialog)
        await narrateDuring("We'll simply call it USER.", async () => {
            await fill(roleDialog.getByRole('textbox', {name: 'Name'}), ROLE_NAME)
            await click(roleDialog.getByRole('button', {name: 'Create Role'}))
            await roleDialog.waitFor({state: 'hidden', timeout: 60_000})
        })
        await pace(page, 1000)

        // Mirrors user_grant in samples/1-terraform/iam.tf; hidden because it
        // shows a personal account name and adds nothing to the story.
        await test.step('hidden - grant the role to the signed-in user', async () => {
            await page.getByRole('cell', {name: `role ${ROLE_NAME}`, exact: true}).click()
            await page.getByRole('button', {name: 'Grant to User'}).click()
            const userGrantDialog = page.getByRole('dialog', {name: /Grant Role to User/})
            await userGrantDialog.getByRole('button', {name: 'User to receive grant'}).click()
            await page.getByRole('option', {name: ctx.snowflakeUser, exact: true}).click()
            await page.keyboard.press('Escape')
            await userGrantDialog.getByRole('button', {name: 'Grant', exact: true}).click()
            await userGrantDialog.waitFor({state: 'hidden', timeout: 60_000})
        })
    })
}

export async function grantAccess(ctx: Ctx) {
    const {page, step, narrateDuring, shot} = ctx
    await step("3. grant the role access to database + schema (UI)", async () => {
        // Snowsight caches the role list per page load: the new role is missing
        // from every role picker until a reload.
        await test.step('hidden - refresh role cache', async () => {
            await page.reload()
            await page.getByRole('link', {name: 'Catalog'}).waitFor({timeout: 60_000})
        })

        await narrateDuring(
            "Our new role needs access to the database and the schema, so let's grant it.",
            async () => {
                await openDatabases(page)
                await click(catalogRow(page, 'Database', DATABASE))
                await listLoaded(page)
            },
        )
        const dbGrant = (await narrateDuring("Permissions are managed on the access tab.", () => openGrantDialog(page)))!
        await narrateDuring("We pick our new role, USER.", () => pickRole(page, dbGrant, ROLE_NAME))
        await narrateDuring("And we give it usage on the database.", async () => {
            await pickPrivileges(page, dbGrant, ['USAGE'])
            await submitGrant(page, dbGrant)
        })

        const schemaGrant = (await narrateDuring("Now we do the same for the schema.", async () => {
            // The database's schemas are listed on its Overview tab.
            await click(page.getByRole('tab', {name: 'Overview'}))
            await click(catalogRow(page, 'Schema', SCHEMA))
            return openGrantDialog(page)
        }))!
        await narrateDuring("Again, we pick our role.", () => pickRole(page, schemaGrant, ROLE_NAME))
        await narrateDuring(
            "Here, it gets usage, and also usage on all future functions.",
            async () => {
                await pickPrivileges(page, schemaGrant, ['USAGE', 'USAGE - FUTURE FUNCTION'])
                await shot(schemaGrant, 'grant-dialog')
            },
        )
        await narrateDuring(
            "That way, every function we create later is available to it right away.",
            () => submitGrant(page, schemaGrant),
        )
    })
}
