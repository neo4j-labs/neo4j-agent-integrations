import {spawnSync} from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import type {Locator} from '@playwright/test'

/** Width and height of a PNG, from its IHDR chunk. */
const pngSize = (png: Buffer) => ({width: png.readUInt32BE(16), height: png.readUInt32BE(20)})

/**
 * Screenshots for a hand-written guide, taken while the screencast records.
 * `shot(dialog, 'grant-dialog')` writes `<dir>/grant-dialog.png`, cropped to
 * the element or the union of several. The crop keeps account names and the
 * rest of the page out. Zoom and highlights are added at render time, so they
 * never appear here.
 *
 * The page is shot whole and cropped with ffmpeg afterwards: a clip or element
 * screenshot makes Chromium redraw the page at the clip's size, and the
 * recording catches gray frames of it. A full-viewport shot doesn't.
 */
export function createGuideShots(dir: string, opts: {padding?: number} = {}) {
    const padding = opts.padding ?? 16
    fs.mkdirSync(dir, {recursive: true})
    return async (target: Locator | Locator[], name: string) => {
        const file = path.join(dir, `${name}.png`)
        const targets = Array.isArray(target) ? target : [target]
        const page = targets[0]!.page()
        // The shot comes first: `animations: 'disabled'` fast-forwards running
        // animations, so boxes measured before it can point at where a
        // sliding card was, not where it is in the image.
        const png = await page.screenshot({animations: 'disabled'})
        // A missing element narrows the crop instead of failing the recording.
        const boxes = (await Promise.all(targets.map((t) => t.boundingBox({timeout: 5_000}).catch(() => null))))
            .filter((b) => b !== null)
        if (boxes.length === 0) throw new Error(`screenshot ${name}: no target is visible`)
        // innerWidth, not viewportSize(): a popup's window can differ from the context's viewport.
        const viewport = await page.evaluate(() => ({width: innerWidth, height: innerHeight}))
        const scale = pngSize(png).width / viewport.width
        const x = Math.max(0, Math.min(...boxes.map((b) => b.x)) - padding)
        const y = Math.max(0, Math.min(...boxes.map((b) => b.y)) - padding)
        const right = Math.min(viewport.width, Math.max(...boxes.map((b) => b.x + b.width)) + padding)
        const bottom = Math.min(viewport.height, Math.max(...boxes.map((b) => b.y + b.height)) + padding)
        // SCREENCAST_DEBUG_SHOTS=1 logs the numbers behind each crop.
        if (process.env.SCREENCAST_DEBUG_SHOTS) {
            console.log(`shot ${name}: viewport ${JSON.stringify(viewport)} png ${JSON.stringify(pngSize(png))} ` +
                `crop ${JSON.stringify({x, y, right, bottom})} boxes ${JSON.stringify(boxes)}`)
        }
        const px = (v: number) => Math.round(v * scale)
        const crop = `crop=${px(right - x)}:${px(bottom - y)}:${px(x)}:${px(y)}`
        const result = spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'png_pipe', '-i', '-', '-vf', crop, file], {input: png})
        if (result.status !== 0) throw new Error(`screenshot ${name}: ffmpeg ${crop} failed: ${result.stderr}`)
    }
}

export type GuideShot = ReturnType<typeof createGuideShots>
