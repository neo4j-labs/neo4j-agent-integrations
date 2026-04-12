#!/usr/bin/env python3
"""publish-to-labs.py — Convert integration README.md → AsciiDoc for Antora.

Writes generated .adoc files directly into the labs-pages working tree
(modules/genai-ecosystem/pages/genai-frameworks/) so Antora picks them up
via its `url: ./` + `branches: HEAD` worktree source — no separate git repo needed.

Usage:
    python3 scripts/publish-to-labs.py --convert [--integrations slug1 slug2 ...]
    python3 scripts/publish-to-labs.py --nav
    python3 scripts/publish-to-labs.py --validate

Environment variables:
    REPO_ROOT       — path to neo4j-agent-integrations repo (default: auto-detected)
    LABS_PAGES_DIR  — path to neo4j labs-pages repo (default: <REPO_ROOT>/labs-pages)
"""

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml required — pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).parent.parent))
SLUG_MAP = REPO_ROOT / "scripts" / "slug-map.yml"

def _labs_pages_dir(args=None):
    """Resolve labs-pages directory from CLI arg, env var, or default symlink."""
    if args and getattr(args, 'labs_pages_dir', None):
        return Path(args.labs_pages_dir)
    env = os.environ.get("LABS_PAGES_DIR")
    if env:
        return Path(env)
    return REPO_ROOT / "labs-pages"  # symlink or sibling dir

def _pages_out(labs_pages):
    return labs_pages / "modules" / "genai-ecosystem" / "pages" / "genai-frameworks"


# ---------------------------------------------------------------------------
# Markdown → AsciiDoc converter
# ---------------------------------------------------------------------------

GITHUB_BASE = "https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main"

# Files that are internal/gitignored and should not be linked in Antora output
_INTERNAL_FILES = {
    'mcp-auth-support.md',
    'AGENTFORCE.md',
    'REPORT.md',
    'APIS-2026.md',
    'PLAN.md',
}


def _build_path_xref_map(integrations_map: list) -> dict:
    """Build a map of repo-root-relative folder paths → Antora xref slugs."""
    m = {}
    for entry in integrations_map:
        folder = entry['folder'].rstrip('/')
        m[folder] = entry['slug']
        m[folder + '/'] = entry['slug']
        m[folder + '/README.md'] = entry['slug']
        for sub in entry.get('sub_pages', []):
            src = f"{folder}/{sub['src'].lstrip('/')}"
            src_dir = str(Path(src).parent)
            m[src] = sub['slug']
            m[src_dir] = sub['slug']
            m[src_dir + '/'] = sub['slug']
    return m


def _make_inline(folder: str, path_xref: dict):
    """Return an _inline function closed over folder context and slug lookup."""

    def _link(m):
        text, url = m.group(1), m.group(2)
        if url.startswith('#'):
            return text  # fragment-only: drop anchor, keep text

        if url.startswith('http'):
            return f'{url}[{text}^]'

        # Strip trailing slash and fragment for lookup
        url_clean = url.rstrip('/')
        url_no_frag = url_clean.split('#')[0]

        # Resolve relative path to repo-root-relative
        # Anchor to REPO_ROOT (not CWD) so this works regardless of where the
        # script is invoked from (e.g. docs-refresh CI checkout directory).
        repo_rel = str((REPO_ROOT / folder / url_no_frag).resolve().relative_to(
            REPO_ROOT.resolve()
        )) if not url_no_frag.startswith('/') else url_no_frag.lstrip('/')

        # Check if it's a known internal/gitignored file
        basename = Path(url_no_frag).name
        if basename in _INTERNAL_FILES:
            return text  # drop link, keep text

        # Check if it maps to a known integration slug (→ xref)
        for candidate in (repo_rel, repo_rel.rstrip('/'), repo_rel + '/'):
            if candidate in path_xref:
                return f'xref:genai-frameworks/{path_xref[candidate]}.adoc[{text}]'

        # Notebook or other source file → GitHub link
        if url_no_frag.endswith('.ipynb') or url_no_frag.endswith('.py'):
            gh_path = repo_rel if not url_no_frag.startswith('./') else f'{folder}/{url_no_frag.lstrip("./")}'
            return f'{GITHUB_BASE}/{gh_path}[{text}^]'

        # Generic relative link — keep as-is (Antora may resolve it)
        return f'link:{url}[{text}]'

    def _inline(line: str) -> str:
        # Images before links
        line = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'image::\2[\1]', line)
        line = re.sub(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', _link, line)
        # Bold **text** → *text*
        line = re.sub(r'\*\*([^*\n]+)\*\*', r'*\1*', line)
        # Italic
        line = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'_\1_', line)
        line = re.sub(r'(?<!_)_([^_\n]+)_(?!_)', r'_\1_', line)
        return line

    return _inline


