# Option A — CI/Build-time MD→AsciiDoc Conversion

Source files stay as `README.md` (Markdown). Conversion to AsciiDoc happens
as a build step — either locally before running Antora or inside a GitHub
Actions workflow. Antora reads from a generated staging directory.

---

## Summary

| Attribute | Value |
|-----------|-------|
| Source of truth | `{integration}/README.md` (Markdown, committed) |
| AsciiDoc files | Generated at build time into `_antora-staging/` (gitignored) |
| Antora integration | Second content source pointing at `_antora-staging/` |
| Collector extension | **Not required** |
| When conversion runs | Every build (local or CI) |
| Validated AsciiDoc files | Ephemeral — generated, validated, consumed, discarded |

---

## Pros and cons

### Pros
- **Markdown stays the default** — contributors edit `README.md` with no AsciiDoc
  knowledge required; GitHub renders it natively in the repo browser
- **Single source of truth** — no risk of `README.md` and `README.adoc` drifting
  out of sync; only one file to maintain per integration
- **No AsciiDoc committed** — the repo stays lean; generated files never appear
  in PRs or git history
- **Conversion logic is centralisable** — the Python script is the only place
  conversion rules live; fixing a rule fixes every page at once
- **Notebook links and code files stay alongside source** — contributors keep
  the natural `{folder}/README.md + notebook.ipynb` pattern unchanged

### Cons
- **Build-time failures are late** — a bad Markdown construct is only caught
  when someone runs the build or CI fires; no static `.adoc` to lint in the IDE
- **Local preview requires extra step** — contributor must run the conversion
  script before launching Antora (or use the `npm run preview` wrapper that does
  it automatically)
- **Conversion quality is opaque** — without committing `.adoc` files, reviewers
  cannot see in a PR diff whether the AsciiDoc output looks correct
- **Slower CI** — every build runs the full conversion pass over all files even
  if only one README changed (mitigatable with file-change detection)
- **Script must be present on every build machine** — Python 3 and any conversion
  dependencies must be available in the CI environment and locally

---

## Repository structure

```
neo4j-agent-integrations/           ← this repo
├── antora.yml                      ← name: labs, version: master (no ext.collector)
├── langgraph/
│   ├── README.md                   ← source of truth (Markdown)
│   └── langgraph.ipynb
├── openai-agents-sdk/
│   ├── README.md
│   └── openai_agents.ipynb
├── aws-agentcore/
│   ├── README.md
│   └── samples/
│       ├── 1-mcp-runtime-docker/README.md
│       ├── 2-gateway-external-mcp/README.md
│       └── 3-mcp-runtime-neo4j-sdk/README.md
├── scripts/
│   ├── publish-to-labs.py          ← --convert writes to _antora-staging/
│   ├── validate-adoc.py            ← runs on _antora-staging/ output
│   └── slug-map.yml                ← folder name → slug + metadata
└── _antora-staging/                ← GITIGNORED, created at build time
    └── modules/
        └── genai-ecosystem/
            └── pages/
                └── genai-frameworks/
                    ├── langgraph.adoc
                    ├── openai-agents.adoc
                    ├── aws-agentcore.adoc
                    ├── aws-agentcore-mcp-docker.adoc
                    └── ...

labs-pages/                         ← separate repo (symlinked here)
├── preview.yml                     ← adds _antora-staging as content source
├── package.json                    ← prebuild script calls publish-to-labs.py
└── modules/genai-ecosystem/
    ├── nav.adoc                    ← updated with genai-frameworks/* entries
    └── pages/
        └── genai-frameworks.adoc   ← updated hub page
```

---

## antora.yml (this repo root)

```yaml
name: labs
version: master
# No ext.collector — staging dir is managed externally
```

---

## slug-map.yml

Defines the folder → slug mapping and metadata. Used by the conversion script
and the nav generator. Lives in `scripts/slug-map.yml`.

