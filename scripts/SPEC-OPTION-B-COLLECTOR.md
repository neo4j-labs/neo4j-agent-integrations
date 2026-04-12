# Option B — In-place README.adoc + Antora Collector Extension

Source Markdown is converted to AsciiDoc once and committed as `README.adoc`
alongside `README.md` in each integration folder. The Antora Collector Extension
handles path mapping at build time — it copies/renames `{folder}/README.adoc`
into the correct Antora module path during every Antora run.

---

## Summary

| Attribute | Value |
|-----------|-------|
| Source of truth | `{integration}/README.adoc` (AsciiDoc, committed) |
| Markdown | `{integration}/README.md` kept as contributor-facing reference |
| AsciiDoc files | Committed alongside README.md; diff-reviewable in PRs |
| Antora integration | Collector extension runs path-mapping script at build time |
| Collector extension | `@antora/collector-extension` ~1.0, installed in labs-pages |
| When conversion runs | Once (initial), then manually when README.md changes significantly |
| Validated AsciiDoc files | Static — can be linted in IDE, in CI, anytime |

---

## Pros and cons

### Pros
- **AsciiDoc is committed** — reviewers see the exact rendered content in PR
  diffs; IDE AsciiDoc plugins (IntelliJ, VS Code) give live preview
- **Validator runs on static files** — no build step required; CI linting is
  instant and always reflects what is actually in the repo
- **Antora collector is the only build-time moving part** — it only does a
  fast path-mapping copy; no Markdown parsing or conversion at build time
- **No staging directory artefacts** — `_generated/` is small and cheap to
  create; the collector creates it in milliseconds from committed `.adoc` files
- **Collector is self-contained** — no external Python requirement in the Antora
  build; the collector's `run` step is a simple shell copy/rename script
- **Decoupled cadence** — README.md can be updated frequently by contributors;
  README.adoc is regenerated deliberately when the content is ready to publish
- **Works natively with Antora's worktree model** — collector reads the git
  working tree directly; no extra repo checkout in CI

### Cons
- **Two files per integration** — `README.md` and `README.adoc` must be kept
  in sync; a contributor who edits only `README.md` silently diverges from
  the published page
- **Initial conversion is a one-time manual step** — someone must run
  `publish-to-labs.py --convert` for all integrations and commit the results
- **AsciiDoc files in PRs can be noisy** — a PR that updates `README.md` and
  regenerates `README.adoc` has twice as many changed files; reviewers must
  know to look at `README.adoc` for actual content changes
- **Sync discipline required** — `README.adoc` may lag behind `README.md` if
  the conversion step is forgotten; stale published pages with no visible error
- **Collector extension is a labs-pages dependency** — adds `@antora/collector-extension`
  to `package.json`; if the extension has a breaking release the build breaks

---

## Repository structure

```
neo4j-agent-integrations/           ← this repo
├── antora.yml                      ← name: labs, version: master + ext.collector
├── langgraph/
│   ├── README.md                   ← contributor-facing Markdown
│   ├── README.adoc                 ← committed AsciiDoc (generated, then maintained)
│   └── langgraph.ipynb
├── openai-agents-sdk/
│   ├── README.md
│   ├── README.adoc
│   └── openai_agents.ipynb
├── aws-agentcore/
│   ├── README.md
│   ├── README.adoc
│   └── samples/
│       ├── 1-mcp-runtime-docker/
│       │   ├── README.md
│       │   ├── README.adoc         ← sub-page AsciiDoc
│       │   └── demo.ipynb
│       ├── 2-gateway-external-mcp/
│       │   ├── README.md
│       │   └── README.adoc
│       └── 3-mcp-runtime-neo4j-sdk/
│           ├── README.md
│           └── README.adoc
├── scripts/
│   ├── publish-to-labs.py          ← --convert writes README.adoc in-place
│   ├── validate-adoc.py            ← runs on committed README.adoc files
│   └── slug-map.yml                ← folder → slug + metadata
└── _generated/                     ← GITIGNORED, created by collector at build time
    ├── langgraph.adoc              (copy of langgraph/README.adoc)
    ├── openai-agents.adoc          (copy of openai-agents-sdk/README.adoc)
    ├── aws-agentcore.adoc
    ├── aws-agentcore-mcp-docker.adoc
    └── ...

labs-pages/                         ← separate repo (symlinked here)
├── preview.yml                     ← registers collector; adds this repo as source
├── package.json                    ← includes @antora/collector-extension
└── modules/genai-ecosystem/
    ├── nav.adoc                    ← updated with genai-frameworks/* entries
    └── pages/
        └── genai-frameworks.adoc   ← updated hub page
```

---

## antora.yml (this repo root)

This is the core of Option B. The collector config lives here and runs
as part of every Antora build that includes this repo as a content source.

```yaml
name: labs
version: master

ext:
  collector:
    - run:
        # Copies {folder}/README.adoc → _generated/{slug}.adoc for all integrations.
        # Uses slug-map.yml for the folder→slug mapping.
        # Fast: no Markdown parsing, just file copies with rename.
        command: python3 scripts/collect.py
        dir: .
        shell: true
        failure: throw
      scan:
        dir: _generated
        files: "*.adoc"
        into: modules/genai-ecosystem/pages/genai-frameworks
```