def convert_md_to_adoc(md_text, entry, folder='', path_xref=None):
    """Convert a full Markdown document to AsciiDoc for an integration page."""
    _inline = _make_inline(folder, path_xref or {})
    lines = md_text.splitlines()
    out = []

    in_code = False
    code_fence = ''
    in_table = False
    table_rows: list[str] = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return
        # Detect header separator row and strip it
        header = []
        data_rows = []
        sep_found = False
        for row in table_rows:
            cells = [c.strip() for c in row.strip().strip('|').split('|')]
            if all(re.match(r'^[-: ]+$', c) for c in cells if c):
                sep_found = True
                continue
            if not sep_found:
                header.append(cells)
            else:
                data_rows.append(cells)

        if not header:
            in_table = False
            table_rows = []
            return

        ncols = len(header[0])
        col_spec = ','.join(['1'] * ncols)
        out.append(f'[cols="{col_spec}", options="header"]')
        out.append('|===')
        out.append('| ' + ' | '.join(_inline(c) for c in header[0]))
        out.append('')
        for row_cells in data_rows:
            # Pad or trim to ncols
            while len(row_cells) < ncols:
                row_cells.append('')
            out.append('| ' + ' | '.join(_inline(c) for c in row_cells[:ncols]))
        out.append('|===')
        out.append('')
        in_table = False
        table_rows = []

    i = 0
    skip_first_h1 = True  # Drop the doc-level H1 (becomes page title in frontmatter)

    while i < len(lines):
        line = lines[i]

        # ── Code fences ──────────────────────────────────────────────────
        # Allow indented fences (e.g. inside list items): ^(\s*)(`{3,}|~{3,})
        fence_match = re.match(r'^(\s*)(`{3,}|~{3,})(.*)', line)
        if fence_match and not in_code:
            if in_table:
                flush_table()
            in_code = True
            code_fence = fence_match.group(2)  # just the fence chars, e.g. ```
            lang = fence_match.group(3).strip()
            if lang:
                out.append(f'[source,{lang}]')
            else:
                out.append('[source]')
            out.append('----')
            i += 1
            continue

        if in_code:
            # Closing fence: same fence char type, optional leading whitespace
            stripped = line.strip()
            if stripped == code_fence or (stripped.startswith(code_fence) and not stripped[len(code_fence):].strip()):
                in_code = False
                code_fence = ''
                out.append('----')
            else:
                out.append(line)
            i += 1
            continue

        # ── HTML comments ─────────────────────────────────────────────────
        if re.match(r'^\s*<!--', line):
            # Strip HTML/Markdown comments entirely
            # Handle multi-line comments
            if '-->' in line:
                i += 1
                continue
            # Multi-line: skip until -->
            i += 1
            while i < len(lines) and '-->' not in lines[i]:
                i += 1
            i += 1
            continue

        # ── Inline HTML (iframes etc.) — wrap in passthrough block ──────────
        if re.match(r'^\s*<[a-zA-Z]', line) and not re.match(r'^\s*<!--', line):
            if in_table:
                flush_table()
            out.append('++++')
            out.append(line)
            i += 1
            while i < len(lines) and lines[i].strip():
                out.append(lines[i])
                i += 1
            out.append('++++')
            continue

        # ── Horizontal rules ─────────────────────────────────────────────
        if re.match(r'^\s*(---+|___+|\*\*\*+)\s*$', line):
            out.append("'''")
            i += 1
            continue

        # ── Headings ─────────────────────────────────────────────────────
        h_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if h_match:
            if in_table:
                flush_table()
            level = len(h_match.group(1))
            text = h_match.group(2).strip()
            if level == 1:
                if skip_first_h1:
                    skip_first_h1 = False
                    i += 1
                    continue
                # Additional H1s become == (shouldn't happen in well-formed MD)
                out.append(f'== {_inline(text)}')
            else:
                # H2 → ==, H3 → ===, H4 → ====, H5 → =====
                out.append('=' * level + ' ' + _inline(text))
            i += 1
            continue

        # ── Tables ────────────────────────────────────────────────────────
        if '|' in line and re.match(r'^\s*\|', line):
            in_table = True
            table_rows.append(line)
            i += 1
            continue
        elif in_table:
            flush_table()
            # Fall through to process current line normally

        # ── Blockquotes ───────────────────────────────────────────────────
        if re.match(r'^>\s?', line):
            # Collect consecutive blockquote lines
            bq_lines = []
            while i < len(lines) and re.match(r'^>\s?', lines[i]):
                bq_lines.append(re.sub(r'^>\s?', '', lines[i]))
                i += 1
            out.append('[NOTE]')
            out.append('====')
            for bql in bq_lines:
                out.append(_inline(bql))
            out.append('====')
            out.append('')
            continue

        # ── Ordered lists ─────────────────────────────────────────────────
        ol_match = re.match(r'^(\s*)\d+\.\s+(.+)$', line)
        if ol_match:
            prev = out[-1] if out else ''
            if prev != '' and not re.match(r'^\.+ ', prev):
                out.append('')
            indent = len(ol_match.group(1))
            level = indent // 2 + 1
            out.append('.' * level + ' ' + _inline(ol_match.group(2)))
            i += 1
            continue

        # ── Unordered lists ───────────────────────────────────────────────
        ul_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if ul_match:
            prev = out[-1] if out else ''
            if prev != '' and not re.match(r'^\*+ ', prev):
                out.append('')
            indent = len(ul_match.group(1))
            level = indent // 2 + 1
            text = ul_match.group(2)
            # Task list items
            text = re.sub(r'^\[[ xX]\]\s*', '', text)
            out.append('*' * level + ' ' + _inline(text))
            i += 1
            continue

        # ── Blank lines ───────────────────────────────────────────────────
        if line.strip() == '':
            out.append('')
            i += 1
            continue

        # ── Regular paragraph line ────────────────────────────────────────
        out.append(_inline(line))
        i += 1

    # Flush any open table
    if in_table:
        flush_table()

    # Strip leading/trailing blank lines
    body = '\n'.join(out).strip()

    # Build frontmatter
    title = entry['title']
    slug = entry['slug']
    tags = entry.get('tags', '')
    product = entry.get('product', '')
    category_attr = 'genai-ecosystem'

    frontmatter = f"""= {title}
:slug: {slug}
:author: Neo4j Labs
:category: {category_attr}
:tags: {tags}
:neo4j-versions: 5.x
:page-pagination:
:page-product: {product}
:attribute-missing: skip

"""

    return frontmatter + body + '\n'


