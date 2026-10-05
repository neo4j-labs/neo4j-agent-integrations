// The Workspaces SQL editor: one worksheet, one statement at a time.
import {test, type FrameLocator, type Locator, type Page} from '@playwright/test'
import {highlight, narrate, pace, waitForNarration, zoom} from 'playwright-recast'

export async function openOrCreateWorksheet(page: Page, ws: FrameLocator, name: string) {
    // The iframe occasionally comes up empty (stale session, slow boot); a
    // reload fixes it.
    const addNewMenu = ws.getByRole('button', {name: 'Add New Menu'})
    await addNewMenu.waitFor({timeout: 20_000}).catch(async () => {
        await page.reload()
        await addNewMenu.waitFor({timeout: 60_000})
    })

    // Otherwise count() races the tree load and creates a duplicate
    // ("showcase.sql.sql") of a file that exists.
    await ws.getByRole('treeitem').first().waitFor({timeout: 20_000})

    const existing = ws.getByRole('treeitem', {name})
    if (await existing.count() > 0) {
        await existing.first().click()
    } else {
        // Typing raced the rename box's focus and went nowhere, so the box is
        // filled directly, with the full name: fill() replaces its whole value.
        await ws.getByRole('button', {name: 'Add New Menu'}).click()
        await ws.getByRole('menuitem', {name: 'SQL file'}).click()
        const rename = ws.locator('input[value$=".sql"]').first()
        await rename.fill(name, {timeout: 10_000})
        await rename.press('Enter')
        await ws.getByRole('treeitem', {name}).first().waitFor({timeout: 10_000})
    }

    // The iframe occasionally wedges, e.g. on a broken tab that a previous run
    // left in Snowsight's session state.
    const editor = ws.getByRole('textbox', {name: 'Code Editor'})
    await editor.waitFor({timeout: 15_000}).catch(async () => {
        await page.reload()
        await editor.waitFor({timeout: 15_000})
    })
}

/** Measured row pitch of the results grid in CSS px, for header and data rows alike. */
const RESULTS_ROW_PX = 31

/** Rows the fitted results pane shows at most; more scroll inside the grid. */
const RESULTS_MAX_ROWS = 6

/**
 * Sizes the results pane to its header plus the grid's rows, capped at
 * RESULTS_MAX_ROWS. The rest goes to the editor.
 *
 * Snowsight opens the pane at half the worksheet after every run. That cuts a
 * long statement off and fills the zoomed frame with an almost empty grid.
 * Does nothing while the pane has no grid.
 */
export async function fitResultsPane(page: Page, ws: FrameLocator) {
    const grid = ws.getByTestId('data-grid-canvas').first()
    const gridBox = await grid.boundingBox().catch(() => null)
    if (!gridBox) return
    // The canvas carries an accessible table; its row count includes the header.
    const rows = Number(await grid.locator('table').getAttribute('aria-rowcount').catch(() => null) ?? 2)

    // Snowsight renders several horizontal drag handles; the pane's divider is
    // the closest one above the grid, the lowest one sits under the pane.
    const sashes = ws.locator('[data-testid="sash"].sash-horizontal')
    const boxes: {x: number, y: number, width: number}[] = []
    for (let i = 0; i < await sashes.count(); i++) {
        const box = await sashes.nth(i).boundingBox()
        if (box) boxes.push({x: box.x, y: box.y + box.height / 2, width: box.width})
    }
    const divider = boxes.filter((b) => b.y < gridBox.y).sort((a, b) => b.y - a.y)[0]
    const paneBottom = Math.max(...boxes.map((b) => b.y))
    if (!divider || paneBottom <= gridBox.y) return

    const chrome = gridBox.y - divider.y
    const height = chrome + Math.min(rows, RESULTS_MAX_ROWS + 1) * RESULTS_ROW_PX + RESULTS_ROW_PX / 2
    const targetY = Math.round(paneBottom - height)
    if (Math.abs(targetY - divider.y) < 8) return

    const x = divider.x + divider.width / 2
    await page.mouse.move(x, divider.y)
    await page.mouse.down()
    await page.mouse.move(x, targetY, {steps: 20})
    await page.mouse.up()
    await page.waitForTimeout(800)
}

/**
 * Rewind the editor to line 1. `keyboard.insertText` leaves the caret at the end
 * of the statement, so a long UDF opens scrolled to its last line.
 */
export async function scrollEditorToTop(page: Page, editor: Locator, statement?: string) {
    await focusEditor(editor)
    await page.keyboard.press('ControlOrMeta+Home')
    // Wait for the first line, as fillEditor does: the narration that follows
    // is about these lines.
    const first = statement ? outerLines(statement).first : undefined
    if (first) await waitForEditorLine(editor, first)
    await pace(page, 800)
}

/**
 * Code is unreadable on a 13" screen at 1:1, so explainCode zooms onto each
 * beat. The config records at scale 2.4 to keep this zoom pixel-sharp.
 */
export const CODE_ZOOM = 1.8

/**
 * Walks through the statement one line per beat, marking, zooming and
 * narrating each. A 45-line UDF doesn't fit a frame that shows ~35 lines.
 *
 * `match` must be a substring of a single CodeMirror line (`div.cm-line`).
 */