### Why a separate `collect.py` and not `publish-to-labs.py --collect`?

`collect.py` is a minimal script (< 50 lines) that only does path copying and
renaming from `slug-map.yml`. It has no conversion logic and no external
dependencies beyond the Python standard library. Keeping it separate means
the collector step is fast and cannot accidentally trigger a full conversion.

---

## scripts/collect.py

```python
#!/usr/bin/env python3
"""
collect.py — Copies committed README.adoc files into _generated/{slug}.adoc
for consumption by the Antora collector extension.

Reads slug-map.yml for the folder → slug mapping.
Runs from the repo root (cwd set by antora.yml collector run.dir).
"""
import shutil, yaml
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "_generated"
OUT.mkdir(exist_ok=True)

with open(ROOT / "scripts" / "slug-map.yml") as f:
    config = yaml.safe_load(f)

for entry in config["integrations"]:
    src = ROOT / entry["folder"] / "README.adoc"
    if not src.exists():
        print(f"  SKIP {entry['folder']}: README.adoc not found")
        continue
    dst = OUT / f"{entry['slug']}.adoc"
    shutil.copy2(src, dst)
    print(f"  Copied {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")

    for sub in entry.get("sub_pages", []):
        sub_src = ROOT / entry["folder"] / sub["src"]
        if not sub_src.exists():
            print(f"  SKIP sub-page {sub['src']}: not found")
            continue
        sub_dst = OUT / f"{sub['slug']}.adoc"
        shutil.copy2(sub_src, sub_dst)
        print(f"  Copied {sub_src.relative_to(ROOT)} → {sub_dst.relative_to(ROOT)}")

print(f"\nCollected {len(list(OUT.glob('*.adoc')))} pages into {OUT.relative_to(ROOT)}/")
```

---

## slug-map.yml (shared with Option A)

```yaml
integrations:
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

  # ... all other integrations (crewai, pydantic-ai, etc.)
```

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
  - url: /Users/mh/d/llm/neo4j-agent-integrations    # local dev path
    branches: HEAD
    worktrees: true     # reads working tree so uncommitted README.adoc changes appear

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

antora:
  extensions:
  - "@antora/collector-extension"
```

### Production playbook (labs-pages CI)

```yaml
content:
  sources:
  - url: https://github.com/neo4j-documentation/labs-pages.git
    branches: publish
  - url: https://github.com/neo4j-labs/neo4j-agent-integrations.git
    branches: main
    # No worktrees: true — reads committed files from git
    # README.adoc files are committed so this works without a pre-build step
```

> **Key advantage over Option A**: the production playbook references the
> GitHub URL directly with no pre-build step. The collector runs within
> the Antora process, reads the committed `README.adoc` files from git,
> copies them to `_generated/`, and injects them. No external checkout needed.

---

## labs-pages/package.json (updated)

```json
{
  "name": "labs-pages",
  "scripts": {
    "preview": "antora --fetch preview.yml && node server.js",
    "build": "antora preview.yml"
  },
  "devDependencies": {
    "@antora/cli": "^3.1",
    "@antora/site-generator": "^3.1",
    "@antora/collector-extension": "^1.0"
  }
}
```

---

## Local testing workflow

### Prerequisites

```bash
# Python (for initial conversion and validate)
python3 --version        # 3.10+
pip install pyyaml

# Node / Antora (in labs-pages)
node --version           # 18+
cd /Users/mh/docs/labs-pages
npm install              # installs @antora/collector-extension
```

### First-time setup: initial conversion of all README.md → README.adoc

```bash
# Run once; commit the resulting README.adoc files
cd /Users/mh/d/llm/neo4j-agent-integrations
python3 scripts/publish-to-labs.py --convert

# Validate all generated README.adoc files
python3 scripts/validate-adoc.py '**/README.adoc'

# Inspect a sample
cat langgraph/README.adoc | head -30

# Commit (once happy with output)
git add '**/README.adoc'
git commit -m "Add generated README.adoc pages for Antora"
```

### Running the full preview locally

```bash
# From labs-pages directory
cd /Users/mh/docs/labs-pages

# Run Antora — the collector fires automatically inside the build
# It reads langgraph/README.adoc etc. via worktrees: true from the local path
antora --fetch preview.yml

# Serve
node server.js
# open http://localhost:5000/labs/genai-ecosystem/genai-frameworks/langgraph/
```

The collector output is visible in the Antora log:

```
[collector] Running: python3 scripts/collect.py
  Copied langgraph/README.adoc → _generated/langgraph.adoc
  Copied openai-agents-sdk/README.adoc → _generated/openai-agents.adoc
  ...
  Collected 26 pages into _generated/
[collector] Scanning _generated → modules/genai-ecosystem/pages/genai-frameworks
[collector] Injected 26 pages into content catalog
```

### Iterating on a single integration (fast loop)

```bash
# 1. Edit langgraph/README.adoc directly (or re-run conversion for one file)
python3 scripts/publish-to-labs.py --convert --integrations langgraph