# ---------------------------------------------------------------------------
# Convert mode
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {'.png', '.svg', '.jpg', '.jpeg', '.gif', '.webp'}


def _copy_images(src_folder: Path, images_out: Path):
    """Copy image files from src_folder into images_out, preserving relative paths."""
    import shutil
    copied = 0
    for img in src_folder.rglob('*'):
        if img.suffix.lower() in _IMAGE_EXTS:
            rel = img.relative_to(src_folder)
            dest = images_out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dest)
            copied += 1
    return copied


def cmd_convert(args, integrations_map):
    labs_pages = _labs_pages_dir(args)
    if not labs_pages.exists():
        print(f"ERROR: labs-pages dir not found: {labs_pages}", file=sys.stderr)
        print("Set LABS_PAGES_DIR env var or pass --labs-pages-dir <path>", file=sys.stderr)
        sys.exit(1)
    PAGES_OUT = _pages_out(labs_pages)
    IMAGES_OUT = labs_pages / "modules" / "genai-ecosystem" / "images"
    PAGES_OUT.mkdir(parents=True, exist_ok=True)

    # Determine which integrations to convert
    if args.integrations:
        slugs_filter = set(args.integrations)
        entries = [e for e in integrations_map if e['slug'] in slugs_filter
                   or e['folder'] in slugs_filter]
    else:
        entries = integrations_map

    errors = 0
    converted = 0
    path_xref = _build_path_xref_map(integrations_map)

    for entry in entries:
        folder_path = REPO_ROOT / entry['folder']
        readme = folder_path / 'README.md'
        if not readme.exists():
            print(f"WARN  {entry['folder']}: README.md not found, skipping")
            continue

        md_text = readme.read_text(encoding='utf-8')
        adoc = convert_md_to_adoc(md_text, entry,
                                   folder=entry['folder'], path_xref=path_xref)
        out_path = PAGES_OUT / f"{entry['slug']}.adoc"
        out_path.write_text(adoc, encoding='utf-8')
        n_imgs = _copy_images(folder_path, IMAGES_OUT)
        img_note = f" (+{n_imgs} images)" if n_imgs else ""
        print(f"  OK  {entry['folder']} → genai-frameworks/{entry['slug']}.adoc{img_note}")
        converted += 1

        # Sub-pages
        for sub in entry.get('sub_pages', []):
            sub_src = folder_path / sub['src']
            if not sub_src.exists():
                print(f"WARN  {sub['src']}: not found, skipping sub-page")
                continue
            sub_folder_path = folder_path / Path(sub['src']).parent
            sub_folder = str(Path(entry['folder']) / Path(sub['src']).parent)
            sub_entry = {
                'title': sub['title'],
                'slug': sub['slug'],
                'tags': entry.get('tags', ''),
                'product': entry.get('product', ''),
            }
            sub_md = sub_src.read_text(encoding='utf-8')
            sub_adoc = convert_md_to_adoc(sub_md, sub_entry,
                                           folder=sub_folder, path_xref=path_xref)
            sub_out = PAGES_OUT / f"{sub['slug']}.adoc"
            sub_out.write_text(sub_adoc, encoding='utf-8')
            n_imgs = _copy_images(sub_folder_path, IMAGES_OUT)
            img_note = f" (+{n_imgs} images)" if n_imgs else ""
            print(f"  OK  {sub['src']} → genai-frameworks/{sub['slug']}.adoc{img_note}")
            converted += 1

    print(f"\nConverted {converted} files → {PAGES_OUT}")
    print(f"  (Antora reads these via 'url: ./' worktree source — no git commit needed)")

    # Run inline validator
    adoc_files = list(PAGES_OUT.glob('*.adoc'))
    if adoc_files:
        validator = REPO_ROOT / 'scripts' / 'validate-adoc.py'
        if validator.exists():
            import subprocess
            result = subprocess.run(
                [sys.executable, str(validator)] + [str(f) for f in adoc_files],
                capture_output=False
            )
            if result.returncode != 0:
                errors += 1

    return 0 if errors == 0 else 1