export async function explainCode(
    page: Page,
    ws: FrameLocator,
    // `zoomOn` names a line in the middle of a multi-line block: the block is
    // centred in the editor and zoomed on, while `match` stays the marked line.
    beats: {match: string, text: string, zoomOn?: string}[],
) {
    for (const beat of beats) {
        const line = ws.locator('.cm-line').filter({hasText: beat.match}).first()
        await line.scrollIntoViewIfNeeded({timeout: 15_000})
        const zoomTarget = beat.zoomOn ? ws.locator('.cm-line').filter({hasText: beat.zoomOn}).first() : line
        if (beat.zoomOn) await zoomTarget.evaluate((el) => el.scrollIntoView({block: 'center'}))
        await pace(page, 500)
        // Mark and zoom end with this beat's sentence. A .cm-line spans the
        // editor, so `text` zooms on the text. `start` keeps a long line's start.
        await highlight(line, {duration: 'narration'})
        await zoom(zoomTarget, CODE_ZOOM, {text: true, align: 'start'})
        await narrate(beat.text)
        await waitForNarration()
    }
}

/**
 * Waits until the editor has rendered the line containing `text`.
 *
 * `insertText` resolves before Snowsight repaints, which takes seconds for a
 * 45-line function. The renderer freezes the last frame during narration, so
 * without this wait the viewer hears about a statement not yet on screen.
 *
 * CodeMirror renders only the lines in view, so `text` must be one of them.
 */
async function waitForEditorLine(editor: Locator, text: string) {
    await editor.locator('.cm-line')
        .filter({hasText: text})
        .first()
        .waitFor({timeout: 30_000})
}

/**
 * `outerLines` picks the lines of `value` to wait for at the top and bottom of
 * the editor. Both must identify THIS statement. The literal last line is often
 * `$$;`, which the outgoing statement ends with too, so waiting for it returns
 * at once. The tail is therefore the last line with real content.
 */
const MIN_ANCHOR_LINE_CHARS = 12

const outerLines = (value: string): {first?: string, last?: string} => {
    const lines = value.split('\n').map((l) => l.trim()).filter((l) => l.length > 0)
    const substantial = lines.filter((l) => l.length >= MIN_ANCHOR_LINE_CHARS)
    return {first: lines[0], last: substantial[substantial.length - 1]}
}

/**
 * Gives the editor keyboard focus. When the main page holds focus (search box,
 * CoCo panel), focusing inside the iframe is not enough, so the iframe's window
 * is focused first. A click is only the fallback, because the empty editor's
 * suggestion buttons intercept it.
 */
export async function focusEditor(editor: Locator) {
    const focused = () => editor.evaluate((el) => {
        el.ownerDocument.defaultView?.focus()
        ;(el as HTMLElement).focus()
        return el.ownerDocument.hasFocus() && el.ownerDocument.activeElement === el
    })
    if (await focused()) return
    await editor.click({force: true})
    if (!(await focused())) throw new Error('Code editor did not take keyboard focus')
}

/** Empty the editor, so the next fillEditor() types into a blank one. */
export async function clearEditor(page: Page, editor: Locator) {
    await focusEditor(editor)
    await page.keyboard.press('ControlOrMeta+A')
    await page.keyboard.press('Delete')
    await pace(page, 300)
}

export async function fillEditor(page: Page, editor: Locator, value: string) {
    await focusEditor(editor)
    await page.keyboard.press('ControlOrMeta+A')
    // insertText lands the statement verbatim in one input event. Typing would
    // trigger auto-indent and bracket closing, which mangle the Python bodies.
    await page.keyboard.insertText(value)
    // The caret ends up at the end of the statement, so the tail is what the
    // editor is guaranteed to be showing once the repaint lands.
    const {last} = outerLines(value)
    if (last) await waitForEditorLine(editor, last)
    await pace(page, 800)
}

export async function runSelected(page: Page, ws: FrameLocator, editor: Locator) {
    // The editor holds one statement, so no selection is needed; selecting
    // would gray the text out right before the run.
    await ws.getByRole('button', {name: 'Run selected'}).click()

    // Wait for the run to clear first, or the check below reads the previous
    // statement's success message (a Python UDF takes ~a minute).
    const running = ws.getByText(/Running query|active quer(y|ies)/i).first()
    await running.waitFor({timeout: 15_000}).catch(() => {/* statement was instant */})
    await running.waitFor({state: 'hidden', timeout: 8 * 60_000}).catch(() => {/* never rendered */})

    await ws.getByText(/Statement executed|successfully|completed|0 rows|1 row|^\d+ rows/i)
        .first()
        .waitFor({timeout: 2 * 60_000})
    // The result is in the DOM before the recording has a frame of it; hold it
    // on screen, or the next narration freezes on the "Running query" frame.
    await pace(page, 1000)
    // Off camera, so the next statement's walkthrough starts with the editor
    // tall again. The cut hides the drag itself.
    await test.step('hidden - fit the results pane', () => fitResultsPane(page, ws))
}

/** The workspace iframe and its editor, with the steps' statement helpers bound to them. */
export function createWorkspace(page: Page) {
    const ws = page.frameLocator('iframe[title="Workspaces"]')
    const editor = ws.getByRole('textbox', {name: 'Code Editor'})

    // The old statement is cleared off camera, so the line plays over the new
    // one filling in, not over the previous run's frozen frame.
    const introduce = async (sql: string, text: string) => {
        await test.step('hidden - clear the editor', () => clearEditor(page, editor))
        await narrate(text)
        await fillEditor(page, editor, sql)
        // insertText leaves the caret at the end, scrolled past a long
        // statement's header; the walkthrough starts at the top.
        await scrollEditorToTop(page, editor, sql)
        await waitForNarration()
    }

    const runStatement = async (sql: string) => {
        await fillEditor(page, editor, sql)
        await runSelected(page, ws, editor)
    }

    return {ws, editor, introduce, runStatement}
}

export type Workspace = ReturnType<typeof createWorkspace>
