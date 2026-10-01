// A stage's file upload dialog.
import type {Locator, Page} from '@playwright/test'
import {click, pace} from 'playwright-recast'

/**
 * Fills in and submits the stage-upload modal and returns it without waiting
 * for the transfer, which runs for minutes: the caller waits in a hidden step.
 */
export async function startStageUpload(
    page: Page,
    files: readonly string[],
    stagePath: string,
    // `beforeUpload` runs once files and path are set, e.g. for the screenshot.
    opts?: {quiet?: boolean, beforeUpload?: (modal: Locator) => Promise<void>},
): Promise<Locator> {
    // `quiet`: plain Playwright calls, for passes inside a hidden step, where
    // click markers, hover dwell and typing cadence are never seen.
    const quiet = opts?.quiet ?? false

    // The pattern also matches the old label. After a large upload, the button
    // stays unclickable until the stage view settles.
    const addFiles = page.getByRole('button', {name: /^(Upload Files|Add files to stage)/})
    if (quiet) {
        await addFiles.click({timeout: 5 * 60_000})
    } else {
        await click(addFiles)
    }
    const modal = page.getByRole('dialog', {name: /Upload Your Files/})

    // The modal's own Browse button, not a bare input[type=file]: the page has
    // an unrelated "import notebook" file input too.
    const [chooser] = await Promise.all([
        page.waitForEvent('filechooser'),
        modal.getByRole('button', {name: /browse files/i}).click(),
    ])
    await chooser.setFiles([...files])

    // One pass per folder, e.g. "minilm/1_Pooling", keeps Terraform's nested layout.
    const pathInput = modal.getByRole('textbox', {name: 'stage path input'})
    const uploadButton = modal.getByRole('button', {name: 'Upload', exact: true})
    if (quiet) {
        await pathInput.fill(stagePath)
        await uploadButton.click()
    } else {
        await fillField(page, pathInput, stagePath)
        await opts?.beforeUpload?.(modal)
        await click(uploadButton)
    }
    return modal
}

async function fillField(page: Page, locator: Locator, text: string) {
    await click(locator)
    await page.keyboard.press('ControlOrMeta+A')
    await locator.pressSequentially(text, {delay: 30})
    await pace(page, 1000)
}
