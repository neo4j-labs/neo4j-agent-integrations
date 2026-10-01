import fs from 'node:fs'
import {defineConfig, type PlaywrightTestConfig} from '@playwright/test'
import {recastVideo} from 'playwright-recast/config'

// Playwright config for a screencast project. Its paths are relative, so run it
// from the project's directory.
export function screencastConfig(config: PlaywrightTestConfig = {}) {
    if (fs.existsSync('.env')) process.loadEnvFile('.env')
    return defineConfig({
        testDir: '.',
        outputDir: './playwright-output',
        // This is also the teardown budget. Teardown zips the trace (~800 MB for
        // a 15-minute recording) and ignores test.setTimeout().
        timeout: 10 * 60_000,
        ...config,
        use: {
            // Without a cap, a click blocked by a popup retries until the test
            // budget is gone, and the failure names no element.
            actionTimeout: 60_000,
            // A 1920x1080 viewport makes the UI ~1.33x larger in the 1440p render.
            // Scale 2.4 keeps the 1.8x code zoom sharp (2560 x 1.8 / 1920).
            // HEADLESS=0 is for debugging only: frames then follow the OS scale.
            ...recastVideo({viewport: {width: 1920, height: 1080}, scale: 2.4}),
            ...(process.env.HEADLESS === '0' ? {headless: false} : {}),
            trace: 'on',
            ...config.use,
        },
    })
}
