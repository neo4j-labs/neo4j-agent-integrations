import fs from 'node:fs'
import path from 'node:path'
import {test} from '../../tools/screencast/test.ts'
import {setupRecast} from 'playwright-recast'
import {blurText} from '../../tools/screencast/blur.ts'
import {createNarration} from '../../tools/screencast/narration.ts'
import {createGuideShots} from '../../tools/screencast/screenshot.ts'
import {dismissPopups, installPopupHandlers} from '../screencast/snowsight/popups.ts'
import {createWorkspace} from '../screencast/snowsight/workspace.ts'
import * as session from '../screencast/steps/session.ts'
import {AURA_STATE} from './aura-state.ts'
import {GUIDE_IMAGES, type Ctx} from './steps/context.ts'
import {cleanup, readFirstName} from './steps/session.ts'
import {findMcpUrl, intro} from './steps/aura.ts'
import {createIntegration, createMcpServer} from './steps/snowflake.ts'
import {createAgent, publishAgent} from './steps/agent.ts'
import {askAgent, connectMcpServer} from './steps/cowork.ts'

if (!fs.existsSync(AURA_STATE)) throw new Error(`${AURA_STATE} missing; run npm run aura-login first`)

setupRecast(test, {clickSettleMs: 700, hoverDwellMs: 450, narrationSettleMs: 500})
// The Aura console and Aura's OAuth sign-in reuse this Google session.
test.use({storageState: AURA_STATE})

const STEP_BUDGET_MS = 60_000
// Covers every email address: Aura's and Google's sign-in pages show the account.
const EMAIL = /[\w.+-]+@[\w-]+(\.[\w-]+)+/
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

test('aura-mcp', async ({page}) => {
    test.setTimeout(STEP_BUDGET_MS)
    const mcpUrl = process.env.AURA_MCP_URL
    if (!mcpUrl) throw new Error('AURA_MCP_URL not set (see .env.example)')
    const blur: (string | RegExp)[] = [EMAIL, /USER\$\w+/, ...(process.env.SCREENCAST_BLUR?.split(',').filter(Boolean) ?? [])]
    await blurText(page, blur)
    await installPopupHandlers(page)

    const ctx: Ctx = {
        page,
        ...createNarration(page, {before: () => dismissPopups(page), fullRunOnly: ['hidden - cleanup']}),
        ...createWorkspace(page),
        openAgentIfShortened: async () => {/* every step opens what it needs */},
        shot: createGuideShots(GUIDE_IMAGES),
        snowflakeUser: '',
        mcpUrl,
        blur,
    }

    await session.login(ctx)
    await session.drainAnnouncements(ctx)
    await session.readUser(ctx)
    const firstName = await readFirstName(ctx)
    // Only the first name is known here; CoWork and the consent screen add the
    // last name, so a capitalized word right after it goes too.
    const names = [
        new RegExp(escape(ctx.snowflakeUser), 'i'),
        ...(firstName ? [new RegExp(`${escape(firstName)}(\\s+\\p{Lu}[\\p{L}'-]+)?`, 'u')] : []),
    ]
    blur.push(...names)
    await blurText(page, names)
    await cleanup(ctx)

    await intro(ctx)
    await findMcpUrl(ctx)
    await createIntegration(ctx)
    await createMcpServer(ctx)
    await createAgent(ctx)
    await publishAgent(ctx)
    await connectMcpServer(ctx)
    await askAgent(ctx)
})