```yaml
integrations:
  # Agent Frameworks
  - folder: langgraph
    slug: langgraph
    title: "LangGraph + Neo4j Integration"
    tags: "langgraph, langchain, agents, neo4j, mcp, checkpoint"
    product: LangGraph
    category: "Agent Frameworks"
    nav_label: LangGraph
    thin: false

  - folder: openai-agents-sdk
    slug: openai-agents
    title: "OpenAI Agents SDK + Neo4j Integration"
    tags: "openai, agents, neo4j, mcp, tools"
    product: "OpenAI Agents SDK"
    category: "Agent Frameworks"
    nav_label: "OpenAI Agents SDK"
    thin: false

  # AWS AgentCore with sub-pages
  - folder: aws-agentcore
    slug: aws-agentcore
    title: "AWS AgentCore + Neo4j Integration"
    tags: "aws, agentcore, bedrock, neo4j, mcp, iam"
    product: "AWS AgentCore"
    category: "Cloud & Enterprise Platforms"
    nav_label: "AWS AgentCore"
    thin: false
    sub_pages:
      - src: samples/1-mcp-runtime-docker/README.md
        slug: aws-agentcore-mcp-docker
        title: "AWS AgentCore — MCP Runtime (Docker)"
        nav_label: "MCP Runtime (Docker)"
      - src: samples/2-gateway-external-mcp/README.md
        slug: aws-agentcore-gateway
        title: "AWS AgentCore — Gateway + External MCP"
        nav_label: "Gateway + External MCP"
      - src: samples/3-mcp-runtime-neo4j-sdk/README.md
        slug: aws-agentcore-neo4j-sdk
        title: "AWS AgentCore — MCP Runtime (Neo4j SDK)"
        nav_label: "MCP Runtime (Neo4j SDK)"

  # ... all other integrations
```

---

## publish-to-labs.py — Option A behaviour

### `--convert` mode

```
python3 scripts/publish-to-labs.py --convert [--integrations langgraph crewai]
```

Steps:
1. Read `scripts/slug-map.yml`
2. For each integration entry:
   a. Read `{folder}/README.md`
   b. Convert Markdown → AsciiDoc (full conversion pipeline)
   c. Inject AsciiDoc frontmatter from slug-map metadata
   d. Write to `_antora-staging/modules/genai-ecosystem/pages/genai-frameworks/{slug}.adoc`
   e. If entry has `sub_pages`, repeat for each sub-page source
3. Write `_antora-staging/antora.yml` (name: labs, version: master)
4. Run validator on all generated files (see validate-adoc.py)
5. Exit non-zero if any ERROR-level finding

### `--nav` mode

```
python3 scripts/publish-to-labs.py --nav
```

Prints the nav.adoc block to add to labs-pages `nav.adoc`. Thin entries
are commented out with `//`.

---

## labs-pages/preview.yml (updated)

```yaml
site:
  title: Neo4j Labs
  url: /labs

content:
  sources:
  - url: ./
    branches: HEAD
    worktrees: true
  - url: /Users/mh/d/llm/neo4j-agent-integrations   # local path for dev
    start_path: _antora-staging
    branches: HEAD
    worktrees: true                                   # reads filesystem, not git

ui:
  bundle:
    url: https://d12wh7zj8x3amw.cloudfront.net/build/ui-bundle-latest.zip
    snapshot: true

urls:
  html_extension_style: indexify

asciidoc:
  extensions:
  - "@neo4j-documentation/remote-include"
  - "@neo4j-documentation/macros"
  attributes:
    page-theme: labs
    page-disabletracking: true
```

> **Note**: The production playbook (used by GitHub Actions / the live build)
> references this repo by its GitHub URL + branch instead of a local path:
> ```yaml
> - url: https://github.com/neo4j-labs/neo4j-agent-integrations.git
>   start_path: _antora-staging
>   branches: main
> ```
> But `_antora-staging/` is gitignored, so this **does not work for the
> production playbook** without a pre-build step that generates and commits
> the staging files — see CI section below.

---

## labs-pages/package.json (updated)

```json
{
  "name": "labs-pages",
  "scripts": {
    "convert": "python3 /path/to/neo4j-agent-integrations/scripts/publish-to-labs.py --convert",
    "preview": "npm run convert && node server.js",
    "build": "npm run convert && antora preview.yml"
  },
  "devDependencies": {
    "@antora/cli": "^3.1",
    "@antora/site-generator": "^3.1"
  }
}
```

