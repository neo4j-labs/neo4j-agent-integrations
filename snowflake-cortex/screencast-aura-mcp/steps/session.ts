// Off camera: drop a previous run's objects, sign in to CoWork.
import {test} from '@playwright/test'
import {generateSync as generateTotp} from 'otplib'
import {pace} from 'playwright-recast'
import {fillEditor, fitResultsPane, openOrCreateWorksheet} from '../../screencast/snowsight/workspace.ts'
import {CLEANUP_STATEMENTS, WORKSHEET_NAME} from '../stack.ts'
import type {Ctx} from './context.ts'

const env = (key: string): string => {
    const val = process.env[key]
    if (!val) throw new Error(`Environment variable ${key} not set (see .env.example)`)
    return val
}

// The home page greets the user by first name, and CoWork shows the full name.
// The account menu only has the username, so the name is read here.
export async function readFirstName(ctx: Ctx): Promise<string | undefined> {
    const greeting = await ctx.page.getByText(/^Hi \S+, how can I help/).first()
        .textContent({timeout: 15_000}).catch(() => null)
    return greeting?.match(/^Hi (\S+),/)?.[1]
}

export async function cleanup(ctx: Ctx) {
    const {page, ws, editor, step, runStatement} = ctx
    await step('hidden - cleanup', async () => {
        await page.getByRole('link', {name: 'Projects', exact: true}).click()
        await openOrCreateWorksheet(page, ws, WORKSHEET_NAME)
        for (const statement of CLEANUP_STATEMENTS) await runStatement(statement)
        await fillEditor(page, editor, ' ')
        await fitResultsPane(page, ws)
        await pace(page, 1200)
    })
}

/** CoWork's URL for the account Snowsight is signed in to: app.snowflake.com/<org>/<account>/... */
export function coworkUrl(snowsightUrl: string) {
    const [, org, account] = new URL(snowsightUrl).pathname.split('/')
    if (!org || !account) throw new Error(`no org/account in ${snowsightUrl}`)
    return `https://ai.snowflake.com/${org}/${account}`
}

// CoWork signs in separately, with the same user and TOTP.
export async function openCoWork(ctx: Ctx, url: string) {
    const {page} = ctx
    await test.step('hidden - open CoWork', async () => {
        await page.goto(url)
        const username = page.getByRole('textbox', {name: 'Username'})
        const capabilities = page.getByRole('button', {name: 'Capabilities'})
        await username.or(capabilities).first().waitFor({timeout: 60_000})
        if (await username.isVisible()) {
            await username.fill(env('SNOWFLAKE_USER'))
            await page.getByRole('textbox', {name: 'Password'}).fill(env('SNOWFLAKE_PASSWORD'))
            await page.getByRole('button', {name: 'Sign in'}).click()
            const otp = page.getByTestId('input').first()
            await otp.or(capabilities).first().waitFor({timeout: 60_000})
            if (await otp.isVisible()) {
                await otp.fill(generateTotp({secret: env('SNOWFLAKE_OTP_SECRET_KEY')}))
                await page.getByRole('button', {name: 'Continue'}).click()
            }
        }
        await capabilities.waitFor({timeout: 60_000})
        await dismissCoWorkPopups(ctx)
        await deleteChats(ctx)
        await pace(page, 1500)
    })
}

// Earlier runs' chats pile up under Recents, in view of every CoWork shot.
export async function deleteChats(ctx: Ctx) {
    const {page} = ctx
    // Not scoped to the sidebar: CoWork's builds don't all mark it as navigation.
    const chats = page.locator('a[href*="#/ai/chat/"]')
    // Recents load after the rest of the page.
    await chats.first().waitFor({timeout: 10_000}).catch(() => {/* no chats */})
    // "Show more" hides the older ones, so this runs until none is left.
    for (let round = 0; round < 100 && await chats.count() > 0; round++) {
        const chat = chats.first()
        const href = await chat.getAttribute('href')
        await chat.hover()
        await chat.locator('xpath=..').getByRole('button', {name: 'More options'}).click()
        await page.getByRole('menuitem', {name: 'Delete'}).click()
        // A confirmation, if CoWork asks for one.
        await page.getByRole('dialog').getByRole('button', {name: /^Delete$/}).click({timeout: 3_000})
            .catch(() => {/* deleted without asking */})
        // The list refills from "Show more", so its length says nothing; the
        // deleted chat's link has to go.
        await page.locator(`a[href="${href}"]`).waitFor({state: 'detached', timeout: 10_000})
    }
    if (await chats.count() > 0) throw new Error(`${await chats.count()} CoWork chats left after the cleanup`)
}

// The Automations intro and other one-time CoWork dialogs.
export async function dismissCoWorkPopups(ctx: Ctx) {
    const {page} = ctx
    for (const name of ['Try later', 'Dismiss', 'Close automations intro']) {
        const button = page.getByRole('button', {name, exact: true})
        if (await button.count() > 0) await button.first().click({timeout: 2_000}).catch(() => {/* gone */})
    }
}
