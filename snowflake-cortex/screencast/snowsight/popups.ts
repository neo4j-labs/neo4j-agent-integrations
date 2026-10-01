// Snowsight's onboarding tours, "What's new" bubbles and toasts, which show up
// at unpredictable moments and block clicks.
import {test, type Locator, type Page} from '@playwright/test'

// Best effort. The spec runs it as the hidden pre-step of every step. Add
// patterns here as new banners appear.
export async function dismissPopups(page: Page) {
    // Workspaces renders in its own iframe and ships its own feature tours
    // ('Semantic view is available in workspace'), which sit on top of the
    // editor toolbar and swallow clicks on "Run selected".
    const workspaces = page.frameLocator('iframe[title="Workspaces"]')
    const candidates: Locator[] = [
        workspaces.getByRole('region').getByRole('button', {name: 'Close'}),
        // The 'New updates' tour (Agent Studio) stacks on top of 'Settings have
        // moved' and blocks its buttons, so it goes first.
        page.getByRole('dialog', {name: 'New updates'}).getByRole('button', {name: 'Skip'}),
        // 'Settings have moved' (role=dialog, Agents page)
        page.getByRole('dialog', {name: 'Settings have moved'})
            .getByRole('button', {name: 'Got it'}),
        // 'Cortex Code is here' (floating panel, home page)
        page.locator('div')
            .filter({has: page.getByRole('heading', {name: 'Cortex Code is here'})})
            .first()
            .getByRole('button', {name: 'Close'}),
         page.locator('div')
            .filter({has: page.getByRole('heading', {name: 'New'})})
            .first()
            .getByRole('button', {name: 'Close'}),
        // 'Find it fast with Command Palette' (Workspaces tour)
        page.locator('*')
            .filter({hasText: 'Find it fast with Command Palette'})
            .first()
            .getByRole('button', {name: 'OK'}),
        // 'Snowflake default network rules' (Network Rules page). Scoped to the
        // dialog: filtering `*` matches <html>, and then every Dismiss button.
        page.getByRole('dialog')
            .filter({hasText: 'Snowflake default network rules'})
            .getByRole('button', {name: /^(Close|Dismiss)$/}),
        // Feature-tour bubbles ('Semantic view is available in workspace',
        // 'Agent readiness', 'CoCo is here') and "What's new" announcements
        // ('Introducing External Data', anchored to a nav flyout) render as
        // role=region with their own Close/Got it button.
        page.getByRole('region').getByRole('button', {name: 'Got it'}),
        page.getByRole('region').getByRole('button', {name: 'Close'}),
        // The CoCo assistant panel opens itself on the agent pages and eats a
        // third of the viewport.
        page.getByRole('button', {name: 'Dismiss panel'}),
        // Error/info toasts, e.g. save failures.
        page.getByRole('alert').getByRole('button', {name: /^(Dismiss|Close)$/}),
        page.getByRole('status').getByRole('button', {name: /^(Dismiss|Close)$/}),
    ]
    for (const btn of candidates) {
        if (await btn.count() > 0) {
            await btn.first().click({timeout: 1000}).catch(() => {/* not visible / already gone */
            })
        }
    }
}

/**
 * Dismisses a known popup when it blocks an interaction mid-step.
 * dismissPopups() covers step boundaries.
 */
export async function installPopupHandlers(page: Page) {
    const ws = page.frameLocator('iframe[title="Workspaces"]')
    // A hidden step, so the popup and its closing are cut from the video.
    const dismissHidden = (body: () => Promise<unknown>) => test.step('hidden - dismiss popup', async () => { await body() })

    // 'New updates' overlays 'Settings have moved' and intercepts its buttons,
    // so it needs its own handler, registered first.
    await page.addLocatorHandler(
        page.getByRole('dialog', {name: 'New updates'}),
        (dialog) => dismissHidden(() => dialog.getByRole('button', {name: 'Skip'}).click()),
    )

    await page.addLocatorHandler(
        page.getByRole('dialog').filter({hasText: 'Snowflake default network rules'}),
        (dialog) => dismissHidden(() => dialog.getByRole('button', {name: /^(Close|Dismiss)$/}).first().click()),
    )

    await page.addLocatorHandler(
        page.getByRole('dialog').filter({
            hasText: /Settings have moved|Cortex Code is here|Find it fast|Welcome/i,
        }),
        (dialog) => dismissHidden(() => dialog.getByRole('button', {name: /^(Got it|Dismiss|Close|OK|Ok)$/}).first().click()),
    )

    // Workspaces tour bubbles pop in mid-step and cover the editor toolbar.
    await page.addLocatorHandler(
        ws.getByRole('region').filter({hasText: /Semantic view|Command Palette|Workspaces/i}),
        (region) => dismissHidden(() => region.getByRole('button', {name: 'Close'}).first().click()),
    )

    // Tour bubbles bring a transparent full-page backdrop that swallows every
    // click. "Agent readiness" lands seconds into a step. The `has` filter skips
    // ordinary regions that mention these words, on which the handler would hang.
    const tourCloseButton = page.getByRole('button', {name: /^(Got it|Close|Dismiss)$/})
    await page.addLocatorHandler(
        page.getByRole('region')
            .filter({hasText: /What's new|Agent readiness/i})
            .filter({has: tourCloseButton})
            .first(),
        (region) => dismissHidden(() => region.getByRole('button', {name: /^(Got it|Close|Dismiss)$/})
            .first()
            .click({timeout: 5_000})
            .catch(() => {/* closed itself in the meantime */})),
    )
}
