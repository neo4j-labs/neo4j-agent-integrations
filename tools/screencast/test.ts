import {test as base} from '@playwright/test'
import {recastPageVideos} from 'playwright-recast/helpers'

/**
 * Playwright's `test`, plus a trace step that says which page each video
 * belongs to, so the renderer composites popups and other tabs. Use it instead
 * of @playwright/test's `test`, and extend it before any other `context`
 * override: recastPageVideos wraps `context`, and an earlier override's pages
 * would be missed.
 */
export const test = base.extend(recastPageVideos)

export {expect} from '@playwright/test'