---

## Local testing workflow

### Prerequisites

```bash
# In neo4j-agent-integrations
python3 --version        # 3.10+
pip install pyyaml       # for slug-map.yml parsing

# In labs-pages
node --version           # 18+
npm install
```

### Step-by-step

```bash
# 1. From neo4j-agent-integrations root — convert all READMEs
python3 scripts/publish-to-labs.py --convert

# 2. Inspect the generated files
ls _antora-staging/modules/genai-ecosystem/pages/genai-frameworks/

# 3. Run the validator on generated output
python3 scripts/validate-adoc.py _antora-staging/modules/genai-ecosystem/pages/genai-frameworks/*.adoc

# 4. Fix any ERRORs in the conversion script, re-run --convert

# 5. From labs-pages — launch Antora preview
cd /Users/mh/docs/labs-pages
antora --fetch preview.yml

# 6. Serve locally
node server.js
# open http://localhost:5000/labs/genai-ecosystem/genai-frameworks/langgraph/
```

### Iterating on a single integration

```bash
# Only convert langgraph, faster iteration
python3 scripts/publish-to-labs.py --convert --integrations langgraph

# Validate just that file
python3 scripts/validate-adoc.py \
  _antora-staging/modules/genai-ecosystem/pages/genai-frameworks/langgraph.adoc

# Rebuild Antora (only needs re-run from labs-pages)
cd /Users/mh/docs/labs-pages && antora --fetch preview.yml
```

### Check external links

```bash
python3 scripts/validate-adoc.py --check-links \
  _antora-staging/modules/genai-ecosystem/pages/genai-frameworks/*.adoc
```

---

## GitHub Actions CI

### Trigger: PR to neo4j-agent-integrations touches any README.md

```yaml
# .github/workflows/validate-docs.yml  (in neo4j-agent-integrations)
name: Validate documentation

on:
  pull_request:
    paths:
      - '**/README.md'
      - 'scripts/publish-to-labs.py'
      - 'scripts/validate-adoc.py'
      - 'scripts/slug-map.yml'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install pyyaml requests

      - name: Convert README.md → AsciiDoc
        run: python3 scripts/publish-to-labs.py --convert

      - name: Validate generated AsciiDoc
        run: |
          python3 scripts/validate-adoc.py \
            _antora-staging/modules/genai-ecosystem/pages/genai-frameworks/*.adoc

      - name: Check external links (on schedule only)
        if: github.event_name == 'schedule'
        run: |
          python3 scripts/validate-adoc.py --check-links \
            _antora-staging/modules/genai-ecosystem/pages/genai-frameworks/*.adoc
```

### Trigger: Antora build in labs-pages (labs-pages CI)

Because `_antora-staging/` is gitignored in this repo, the labs-pages CI
must run the conversion script before invoking Antora:

```yaml
# .github/workflows/build.yml  (in labs-pages)
name: Build site

on:
  push:
    branches: [publish]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout labs-pages
        uses: actions/checkout@v4

      - name: Checkout neo4j-agent-integrations
        uses: actions/checkout@v4
        with:
          repository: neo4j-labs/neo4j-agent-integrations
          path: agent-integrations

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install pyyaml

      - name: Convert integration READMEs
        run: python3 agent-integrations/scripts/publish-to-labs.py --convert
        env:
          REPO_ROOT: agent-integrations      # script respects this env var

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - run: npm ci

      - name: Build Antora site
        run: npx antora preview.yml
        # preview.yml points at agent-integrations/_antora-staging via local path
        # which now exists on the CI runner filesystem
```

---

## Key risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Conversion script has a bug — bad AsciiDoc generated silently | Validator step is mandatory; CI fails on ERROR |
| `_antora-staging/` not found when labs-pages CI runs | labs-pages CI explicitly checks out this repo first and runs conversion |
| Contributor edits `README.md`, doesn't run preview, broken output not caught until CI | Pre-commit hook in this repo runs `--convert --validate` automatically |
| Production playbook URL doesn't have access to `_antora-staging/` (gitignored) | labs-pages CI generates it fresh on every build run |
