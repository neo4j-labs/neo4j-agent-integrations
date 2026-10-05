// Opens a visible browser with the saved Aura session, for looking around in
// the Aura console by hand. Closes when the window is closed.
import {chromium} from '@playwright/test'
import {AURA_STATE} from './aura-state.ts'

const browser = await chromium.launch({
    // The installed Google Chrome: no browser download needed for a quick look.
    channel: 'chrome',
    headless: false,
    // Google refuses sign-in in a browser that announces automation.
    ignoreDefaultArgs: ['--enable-automation'],
    args: ['--disable-blink-features=AutomationControlled'],
})
const context = await browser.newContext({storageState: AURA_STATE, viewport: null})
const page = await context.newPage()
await page.goto('https://console.neo4j.io/')
console.log('Browser open. Close the window to quit.')
await new Promise<void>((resolve) => browser.on('disconnected', () => resolve()))
