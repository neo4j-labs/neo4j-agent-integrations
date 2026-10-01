// The opening line, spoken over the home page.
import {test} from '@playwright/test'
import {narrate, pace, waitForNarration} from 'playwright-recast'
import type {Ctx} from './context.ts'

export async function intro(ctx: Ctx) {
    const {page, step} = ctx
    await step("intro", async () => {
        // goto() returns before Snowsight has painted the home page; loading it
        // off camera keeps the wait out of the video.
        await test.step('hidden - open the home page', async () => {
            await page.goto('https://app.snowflake.com/')
            await page.getByRole('link', {name: 'Catalog', exact: true}).waitFor({timeout: 60_000})
            await pace(page, 2500)
        })
        await narrate(
            "This screencast will show, how we'll wire up a Cortex Agent in Snowsight that reasons over a Neo4j graph.",
        )
        await waitForNarration()
    })
}
