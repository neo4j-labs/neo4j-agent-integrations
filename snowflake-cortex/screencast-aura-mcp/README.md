# Screencast: Aura MCP

This screencast records [sample 3](../samples/3-aura-mcp/README.md) in the Aura console, Snowsight and Snowflake CoWork, including Aura's OAuth popup. It renders the narrated [video](https://youtu.be/y7-blfjETFw) with the [screencast kit](../../tools/screencast/README.md).

The sample's guide is written by hand. The screencast keeps two parts of it up to date:

- A recording writes the screenshots to `../samples/3-aura-mcp/images/`.
- `npm run readme` fills the marked code blocks from `stack.ts`.

## Layout

| Path | What it holds |
| --- | --- |
| `aura-mcp.spec.ts` | The test. It signs in, runs the cleanup, then the steps in order. |
| `stack.ts` | Names, SQL statements and the question for the agent. |
| `steps/` | The recorded steps and their narration: Aura console, Snowsight SQL, Agent Studio, CoWork. |
| `aura-login.ts` | Saves the Aura console session, see [Setup](#setup). |
| `aura-browser.ts` | Opens a browser with the saved session, to look around in the Aura console. |
| `aura-state.ts` | Path of the saved session, and saving it without Snowflake's cookies. |
| `readme.ts` | Fills the marked code blocks of the guide. |

The Snowsight helpers and the Snowflake sign-in come from [sample 2's screencast](../screencast/README.md).

## Setup

1. Follow the kit's [setup](../../tools/screencast/README.md#setup).
2. Fill in `../screencast/.env` as described there. This screencast reads the Snowflake sign-in and `SCREENCAST_BLUR` from it.
3. Run `cp .env.example .env` and set `AURA_MCP_URL` to the MCP URL of your Aura instance.
4. Run `npm run aura-login` and sign in to the Aura console in the window that opens. Google sign-in can't be scripted, so the screencast reuses this session for the Aura console and Aura's OAuth popup. Each successful recording renews it. Run it again when a recording fails with "The Aura session expired".

The Aura instance needs the **Movies** sample dataset.

## Run

| Command | What it does |
| --- | --- |
| `npx playwright test` | Drops the demo objects, records into `playwright-output/` and writes the guide's screenshots. It also deletes the account's CoWork chats. |
| `node render.ts` | Renders the video, with the URL pill at each host switch. |
| `npm run readme` | Fills the guide's code blocks from `stack.ts`. |
| `npm run readme -- --check` | Fails if the code blocks are out of date. |
| `npm run aura-browser` | Opens the saved Aura session in Google Chrome. |
| `SCREENCAST_DEBUG_SHOTS=1 npx playwright test` | Logs the numbers behind each screenshot crop. |

Each run connects the MCP server again, so Aura's consent screen shows in every recording. For `ONLY_STEPS`, `OUTPUT_NAME` and `HEADLESS=0`, see the [kit](../../tools/screencast/README.md).
