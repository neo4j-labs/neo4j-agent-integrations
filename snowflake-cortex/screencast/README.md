# Screencast

This screencast records [sample 2](../samples/2-snowsight/README.md) in Snowsight. It renders the narrated [video](https://youtu.be/5w1wxf3WfYQ) with the [screencast kit](../../tools/screencast/README.md). The UDF bodies, SQL bodies and model come from `../shared/`, so they match what Terraform deploys.

The sample's guide is written by hand. The screencast keeps two parts of it up to date:

- A recording writes the screenshots to `../samples/2-snowsight/images/`.
- `npm run readme` fills the marked code blocks from `stack.ts`.

## Layout

| Path | What it holds |
| --- | --- |
| `create-agent-via-ui.spec.ts` | The test. It runs the setup, then the steps in order. |
| `stack.ts` | Names and SQL statements. It reads the bodies, tool texts, model and cleanup from `../shared/`. |
| `steps/` | The recorded steps and their narration, grouped by phase. |
| `snowsight/` | Helpers for the Snowsight UI: catalog, workspace editor, stage upload, tool dialogs and popups. |
| `readme.ts` | Fills the marked code blocks of the guide. |
| `cleanup.py` | Drops the demo objects outside a recording. |

## Setup

1. Follow the kit's [setup](../../tools/screencast/README.md#setup).
2. Run `cp .env.example .env` and fill in the values.
3. Put the model in `../shared/model/minilm/`. The Terraform sample downloads it.

## Run

| Command | What it does |
| --- | --- |
| `npx playwright test` | Drops and recreates the demo objects, records into `playwright-output/` and writes the guide's screenshots. |
| `ONLY_STEPS=intro,8,9 npx playwright test` | Records only the listed steps. It reuses the objects of a full run. |
| `node render.ts` | Renders the video. |
| `npm run readme` | Fills the guide's code blocks from `stack.ts`. |
| `npm run readme -- --check` | Fails if the code blocks are out of date. |
| `uv run cleanup.py` | Drops the demo objects. It connects as `TERRAFORM_SVC` with `../samples/1-terraform/terraform.tfvars`. |

For `OUTPUT_NAME` and `HEADLESS=0`, see the [kit](../../tools/screencast/README.md).
