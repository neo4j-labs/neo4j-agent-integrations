import path from 'node:path'
import type {Ctx as SnowsightCtx} from '../../screencast/steps/context.ts'

/** The guide's screenshots: `shot` writes here, and so do the popup's element shots. */
export const GUIDE_IMAGES = path.resolve(import.meta.dirname, '../../samples/3-aura-mcp/images')

/** Sample 2's step context, plus the Aura instance's MCP URL and the blur patterns. `shot` writes to samples/3-aura-mcp/images/. */
export type Ctx = SnowsightCtx & {
    mcpUrl: string,
    /** Every blur pattern of the page, for popups, which don't inherit them */
    blur: (string | RegExp)[],
}
