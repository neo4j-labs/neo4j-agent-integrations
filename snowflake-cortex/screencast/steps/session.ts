// Off camera: sign in, clear one-time announcements, drop a previous run's objects.
import {generateSync as generateTotp} from 'otplib'
import {pace} from 'playwright-recast'
import {accountMenuUser, navGroup} from '../snowsight/catalog.ts'
import {fillEditor, fitResultsPane, openOrCreateWorksheet} from '../snowsight/workspace.ts'
import {dismissPopups} from '../snowsight/popups.ts'
import {CLEANUP_STATEMENTS, WORKSHEET_NAME} from '../stack.ts'
import type {Ctx} from './context.ts'

export const env = (key: string): string => {
    const val = process.env[key]
    if (!val) throw new Error(`Environment variable ${key} not set (see .env.example)`)
    return val
}

// Sign in with the .env credentials and TOTP.
export async function login(ctx: Ctx) {
    const {page, step} = ctx
    await step("hidden - login", async () => {
        await page.goto('https://app.snowflake.com/');
        await page.getByRole('textbox', {name: 'Account identifier'}).fill(env('SNOWFLAKE_ACCOUNT'));
        await page.getByRole('button', {name: 'Sign in'}).click();
        await page.getByRole('textbox', {name: 'Username'}).fill(env('SNOWFLAKE_USER'));
        await page.getByRole('textbox', {name: 'Password'}).fill(env('SNOWFLAKE_PASSWORD'));
        await page.getByRole('button', {name: 'Sign in'}).click();
        await page.getByTestId('input').first().fill(generateTotp({secret: env('SNOWFLAKE_OTP_SECRET_KEY')}));
        await page.getByRole('button', {name: 'Continue'}).click();
        await page.getByRole('button', {name: 'Hide navigation'}).click();
        // Without a short timeout, a missing dialog costs the full action timeout.
        await page.getByTestId('entry-dialog-close-button').click({timeout: 10_000}).catch(() => {/* dialog may not appear */
        });
    })
}

export async function drainAnnouncements(ctx: Ctx) {
    const {page, step} = ctx
    await step("hidden - drain one-time announcements", async () => {
        // "What's new" bubbles show once per account, on a nav flyout's first
        // opening. Opening every flyout here gets them out of the way off camera.
        for (const group of ['Catalog', 'AI & ML', 'Governance & security', 'Projects', 'Admin']) {
            await navGroup(page, group).hover({timeout: 5_000}).catch(() => {/* nav may be collapsed */})
            await page.waitForTimeout(1200)
            await dismissPopups(page)
        }
        await page.keyboard.press('Escape')
        // The "What's new" bubble leaves the Catalog flyout open after its
        // dismissal; only hovering Catalog again and leaving closes it.
        await navGroup(page, 'Catalog').hover({timeout: 5_000}).catch(() => {/* nav may be collapsed */})
        await page.waitForTimeout(500)
        await page.mouse.move(960, 540, {steps: 10})
    })
}

// Snowflake usernames differ from the login identifier (the login is an
// email, the user object is not), and the role grant needs the username.
export async function readUser(ctx: Ctx) {
    ctx.snowflakeUser = await accountMenuUser(ctx.page)
}

// Drops a previous run's objects, so every run starts from an empty account.
// The defaults are this screencast's; the Aura MCP screencast passes its own.
export async function cleanup(ctx: Ctx, worksheet = WORKSHEET_NAME, statements = CLEANUP_STATEMENTS) {
    const {page, ws, editor, step, runStatement} = ctx
    await step("hidden - cleanup", async () => {
        await page.getByRole('link', {name: 'Projects', exact: true}).click();
        await openOrCreateWorksheet(page, ws, worksheet);
        for (const statement of statements) await runStatement(statement)
        await fillEditor(page, editor, ' ');
        await fitResultsPane(page, ws)
        await pace(page, 1200)
    })
}
