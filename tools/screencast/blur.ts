import type {Page} from '@playwright/test'

type Source = {source: string, flags: string}

const toSources = (patterns: (string | RegExp)[]): Source[] => patterns.map((p) => typeof p === 'string'
    ? {source: p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags: ''}
    // A global regex keeps state between test() calls.
    : {source: p.source, flags: p.flags.replace('g', '')})

// Runs in every frame. The first call adds the style and the observer that
// blurs matching text as it appears; later calls only add patterns.
function install(sources: Source[]) {
    type BlurState = {regexes: RegExp[], scan: (root: Node) => void}
    const w = window as unknown as {__screencastBlur?: BlurState}
    const ATTR = 'data-screencast-blur'
    if (!w.__screencastBlur) {
        const state: BlurState = {
            regexes: [],
            scan: (root: Node) => {
                const matches = (text: string | null) => !!text && state.regexes.some((r) => r.test(text))
                if (root.nodeType === Node.TEXT_NODE) {
                    if (matches(root.nodeValue)) root.parentElement?.setAttribute(ATTR, '')
                    return
                }
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
                for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                    if (matches(node.nodeValue)) node.parentElement?.setAttribute(ATTR, '')
                }
            },
        }
        w.__screencastBlur = state
        const start = () => {
            // An attribute rather than an inline style: React re-renders
            // rewrite className and style, but leave unknown attributes alone.
            const style = document.createElement('style')
            style.textContent = `[${ATTR}] { filter: blur(6px) !important; }`
            document.head.append(style)
            state.scan(document.body)
            new MutationObserver((mutations) => {
                for (const m of mutations) {
                    if (m.type === 'characterData') state.scan(m.target)
                    else m.addedNodes.forEach(state.scan)
                }
            }).observe(document.body, {subtree: true, childList: true, characterData: true})
        }
        if (document.body) start()
        else document.addEventListener('DOMContentLoaded', start)
    }
    const state = w.__screencastBlur
    state.regexes.push(...sources.map((s) => new RegExp(s.source, s.flags)))
    if (document.body) state.scan(document.body)
}

/**
 * Blurs every element whose own text matches a pattern, in all frames for the
 * whole session, so neither video nor screenshots show it. A later call, e.g.
 * for the signed-in user's name, also reaches frames that are already open.
 */
export async function blurText(page: Page, patterns: (string | RegExp)[]) {
    const sources = toSources(patterns)
    await page.addInitScript(install, sources)
    for (const frame of page.frames()) {
        await frame.evaluate(install, sources).catch(() => {/* frame gone or not scriptable */})
    }
}
