import fs from 'node:fs'
import path from 'node:path'
import type {BrowserContext} from '@playwright/test'

/** The saved Aura console session: aura-login.ts writes it, the spec loads it, step 6 renews it. */
export const AURA_STATE = path.resolve(import.meta.dirname, '.aura-state.json')

/**
 * Saves the context's Aura and Google sign-in. Snowflake's is left out: with
 * it, Snowsight skips the sign-in form that the hidden login step fills in.
 */
export async function saveAuraState(context: BrowserContext) {
    const state = await context.storageState()
    const isSnowflake = (host: string) => /snowflake(computing)?\.com$/.test(host.replace(/^\./, ''))
    fs.writeFileSync(AURA_STATE, JSON.stringify({
        cookies: state.cookies.filter((c) => !isSnowflake(c.domain)),
        origins: state.origins.filter((o) => !isSnowflake(new URL(o.origin).host)),
    }, null, 2))
}
