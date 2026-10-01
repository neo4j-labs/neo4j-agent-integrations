import fs from 'node:fs'
import path from 'node:path'
import type {Locator} from '@playwright/test'

/**
 * Screenshots for a hand-written guide, taken while the screencast records.
 * `shot(dialog, 'grant-dialog')` writes `<dir>/grant-dialog.png`, cropped to
 * the element or the union of several. The crop keeps account names and the
 * rest of the page out. Zoom and highlights are added at render time, so they
 * never appear here.
 */
export function createGuideShots(dir: string, opts: {padding?: number} = {}) {
    const padding = opts.padding ?? 16
    fs.mkdirSync(dir, {recursive: true})
    return async (target: Locator | Locator[], name: string) => {
        const file = path.join(dir, `${name}.png`)
        const targets = Array.isArray(target) ? target : [target]
        if (targets.length === 1 && padding === 0) {
            await targets[0]!.screenshot({path: file, animations: 'disabled'})
            return
        }
        // A missing element narrows the crop instead of failing the recording.
        const boxes = (await Promise.all(targets.map((t) => t.boundingBox({timeout: 5_000}).catch(() => null))))
            .filter((b) => b !== null)
        if (boxes.length === 0) throw new Error(`screenshot ${name}: no target is visible`)
        const page = targets[0]!.page()
        const viewport = page.viewportSize()!
        const x = Math.max(0, Math.min(...boxes.map((b) => b.x)) - padding)
        const y = Math.max(0, Math.min(...boxes.map((b) => b.y)) - padding)
        const right = Math.min(viewport.width, Math.max(...boxes.map((b) => b.x + b.width)) + padding)
        const bottom = Math.min(viewport.height, Math.max(...boxes.map((b) => b.y + b.height)) + padding)
        await page.screenshot({path: file, clip: {x, y, width: right - x, height: bottom - y}, animations: 'disabled'})
    }
}

export type GuideShot = ReturnType<typeof createGuideShots>
