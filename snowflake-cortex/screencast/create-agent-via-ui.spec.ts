import {test} from '@playwright/test'
import {setupRecast} from 'playwright-recast'
import {blurText} from '../../tools/screencast/blur.ts'
import path from 'node:path'
import {createNarration} from '../../tools/screencast/narration.ts'
import {createGuideShots} from '../../tools/screencast/screenshot.ts'
import {openAgentIfShortened} from './snowsight/agent-studio.ts'
import {dismissPopups, installPopupHandlers} from './snowsight/popups.ts'
import {createWorkspace} from './snowsight/workspace.ts'
import type {Ctx} from './steps/context.ts'
import * as session from './steps/session.ts'
import {intro} from './steps/intro.ts'
import * as access from './steps/access.ts'
import * as connectivity from './steps/connectivity.ts'
import * as functions from './steps/functions.ts'
import * as agent from './steps/agent.ts'

// hoverDwellMs lets Snowsight paint its hover styling, so the viewer sees what
// is about to be clicked. narrationSettleMs lets the recording catch up with
// the page before a narration hold freezes it.
setupRecast(test, {clickSettleMs: 700, hoverDwellMs: 450, narrationSettleMs: 500})

// A per-step budget, because the step wrapper extends the timeout by each step's runtime.
const STEP_BUDGET_MS = 60_000

test('test', async ({page}) => {
    test.setTimeout(STEP_BUDGET_MS)
    // The personal database USER$... carries the user's name. SCREENCAST_BLUR
    // in .env adds account-specific text, e.g. the account locator.
    await blurText(page, [/USER\$\w+/, ...(process.env.SCREENCAST_BLUR?.split(',').filter(Boolean) ?? [])])
    await installPopupHandlers(page)

    const ctx: Ctx = {
        page,
        ...createNarration(page, {before: () => dismissPopups(page), fullRunOnly: ['hidden - cleanup']}),
        ...createWorkspace(page),
        openAgentIfShortened: (tab, always) => openAgentIfShortened(page, tab, always),
        shot: createGuideShots(path.resolve(import.meta.dirname, '../samples/2-snowsight/images')),
        snowflakeUser: '',
    }

    await session.login(ctx)
    await session.drainAnnouncements(ctx)
    await session.readUser(ctx)
    // The username is known only after sign-in. It shows up in the role grant
    // and the account menu.
    await blurText(page, [new RegExp(ctx.snowflakeUser.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i')])
    await session.cleanup(ctx)

    await intro(ctx)
    await access.createDatabaseAndSchema(ctx)
    await access.createRole(ctx)
    await access.grantAccess(ctx)
    await connectivity.createSecret(ctx)
    await connectivity.createNetworkRule(ctx)
    await connectivity.createIntegration(ctx)
    await functions.createModelStage(ctx)
    await functions.createPythonUdfs(ctx)
    await functions.createToolFunctions(ctx)
    await agent.createAgent(ctx)
    await agent.addTools(ctx)
    await agent.publishAgent(ctx)
    await agent.askAgent(ctx)
})
