import type {FrameLocator, Locator, Page} from '@playwright/test'
import type {Narration} from '../../../tools/screencast/narration.ts'
import type {GuideShot} from '../../../tools/screencast/screenshot.ts'
import type {Workspace} from '../snowsight/workspace.ts'

/** What every step works with: the page, the narration helpers and the workspace editor. */
export type Ctx = Narration & Workspace & {
    page: Page,
    ws: FrameLocator,
    editor: Locator,
    openAgentIfShortened: (tab?: string, always?: boolean) => Promise<void>,
    /** A screenshot for samples/2-snowsight/README.md */
    shot: GuideShot,
    /** The signed-in Snowflake username, read after login */
    snowflakeUser: string,
}
