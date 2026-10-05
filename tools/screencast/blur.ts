import type {Page} from '@playwright/test'

type Source = {source: string, flags: string}

const toSources = (patterns: (string | RegExp)[]): Source[] => patterns.map((p) => typeof p === 'string'
    ? {source: p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags: ''}
    : {source: p.source, flags: p.flags.replace('g', '')})

// Runs in every frame. The first call adds the style and the observer that
// re-marks matching text as the page changes; later calls only add patterns.
function install(sources: Source[]) {
    type BlurState = {regexes: RegExp[], rescan: () => void}
    const w = window as unknown as {__screencastBlur?: BlurState}
    const NAME = 'screencast-blur'
    if (!w.__screencastBlur) {
        // A CSS highlight marks text ranges without touching the DOM, so React
        // pages keep working, and only the match is blurred, not its element.
        const highlight = new Highlight()
        CSS.highlights.set(NAME, highlight)
        let pending = false
        const state: BlurState = {
            regexes: [],
            rescan: () => {
                if (pending || !document.body) return
                pending = true
                // Coalesces bursts of mutations into one pass per frame.
                requestAnimationFrame(() => {
                    pending = false
                    highlight.clear()
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
                    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                        const text = node.nodeValue
                        if (!text) continue
                        for (const regex of state.regexes) {
                            regex.lastIndex = 0
                            for (let m = regex.exec(text); m; m = regex.exec(text)) {
                                if (m[0].length === 0) { regex.lastIndex++; continue }
                                const range = new Range()
                                range.setStart(node, m.index)
                                range.setEnd(node, m.index + m[0].length)
                                highlight.add(range)
                            }
                        }
                    }
                })
            },
        }
        w.__screencastBlur = state
        const start = () => {
            // Transparent text with a wide shadow: unreadable even at the
            // recording's 2.4x scale and in a zoom.
            const style = document.createElement('style')
            style.textContent = `::highlight(${NAME}) { color: transparent; text-shadow: 0 0 0.6em rgba(60, 60, 60, 0.95); }`
            document.head.append(style)
            new MutationObserver(state.rescan)
                .observe(document.body, {subtree: true, childList: true, characterData: true})
            state.rescan()
        }
        if (document.body) start()
        else document.addEventListener('DOMContentLoaded', start)
    }
    const state = w.__screencastBlur
    state.regexes.push(...sources.map((s) => new RegExp(s.source, s.flags + 'g')))
    state.rescan()
}

/**
 * Blurs every text match of a pattern, in all frames for the whole session, so
 * neither video nor screenshots show it. Only the match is blurred, e.g. the
 * name in "Good evening, Jane". A later call, e.g. for the signed-in user's
 * name, also reaches frames that are already open.
 */
export async function blurText(page: Page, patterns: (string | RegExp)[]) {
    const sources = toSources(patterns)
    await page.addInitScript(install, sources)
    for (const frame of page.frames()) {
        await frame.evaluate(install, sources).catch(() => {/* frame gone or not scriptable */})
    }
}