# 2. Validate just that file
python3 scripts/validate-adoc.py langgraph/README.adoc

# 3. Re-run Antora (collector re-fires, picks up the change)
cd /Users/mh/docs/labs-pages && antora preview.yml

# 4. Refresh browser
```

Because `worktrees: true` is set in `preview.yml`, Antora reads the file
from the filesystem — you do NOT need to `git commit` between iterations.

### Debugging the collector

```bash
# Run collect.py directly to see what it does without Antora
cd /Users/mh/d/llm/neo4j-agent-integrations
python3 scripts/collect.py

# Check _generated/ contents
ls -la _generated/

# Diff a collected file against its source
diff langgraph/README.adoc _generated/langgraph.adoc
# Should show no diff (collect.py is a plain copy)
```

### Testing with --check-links

```bash
# Validate committed README.adoc files with external link checking
cd /Users/mh/d/llm/neo4j-agent-integrations
python3 scripts/validate-adoc.py --check-links '**/README.adoc'
```

---

## GitHub Actions CI

### Trigger: PR touches README.md or README.adoc

```yaml
# .github/workflows/validate-docs.yml  (in neo4j-agent-integrations)
name: Validate documentation

on:
  pull_request:
    paths:
      - '**/README.md'
      - '**/README.adoc'
      - 'scripts/publish-to-labs.py'
      - 'scripts/validate-adoc.py'
      - 'scripts/slug-map.yml'
      - 'antora.yml'

jobs:
  validate-adoc:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install pyyaml requests

      - name: Validate committed README.adoc files
        run: python3 scripts/validate-adoc.py '**/README.adoc'

      - name: Check README.md ↔ README.adoc sync
        run: |
          # Warn if README.md is newer than README.adoc (potential stale page)
          python3 scripts/publish-to-labs.py --check-sync

  check-sync:
    # Optional: re-convert README.md and diff against committed README.adoc
    # Flags if README.adoc is stale (README.md was updated without re-converting)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - run: pip install pyyaml

      - name: Re-convert and diff
        run: |
          python3 scripts/publish-to-labs.py --convert --output /tmp/fresh
          for f in $(find /tmp/fresh -name '*.adoc'); do
            slug=$(basename $f .adoc)
            committed=$(find . -name "README.adoc" -path "*${slug}*" | head -1)
            if [ -n "$committed" ]; then
              diff "$committed" "$f" || echo "STALE: $slug"
            fi
          done
```

### Trigger: Antora build in labs-pages

```yaml
# .github/workflows/build.yml  (in labs-pages)
name: Build site

on:
  push:
    branches: [publish]
  repository_dispatch:
    types: [agent-integrations-updated]   # triggered by webhook from this repo

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - run: npm ci    # installs @antora/collector-extension

      - name: Build Antora site
        run: npx antora preview.yml
        # preview.yml uses the GitHub URL for neo4j-agent-integrations
        # Collector runs inside Antora, reads committed README.adoc from git
        # No separate checkout of neo4j-agent-integrations needed
```

> **Key difference from Option A**: no separate `checkout` of this repo in the
> labs-pages CI job. The collector fetches what it needs directly from git.

---

## Sync discipline: keeping README.md and README.adoc in step

Add a `--check-sync` flag to `publish-to-labs.py`:

```
python3 scripts/publish-to-labs.py --check-sync
```

Compares git modification timestamps and reports:

```
OK    langgraph         README.adoc is current
STALE crewai            README.md modified 2026-03-15, README.adoc last converted 2026-02-01
MISS  ibm-watsonx       README.adoc does not exist
```

Run this locally before pushing, and in CI on every PR.

---

## Key risks and mitigations

| Risk | Mitigation |
|------|-----------|
| README.md updated, README.adoc not regenerated — stale published page | `--check-sync` in CI fails the PR; pre-commit hook warns locally |
| README.adoc accidentally hand-edited — diverges from README.md | Code review policy: README.adoc is generated; edits go in README.md first |
| Collector extension breaking release | Pin `@antora/collector-extension` to exact version; Dependabot monitors |
| `collect.py` not found when collector runs | `antora.yml` `run.dir: .` ensures CWD is repo root; path is relative to root |
| Sub-page README.adoc not yet created | `collect.py` prints SKIP but does not fail; missing pages show as broken xrefs in Antora build |

---

## Comparison with Option A

| Factor | Option A (CI conversion) | Option B (collector) |
|--------|--------------------------|----------------------|
| Source format | README.md only | README.md + README.adoc |
| AsciiDoc in git | No | Yes |
| Conversion timing | Every build | Once, on demand |
| Build complexity | Extra CI step to checkout repo | Self-contained in Antora |
| Production playbook | Needs pre-build checkout | GitHub URL + branch, no extras |
| PR diff shows AsciiDoc | No | Yes |
| IDE AsciiDoc preview | No | Yes |
| Stale content risk | Low (always fresh) | Medium (sync discipline required) |
| Validator runs on | Ephemeral staging files | Committed files, anytime |
| Collector extension needed | No | Yes |
| Initial setup effort | Lower | Slightly higher (initial conversion) |
