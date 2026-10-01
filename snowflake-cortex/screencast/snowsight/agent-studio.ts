// Agent Studio's "Add custom tool" dialog.
import {expect, test, type Locator, type Page} from '@playwright/test'
import {click, highlight, narrate, pace, waitForNarration} from 'playwright-recast'
import {ONLY_STEPS, scrollIntoViewVisibly, zoomDialog, type Narration} from '../../../tools/screencast/narration.ts'
import {AGENT_DISPLAY_NAME, type AgentToolSpec} from '../stack.ts'
import {openNavItem, pickDatabaseAndSchema} from './catalog.ts'

/** A tool from the agent spec, with what is spoken while its dialog is filled in. */
export type AgentTool = AgentToolSpec & {
    narration: string,
    /** Spoken while the optional parameters are marked and unticked. */
    optionalNarration?: string,
    /** Spoken while a pre-filled argument the tool leaves out is removed. */
    removeNarration?: string,
}

/** Add the Cortex Analyst tool over a semantic view: Tools > Query structured data. */
export async function addAnalystTool(
    page: Page,
    tool: {name: string, description: string, semanticView: string},
    helpers: Pick<Narration, 'fill' | 'fillInstantly'>,
    narration: {open: string, details: string},
) {
    await narrate(narration.open)
    await click(page.getByRole('button', {name: 'Add semantic view'}))
    await click(page.getByRole('menuitem', {name: 'Add semantic view'}))
    const dialog = page.getByRole('dialog', {name: 'Add tool: Cortex Analyst'})
    await dialog.waitFor({timeout: 30_000})
    // A zoom starts with the current narration. Set during the line above, it
    // would move the camera before the dialog opens and clip the menu.
    await waitForNarration()
    await zoomDialog(page, dialog)
    await click(dialog.getByRole('button', {name: /^Database/}))
    await pickDatabaseAndSchema(page)
    await click(dialog.getByRole('button', {name: /Select semantic view/}))
    await click(page.getByRole('option', {name: tool.semanticView, exact: true}))
    await waitForNarration()
    await narrate(narration.details)
    await scrollIntoViewVisibly(page, dialog.getByRole('textbox', {name: 'Name'}))
    await helpers.fill(dialog.getByRole('textbox', {name: 'Name'}), tool.name)
    await scrollIntoViewVisibly(page, dialog.getByRole('textbox', {name: 'Description'}))
    await helpers.fillInstantly(dialog.getByRole('textbox', {name: 'Description'}), tool.description)
    await scrollIntoViewVisibly(page, dialog.getByRole('spinbutton', {name: 'Query timeout'}))
    await dialog.getByRole('spinbutton', {name: 'Query timeout'}).fill('60')
    await waitForNarration()
    await click(dialog.getByRole('button', {name: 'Add', exact: true}))
    await dialog.waitFor({state: 'hidden', timeout: 60_000})
    await pace(page, 1200)
}

