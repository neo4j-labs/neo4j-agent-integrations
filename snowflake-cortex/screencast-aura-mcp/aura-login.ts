// Saves an Aura console session for this screencast. Google sign-in
// can't be scripted, so you sign in once by hand in the window this opens.
// Run again when the session expires.
import {chromium} from '@playwright/test'
import {AURA_STATE, saveAuraState} from './aura-state.ts'

const browser = await chromium.launch({
    headless: false,
    // Google refuses sign-in in a browser that announces automation.
    ignoreDefaultArgs: ['--enable-automation'],
    args: ['--disable-blink-features=AutomationControlled'],
})
const context = await browser.newContext()
const page = await context.newPage()
await page.goto('https://console.neo4j.io/')
console.log('Sign in to the Aura console in the browser window. Waiting up to 5 minutes...')
// The project's instance list appears only once signed in.
await page.getByText('Instances', {exact: true}).first().waitFor({timeout: 5 * 60_000})
await page.waitForTimeout(3000)
await saveAuraState(context)
console.log(`Saved ${AURA_STATE}`)
await browser.close()
