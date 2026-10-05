# Screencast kit

This kit records narrated screencasts of the integrations with Playwright and renders them with [playwright-recast](https://github.com/ThePatriczek/playwright-recast). Each screencast lives in `<integration>/screencast/`.

The kit exists only on the `screencasts` branch. See [Branch workflow](#branch-workflow).

| File | What it provides |
| --- | --- |
| `config.ts` | `screencastConfig()` returns the Playwright config: viewport, recording scale, trace, video, `.env` and `HEADLESS=0`. |
| `test.ts` | `test`, Playwright's with playwright-recast's `recastPageVideos` fixture: it records which page each video belongs to, so popups and other tabs reach the video. Specs import it instead of `@playwright/test`'s. |
| `render.ts` | `renderScreencasts()` renders the narrated video. |
| `blur.ts` | `blurText()` blurs matching text in the page. You can add patterns at any time, for example after sign-in. |
| `screenshot.ts` | `createGuideShots()` takes screenshots for a guide, cropped to an element. |
| `sync-readme.ts` | `syncCodeBlocks()` fills the marked code blocks of a Markdown file from their source. |
| `narration.ts` | `createNarration()` returns the step wrapper and the narration helpers (`say`, `narrateDuring`, `markAndSay`, typing). It also has `zoomDialog` and `scrollIntoViewVisibly`. |
| `voices/` | The default narrator voice sample. |

## Setup

1. Run `npm ci` in the repository root. All screencasts share one `node_modules` through npm workspaces.
2. Create a Python environment for the voice: `python3 -m venv ~/.venvs/playwright-recast`
3. Install its packages: `~/.venvs/playwright-recast/bin/pip install -r node_modules/playwright-recast/dist/voiceover/providers/qwen-sidecar/requirements.txt`

## New screencast

Add `<integration>/screencast/` to `workspaces` in the root `package.json`. Then create these two files:

```ts
// playwright.config.ts
import {screencastConfig} from '../../tools/screencast/config.ts'
export default screencastConfig()
```

```ts
// render.ts
import {renderScreencasts} from '../../tools/screencast/render.ts'
await renderScreencasts()
```

Run these commands in the screencast's directory:

| Command | What it does |
| --- | --- |
| `npx playwright test` | Records into `playwright-output/`. |
| `node render.ts` | Renders `screencast-output/<test>.mp4`. |
| `OUTPUT_NAME=x node render.ts` | Renders to `x.mp4` instead. |
| `ONLY_STEPS=2,3 npx playwright test` | Records only the listed steps. See `narration.ts`. |
| `HEADLESS=0 npx playwright test` | Shows the browser, for debugging. The frames then follow the display scale of your OS. |

The render cuts steps whose name starts with `hidden - `.

Do not run other tests in the same directory. Playwright empties `playwright-output/` on every run, which deletes the last recording. Pass `--output=<dir>` for other runs.

`renderScreencasts()` takes these options:

| Option | Default |
| --- | --- |
| `voice: {sample, transcript}` | `voices/female-voice.wav`. For your own voice, pass a short, clean WAV recording and its exact transcript. |
| `clickSound` | `true`, which is playwright-recast's click. Pass a sound file, or `false` for no sound. |
| `clickVolume` | `0.2`, a quarter of playwright-recast's default. |
| `textRules` | Extra rules for the spoken text. |
| `urlBar` | playwright-recast's URL pill, e.g. `{show: 'host-change', redact: [...]}`. Without it, the pill shows only at `showUrl()` markers. |

CI (`.github/workflows/screencasts.yml`) runs the `typecheck` script of each workspace. It also runs `readme:check` where a workspace defines it.

## Branch workflow

`screencasts` is `main` plus added files. It never edits a file that `main` owns, so `main` merges into it without conflicts. Guides, images and integration code belong to `main`.

| Step | Branch | Action |
| --- | --- | --- |
| 1. Change the integration or its guide. | A feature branch, then a PR to `main` | Work as usual. |
| 2. Update the screencasts branch. | `screencasts` | Run `git merge origin/main`. CI's `readme:check` then flags guides that no longer match `stack.ts`. |
| 3. Sync the guide and record. | `screencasts` | Run `npm run readme`, `npx playwright test` and `node render.ts`. |
| 4. Hand the guide back. | A branch from `main`, then a PR to `main` | Run `git checkout origin/screencasts -- <guide>/README.md <guide>/images`. The next step 2 makes both branches equal again. |
| 5. Publish the video. | - | Upload the video. The guide on `main` holds the link. |

- Merge `main` into `screencasts`; don't rebase. The branch is shared, and a rebase needs a force push.
- Between steps 3 and 4, both branches change the guide. Finish step 4 before the guide changes on `main` again.