def _git_commit_staging():
    """Init/refresh a bare git repo inside _antora-staging/ for Antora 2.x compatibility."""
    import subprocess

    git_dir = STAGING / '.git'
    env = {**__import__('os').environ,
           'GIT_AUTHOR_NAME': 'publish-to-labs',
           'GIT_AUTHOR_EMAIL': 'noreply@neo4j.com',
           'GIT_COMMITTER_NAME': 'publish-to-labs',
           'GIT_COMMITTER_EMAIL': 'noreply@neo4j.com'}

    def git(*args):
        subprocess.run(['git', '-C', str(STAGING)] + list(args),
                       check=True, capture_output=True, env=env)

    if not git_dir.exists():
        git('init', '-b', 'main')
        git('config', 'user.email', 'noreply@neo4j.com')
        git('config', 'user.name', 'publish-to-labs')
    else:
        # Rename legacy "HEAD" branch to "main" if needed
        result = subprocess.run(
            ['git', '-C', str(STAGING), 'branch', '--show-current'],
            capture_output=True, text=True
        )
        if result.stdout.strip() == 'HEAD':
            git('branch', '-m', 'HEAD', 'main')

    git('add', '-A')
    # Only commit if there are staged changes
    result = subprocess.run(
        ['git', '-C', str(STAGING), 'diff', '--cached', '--quiet'],
        capture_output=True
    )
    if result.returncode != 0:
        git('commit', '--allow-empty', '-m', 'staging update')
    print(f"  git  _antora-staging/ committed (main)")

    # Write/refresh preview-local.yml in labs-pages so developers can use it
    # without hardcoding a path in the shared preview.yml
    labs_pages = REPO_ROOT / 'labs-pages'
    preview_local = labs_pages / 'preview-local.yml'
    preview_local.write_text(
        f"# Auto-generated by publish-to-labs.py — do not commit\n"
        f"content:\n"
        f"  sources:\n"
        f"  - url: {STAGING}\n"
        f"    branches: main\n"
    )
    print(f"  cfg  labs-pages/preview-local.yml written")


