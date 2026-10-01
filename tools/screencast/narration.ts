import {test, type Locator, type Page} from '@playwright/test'
import {click, highlight, narrate, pace, waitForNarration, zoom} from 'playwright-recast'

/** Dialogs are zoomed while filled in, so they stay readable on small screens. */
const DIALOG_ZOOM = 1.3

// ONLY_STEPS=8,9 records only those steps, for quick iteration. It relies on
// the objects a previous full run left behind.
export const ONLY_STEPS = process.env.ONLY_STEPS?.split(',').map((s) => s.trim())

/**
 * Narration helpers bound to a page. `before` runs as a hidden pre-step of
 * every step, e.g. popup dismissal. An ONLY_STEPS run skips the `fullRunOnly`
 * steps, e.g. the cleanup.
 */
export function createNarration(page: Page, opts: {before?: () => Promise<void>, fullRunOnly?: string[]} = {}) {
    const isSelected = (name: string) => {
        if (!ONLY_STEPS) return true
        if (opts.fullRunOnly?.includes(name)) return false
        if (name.startsWith('hidden - ')) return true
        return ONLY_STEPS.includes(name.split('.')[0]!)
    }

    // Extending the timeout by each step's runtime makes it a per-step budget,
    // so a timeout points at the slow step.
    const step = async <T>(name: string, body: () => Promise<T>): Promise<T | undefined> => {
        if (!isSelected(name)) return undefined
        const start = Date.now()
        try {
            if (opts.before) await test.step('hidden - dismiss popups', opts.before)
            return await test.step(name, body)
        } finally {
            test.setTimeout(test.info().timeout + (Date.now() - start))
        }
    }

    // The viewer hears what is about to happen before seeing the clicks.
    // The wait costs no video time, because the renderer freezes the frame.
    const say = async (text: string) => {
        await narrate(text)
        await waitForNarration()
    }

    // Holding until the line ends keeps the next line's actions from starting
    // under this one.
    const narrateDuring = async <T>(
        text: string, actions?: () => Promise<T>,
    ): Promise<T | undefined> => {
        await narrate(text)
        const result = actions ? await actions() : undefined
        await waitForNarration()
        return result
    }

    // The mark lasts exactly as long as the line, so only one thing is
    // highlighted at any moment.
    const markAndSay = async (locator: Locator, text: string, opts?: {zoom?: number}) => {
        if (opts?.zoom) await zoom(locator, opts.zoom)
        await highlight(locator, {duration: 'narration'})
        await say(text)
    }

    // Selects the old value first: some forms mirror one field into another as
    // you type, so typing on top would append.
    const fill = async (locator: Locator, text: string) => {
        await click(locator)
        await page.keyboard.press('ControlOrMeta+A')
        await locator.pressSequentially(text, {delay: 30})
        await pace(page, 1000)
    }

    // Long prose would take half a minute to type out, so it lands in one go.
    const fillInstantly = async (locator: Locator, text: string) => {
        await click(locator)
        await locator.fill(text)
        await pace(page, 800)
    }

    return {step, say, narrateDuring, markAndSay, fill, fillInstantly}
}

export type Narration = ReturnType<typeof createNarration>

/**
 * Zooms onto `target` up to DIALOG_ZOOM, but keeps all of it in frame, or a
 * tall dialog would lose its title. Skips zooms too small to notice.
 */
export async function zoomDialog(page: Page, target: Locator) {
    const viewport = page.viewportSize()
    const box = await target.boundingBox()
    if (!viewport || !box) return
    const fit = Math.min(DIALOG_ZOOM, (viewport.height * 0.92) / box.height, (viewport.width * 0.92) / box.width)
    if (fit < 1.05) return
    await zoom(target, Math.round(fit * 100) / 100)
}

/** Zooms onto the open list holding `option`. The list can open outside the dialog's zoom. */
export async function zoomOnList(page: Page, option: string) {
    const list = page.getByRole('listbox').filter({has: page.getByRole('option', {name: option, exact: true})}).first()
    await list.waitFor({timeout: 10_000})
    await zoomDialog(page, list)
}

/**
 * Scrolls `target` into view smoothly. Playwright's own scrolling jumps, so the
 * next field would appear from nowhere. Does nothing if it is fully in view.
 */
export async function scrollIntoViewVisibly(page: Page, target: Locator) {
    const moved = await target.evaluate((el) => {
        const r = el.getBoundingClientRect()
        const inView = r.top >= 0 && r.bottom <= (el.ownerDocument.defaultView?.innerHeight ?? r.bottom)
        // A field in a scrolling dialog can be in the window's view but still
        // clipped by the dialog.
        let clipped = false
        for (let p = el.parentElement; p; p = p.parentElement) {
            if (p.scrollHeight > p.clientHeight && getComputedStyle(p).overflowY !== 'visible') {
                const pr = p.getBoundingClientRect()
                clipped = r.top < pr.top || r.bottom > pr.bottom
                break
            }
        }
        if (inView && !clipped) return false
        el.scrollIntoView({behavior: 'smooth', block: 'center'})
        return true
    })
    if (moved) await pace(page, 900)
}
