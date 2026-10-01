// The Horizon Catalog: navigation, object lists, the database/schema picker and
// the grant dialog.
import type {Locator, Page} from '@playwright/test'
import {click, pace} from 'playwright-recast'
import {zoomOnList} from '../../../tools/screencast/narration.ts'
import {DATABASE, SCHEMA} from '../stack.ts'

// The left nav opens a flyout on hover whose entries are `option`s, not links.
export async function openNavItem(page: Page, group: string, item: string | RegExp) {
    await page.getByRole('navigation', {name: group}).hover()
    await click(page.getByRole('option', {name: item}))
}

/** Opens the Databases list. The Catalog opens on a landing page, so this goes through the tree. */
export async function openDatabases(page: Page) {
    await click(page.getByRole('link', {name: 'Catalog', exact: true}))
    await click(page.getByRole('treeitem', {name: /^Databases/}).getByText(/^Databases/))
    await listLoaded(page)
}

// A list still showing its loading skeleton under a narration looks empty.
export async function listLoaded(page: Page) {
    await page.getByRole('rowheader').first().waitFor({timeout: 30_000}).catch(() => {/* an empty list */})
    await pace(page, 800)
}

/**
 * The clickable name of an object in a Horizon Catalog list. Rows are headed
 * "<Kind> <NAME> Copy name"; the name itself opens the object.
 */
export function catalogRow(page: Page, kind: string, name: string): Locator {
    return page.getByRole('rowheader', {name: new RegExp(`^${kind} ${name}\\b`)}).getByText(name, {exact: true})
}

// Read off the account menu's avatar: its accessible name is the username
// whether the nav is expanded or collapsed (then only the avatar renders).
export async function accountMenuUser(page: Page): Promise<string> {
    const menu = page.getByRole('button', {name: 'Account Menu'})
    await menu.waitFor({timeout: 30_000})
    const user = await menu.getByRole('img').first().getAttribute('aria-label')
    if (!user) {
        throw new Error('could not read the Snowflake username from the account menu')
    }
    return user
}

// Two cascading "Suggestions" listboxes, databases then schemas. The schema
// name appears in BOTH, so the schema click is scoped to the second.
export async function pickDatabaseAndSchema(page: Page) {
    const picker = page.getByRole('dialog', {name: /Database schema filter|filter|Location/}).first()
    const databases = picker.getByRole('listbox', {name: 'Suggestions'}).first()
    const schemas = picker.getByRole('listbox', {name: 'Suggestions'}).nth(1)
    await click(databases.getByRole('option', {name: DATABASE, exact: true}))
    await click(schemas.getByRole('option', {name: SCHEMA, exact: true}))
    await pace(page, 600)
    // Some dialogs leave the picker open, where it swallows the next keystrokes;
    // Escape on a closed picker would close the dialog behind it.
    if (await picker.isVisible().catch(() => false)) {
        await page.keyboard.press('Escape')
    }
    await pace(page, 800)
}

/** Open the grant dialog from the current object's Access tab. */
export async function openGrantDialog(page: Page): Promise<Locator> {
    await click(page.getByRole('tab', {name: 'Access'}))
    await click(page.getByRole('button', {name: 'Privilege', exact: true}))
    const dialog = page.getByRole('dialog', {name: /Grant new privileges/})
    await dialog.waitFor({timeout: 30_000})
    return dialog
}

/** Pick the role in an open grant dialog, zoomed onto the open list. */
export async function pickRole(page: Page, dialog: Locator, role: string) {
    await click(dialog.getByRole('button', {name: 'Select role'}))
    await zoomOnList(page, role)
    await click(page.getByRole('option', {name: role, exact: true}))
}

/**
 * Picks privileges in an open grant dialog, zoomed onto the first open list.
 * Both pickers close on a pick, so no Escape is needed. It would close the dialog.
 */
export async function pickPrivileges(page: Page, dialog: Locator, privileges: string[]) {
    for (const [i, privilege] of privileges.entries()) {
        await click(dialog.getByRole('button', {name: 'Select privilege'}))
        // The schema list runs to dozens of entries; filtering (the search
        // field has focus) brings the one we want into view.
        await page.getByRole('searchbox', {name: 'Search options'}).pressSequentially(privilege, {delay: 30})
        if (i === 0) await zoomOnList(page, privilege)
        await click(page.getByRole('option', {name: privilege, exact: true}))
    }
}

export async function submitGrant(page: Page, dialog: Locator) {
    await click(dialog.getByRole('button', {name: 'Grant privileges'}))
    await dialog.waitFor({state: 'hidden', timeout: 60_000})
    await pace(page, 1200)
}
