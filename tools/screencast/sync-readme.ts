import fs from 'node:fs'

/**
 * Fills the marked blocks of a hand-written Markdown file from their source,
 * so code in a guide can't drift from the code that runs:
 *
 *     <!-- code: NAME -->
 *     ```sql
 *     (replaced with blocks.NAME)
 *     ```
 *     <!-- /code -->
 *
 * `<!-- text: NAME -->` ... `<!-- /text -->` holds plain Markdown instead.
 * The fence's language is kept, and nothing outside the markers changes.
 * With `check`, the file is not written, and `changed` says if it is stale.
 */
export function syncCodeBlocks(file: string, blocks: Record<string, string>, opts: {check?: boolean} = {}) {
    const before = fs.readFileSync(file, 'utf8')
    const used = new Set<string>()
    const after = before.replace(
        /(<!-- code: ([\w:.-]+) -->\n)(`{3,})([^\n]*)\n[\s\S]*?\n\3\n(<!-- \/code -->)/g,
        (_all, open: string, name: string, _fence: string, lang: string, close: string) => {
            const code = blocks[name]
            if (code === undefined) throw new Error(`${file}: no block named ${name}`)
            used.add(name)
            // The fence must be longer than any backtick run inside the code.
            const ticks = '`'.repeat(Math.max(3, ...[...code.matchAll(/`+/g)].map((m) => m[0].length + 1)))
            return `${open}${ticks}${lang}\n${code}\n${ticks}\n${close}`
        },
    ).replace(
        /(<!-- text: ([\w:.-]+) -->\n)[\s\S]*?\n?(<!-- \/text -->)/g,
        (_all, open: string, name: string, close: string) => {
            const text = blocks[name]
            if (text === undefined) throw new Error(`${file}: no block named ${name}`)
            used.add(name)
            return `${open}${text}\n${close}`
        },
    )
    const unused = Object.keys(blocks).filter((name) => !used.has(name))
    if (!opts.check && after !== before) fs.writeFileSync(file, after)
    return {changed: after !== before, unused}
}

/** CLI wrapper: `--check` exits 1 when the file is out of date. */
export function syncCodeBlocksCli(file: string, blocks: Record<string, string>) {
    const check = process.argv.includes('--check')
    const {changed, unused} = syncCodeBlocks(file, blocks, {check})
    if (unused.length > 0) console.warn(`${file}: blocks without a marker: ${unused.join(', ')}`)
    if (check && changed) {
        console.error(`${file} is out of date; run without --check to update it`)
        process.exit(1)
    }
    console.log(`${file}: ${changed ? (check ? 'out of date' : 'updated') : 'up to date'}`)
}