# ---------------------------------------------------------------------------
# Nav mode
# ---------------------------------------------------------------------------

def cmd_nav(integrations_map):
    """Print nav.adoc snippet for all integrations, grouped by category."""
    from collections import OrderedDict

    by_category: dict = OrderedDict()
    for entry in integrations_map:
        cat = entry.get('category', 'Other')
        by_category.setdefault(cat, []).append(entry)

    lines = []
    lines.append('**** Agent Integration Guides')

    for cat, entries in by_category.items():
        lines.append(f'***** {cat}')
        for entry in entries:
            slug = entry['slug']
            label = entry.get('nav_label', entry['title'])
            thin = entry.get('thin', False)
            prefix = '// ' if thin else ''
            xref = f'xref:genai-frameworks/{slug}.adoc[{label}]'
            lines.append(f'{prefix}****** {xref}')
            for sub in entry.get('sub_pages', []):
                sub_xref = f"xref:genai-frameworks/{sub['slug']}.adoc[{sub['nav_label']}]"
                lines.append(f'******* {sub_xref}')

    print('\n'.join(lines))
    return 0


# ---------------------------------------------------------------------------
# Validate mode (delegates to validate-adoc.py)
# ---------------------------------------------------------------------------

def cmd_validate(args):
    import subprocess
    labs_pages = _labs_pages_dir(args)
    PAGES_OUT = _pages_out(labs_pages)
    adoc_files = list(PAGES_OUT.glob('*.adoc'))
    if not adoc_files:
        print(f"No .adoc files found in {PAGES_OUT}")
        return 1
    validator = REPO_ROOT / 'scripts' / 'validate-adoc.py'
    if not validator.exists():
        print(f"ERROR: validate-adoc.py not found at {validator}", file=sys.stderr)
        return 1
    result = subprocess.run(
        [sys.executable, str(validator)] + [str(f) for f in adoc_files]
    )
    return result.returncode


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_slug_map():
    with open(SLUG_MAP, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data['integrations']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--convert', action='store_true',
                       help='Convert README.md files to AsciiDoc in _antora-staging/')
    group.add_argument('--nav', action='store_true',
                       help='Print nav.adoc snippet for all integrations')
    group.add_argument('--validate', action='store_true',
                       help='Run validator on existing _antora-staging/ files')
    parser.add_argument('--integrations', nargs='+', metavar='SLUG',
                        help='Limit conversion to these folder/slug names')
    parser.add_argument('--labs-pages-dir', metavar='PATH',
                        help='Path to labs-pages repo (default: $LABS_PAGES_DIR or ./labs-pages)')

    args = parser.parse_args()
    integrations = load_slug_map()

    if args.convert:
        sys.exit(cmd_convert(args, integrations))
    elif args.nav:
        sys.exit(cmd_nav(integrations))
    elif args.validate:
        sys.exit(cmd_validate(args))


if __name__ == '__main__':
    main()