// Picking the identifier makes Snowsight pre-create one parameter row per
// argument, in its own order, so rows are matched by name. We add descriptions
// and untick "Required" where SQL has a default.
export async function addCustomTool(
    page: Page,
    tool: AgentTool,
    helpers: Pick<Narration, 'fill' | 'fillInstantly'>,
    // Runs after the identifier is picked, before the fields are filled, e.g. for the screenshot.
    opts: {onIdentifier?: (dialog: Locator) => Promise<void>} = {},
) {
    await click(page.getByRole('button', {name: 'Add', exact: true}).last())
    const dialog = page.getByRole('dialog', {name: 'Add custom tool'})
    await dialog.waitFor({timeout: 30_000})
    await zoomDialog(page, dialog)

    // Resource type defaults to `procedure`; our tools are functions.
    await click(dialog.getByRole('button', {name: /Resource type/}))
    await click(page.getByRole('option', {name: 'function', exact: true}))

    await click(dialog.getByRole('button', {name: /^Database/}))
    await pickDatabaseAndSchema(page)

    // Right after the functions were created, the list can open empty.
    const identifier = page.getByRole('option', {name: tool.identifier})
    await expect(async () => {
        if (!(await identifier.isVisible())) await click(dialog.getByRole('button', {name: /Custom tool identifier/}))
        await expect(identifier).toBeVisible({timeout: 5_000})
    }).toPass({timeout: 60_000})
    await click(identifier)
    // Snowsight fetches the signature and rebuilds the parameter rows.
    await dialog.getByRole('textbox', {name: 'Parameter'}).first().waitFor({timeout: 30_000})
    await pace(page, 1000)
    await opts.onIdentifier?.(dialog)

    await scrollIntoViewVisibly(page, dialog.getByRole('textbox', {name: 'Name'}))
    await helpers.fill(dialog.getByRole('textbox', {name: 'Name'}), tool.name)
    // query_timeout: 60, as in the terraform tool_resources block.
    await scrollIntoViewVisibly(page, dialog.getByRole('spinbutton', {name: 'Query timeout'}))
    await dialog.getByRole('spinbutton', {name: 'Query timeout'}).fill('60')
    // The tool description is the first "Description" box in the dialog; the
    // ones after it belong to the parameter rows.
    await scrollIntoViewVisibly(page, dialog.getByRole('textbox', {name: 'Description'}).first())
    await helpers.fillInstantly(dialog.getByRole('textbox', {name: 'Description'}).first(), tool.description)

    const parameterNames = dialog.getByRole('textbox', {name: 'Parameter'})
    const descriptions = dialog.getByRole('textbox', {name: 'Description'})
    const required = dialog.getByRole('checkbox', {name: 'Required'})
    // Removes arguments the tool leaves out, e.g. QUERY_NEO4J's optional PARAMS,
    // so the SQL default applies. Last first keeps the earlier indices valid.
    for (let i = await parameterNames.count() - 1; i >= 0; i--) {
        const name = await parameterNames.nth(i).inputValue()
        if (tool.params.some((p) => p.name.toLowerCase() === name.toLowerCase())) continue
        const remove = dialog.getByRole('button', {name: 'Delete parameter'}).nth(i)
        await scrollIntoViewVisibly(page, remove)
        if (tool.removeNarration) {
            await waitForNarration()
            await highlight(parameterNames.nth(i), {duration: 'narration'})
            await narrate(tool.removeNarration)
            await waitForNarration()
        }
        await click(remove)
        await pace(page, 800)
    }
    const parameterCount = await parameterNames.count()
    let explainingOptional = false
    for (let i = 0; i < parameterCount; i++) {
        const name = await parameterNames.nth(i).inputValue()
        const param = tool.params.find((p) => p.name.toLowerCase() === name.toLowerCase())
        if (!param) {
            throw new Error(`tool ${tool.name}: no configuration for parameter "${name}"`)
        }
        await scrollIntoViewVisibly(page, descriptions.nth(i + 1))
        await helpers.fillInstantly(descriptions.nth(i + 1), param.description)
        if (!param.required && await required.nth(i).isChecked()) {
            // The checkbox input sits under a custom-styled overlay that eats
            // pointer events; its label is the clickable surface.
            const requiredLabel = required.nth(i).locator('xpath=ancestor::label[1]')
            await scrollIntoViewVisibly(page, requiredLabel)
            if (tool.optionalNarration && !explainingOptional) {
                // The tool's own line ends here; the optional parameters get
                // theirs while they are marked and unticked.
                await waitForNarration()
                await zoomDialog(page, dialog)
                await highlight(requiredLabel, {duration: 'narration'})
                await narrate(tool.optionalNarration)
                explainingOptional = true
            }
            await click(requiredLabel)
        }
    }
    if (explainingOptional) await waitForNarration()

    await click(dialog.getByRole('button', {name: 'Add', exact: true}))
    await dialog.waitFor({state: 'hidden', timeout: 60_000})
    await pace(page, 1200)
}

// Opens the agent page off camera: an ONLY_STEPS run does not arrive there from
// the step before. `always` also reopens it in a full run.
export async function openAgentIfShortened(page: Page, tab?: string, always = false) {
    if (!ONLY_STEPS && !always) return
    await test.step('hidden - open the agent', async () => {
        // A reload drops Snowsight's per-session object cache: without it,
        // functions created earlier in the session never reach the custom
        // tool identifier dropdown.
        if (always) await page.reload()
        await openNavItem(page, 'AI & ML', /^(Agents|Agent Studio)/)
        await page.getByRole('row', {name: new RegExp(AGENT_DISPLAY_NAME)}).first().click()
        await page.getByRole('tab', {name: 'Preview'}).waitFor({timeout: 60_000})
        if (tab) await page.getByRole('tab', {name: tab}).click()
    })
}
