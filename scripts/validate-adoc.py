#!/usr/bin/env python3
"""validate-adoc.py — Validate AsciiDoc files produced by publish-to-labs.py.

Usage:
    python3 scripts/validate-adoc.py [OPTIONS] [FILES...]

Options:
    --check-links   Enable external URL reachability checks (slow)
    --strict        Treat WARN as ERROR for exit code purposes
    --rule RULE_ID  Run only the specified rule(s) (repeatable)
    --skip RULE_ID  Skip the specified rule(s) (repeatable)
    --format json   Emit findings as JSON array
    --summary-only  Print only the summary line
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class Finding:
    __slots__ = ('severity', 'file', 'line', 'rule', 'message')

    def __init__(self, severity, file, line, rule, message):
        self.severity = severity   # ERROR | WARN | INFO
        self.file = file
        self.line = line           # 1-based or None
        self.rule = rule
        self.message = message

    def __str__(self):
        loc = f'{self.file}:{self.line}' if self.line else str(self.file)
        return f'{self.severity:<5}  {loc:<55}  [{self.rule}]  {self.message}'


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_file(path: Path, check_links: bool, rule_filter: set, skip: set) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines()
    fname = str(path)

    def emit(severity, lineno, rule, message):
        if rule_filter and rule not in rule_filter:
            return
        if rule in skip:
            return
        findings.append(Finding(severity, fname, lineno, rule, message))

    # ── Parser state ──────────────────────────────────────────────────────
    in_code_block = False
    code_delim_count = 0
    in_block_comment = False
    block_comment_count = 0
    in_passthrough = False
    passthrough_count = 0
    in_table = False
    table_delim_count = 0
    sidebar_count = 0
    example_count = 0

    top_heading_count = 0
    current_heading_level = 0
    frontmatter_attrs = set()
    frontmatter_done = False
    frontmatter_lines = 0

    urls_seen: list[tuple[int, str]] = []  # (lineno, url) for --check-links

    for lineno, line in enumerate(lines, start=1):

        # ── Track frontmatter (first 15 lines) ────────────────────────────
        if lineno <= 15:
            if re.match(r'^= ', line):
                frontmatter_attrs.add('title')
            for attr in (':slug:', ':category:', ':tags:', ':page-product:'):
                if line.startswith(attr):
                    frontmatter_attrs.add(attr.strip(':'))

        # ── Block comment handling ────────────────────────────────────────
        if line.strip() == '////' and not in_code_block:
            block_comment_count += 1
            in_block_comment = not in_block_comment
            continue

        # ── Single-line comment — skip all rule checks for this line ─────
        if re.match(r'^\s*//', line) and not in_code_block and not in_block_comment:
            # V-C01
            xref_in_comment = re.search(r'xref:', line)
            url_in_comment = re.search(r'https?://', line)
            if xref_in_comment or url_in_comment:
                emit('INFO', lineno, 'V-C01', f'Commented-out link (not validated): {line.strip()}')
            continue

        if in_block_comment:
            continue

        # ── Code block delimiters ─────────────────────────────────────────
        if line.strip() == '----' and not in_passthrough:
            code_delim_count += 1
            in_code_block = not in_code_block
            continue

        # ── Passthrough block delimiters ─────────────────────────────────
        if line.strip() == '++++':
            passthrough_count += 1
            in_passthrough = not in_passthrough
            continue

        if in_passthrough:
            continue

        # ── Table delimiters ─────────────────────────────────────────────
        if line.strip() == '|===':
            table_delim_count += 1
            in_table = not in_table
            continue

        # ── Sidebar / example block delimiters ───────────────────────────
        if line.strip() == '****' and not in_code_block:
            sidebar_count += 1
        if line.strip() == '====' and not in_code_block:
            example_count += 1

        # ── V-M01: Markdown heading ───────────────────────────────────────
        if not in_code_block and re.match(r'^#{1,6} ', line):
            emit('ERROR', lineno, 'V-M01', f'Markdown heading: {line.strip()!r}')
            continue

        # ── V-M02: Markdown fenced code block ─────────────────────────────
        if not in_code_block and re.match(r'^```', line):
            emit('ERROR', lineno, 'V-M02', f'Markdown code fence: {line.strip()!r}')
            continue

        if in_code_block:
            continue  # skip rule checks inside code blocks

        # ── V-M03: Markdown bold ──────────────────────────────────────────
        if re.search(r'\*\*[^*\n]+\*\*', line):
            emit('WARN', lineno, 'V-M03', f'Markdown double-asterisk bold in: {line.strip()!r}')

        # ── V-M04: Markdown inline link ───────────────────────────────────
        if re.search(r'(?<!!)\[([^\]]+)\]\(([^)]+)\)', line):
            emit('ERROR', lineno, 'V-M04', f'Markdown link syntax: {line.strip()!r}')

        # ── V-M05: Markdown reference-style link ──────────────────────────
        if re.search(r'\[[^\]]+\]\[[^\]]*\]', line):
            emit('WARN', lineno, 'V-M05', f'Markdown reference-style link: {line.strip()!r}')

        # ── V-M06: Markdown image ─────────────────────────────────────────
        if re.search(r'!\[([^\]]*)\]\(([^)]+)\)', line):
            emit('ERROR', lineno, 'V-M06', f'Markdown image syntax: {line.strip()!r}')

        # ── V-M07: Markdown horizontal rule ──────────────────────────────
        if re.match(r'^\s*(---+|___+|\*\*\*+)\s*$', line):
            emit('WARN', lineno, 'V-M07', f'Markdown horizontal rule: {line.strip()!r}')

        # ── V-M08: Markdown blockquote ────────────────────────────────────
        if re.match(r'^>\s', line):
            emit('WARN', lineno, 'V-M08', f'Markdown blockquote: {line.strip()!r}')

        # ── V-M09: Markdown task list ─────────────────────────────────────
        if re.match(r'^\s*[-*] \[[ xX]\]', line):
            emit('WARN', lineno, 'V-M09', f'Markdown task list item: {line.strip()!r}')

        # ── V-M10: Markdown table separator ──────────────────────────────
        if not in_table and re.match(r'^\|?[\s\-:]+\|[\s\-:|]+$', line):
            emit('ERROR', lineno, 'V-M10', f'Markdown table separator row: {line.strip()!r}')

        # ── V-C03: HTML/Markdown comment artefact ────────────────────────
        if '<!--' in line:
            emit('WARN', lineno, 'V-C03', f'HTML comment artefact: {line.strip()!r}')

        # ── V-S04: Table row structure ────────────────────────────────────
        if in_table and line.strip() and not line.strip().startswith('|') \
                and not line.strip().startswith('[') and not line.strip() == '':
            emit('WARN', lineno, 'V-S04', f'Table row does not start with |: {line.strip()!r}')

        # ── V-S05: Heading level skip ─────────────────────────────────────
        adoc_h = re.match(r'^(={2,6}) ', line)
        if adoc_h:
            level = len(adoc_h.group(1))  # == is level 1, etc.
            if level - current_heading_level > 1 and current_heading_level > 0:
                emit('WARN', lineno, 'V-S05',
                     f'Heading level skip from {"=" * (current_heading_level + 1)} to {"=" * (level + 1)}')
            current_heading_level = level

        # ── V-S06: Repeated top-level heading ────────────────────────────
        if re.match(r'^= [^=]', line):
            top_heading_count += 1
            if top_heading_count > 1:
                emit('ERROR', lineno, 'V-S06',
                     f'Extra top-level heading (= title) — only one allowed: {line.strip()!r}')

        # ── V-L01: Bare URL ───────────────────────────────────────────────
        for url_m in re.finditer(r'https?://[^\s\[<]+', line):
            url = url_m.group(0)
            # Check if followed by [  (i.e. it's already a proper AsciiDoc link)
            pos_after = url_m.end()
            if pos_after >= len(line) or line[pos_after] != '[':
                emit('INFO', lineno, 'V-L01', f'Bare URL (no link text): {url}')
            urls_seen.append((lineno, url))

        # ── V-L02: xref target check (files only) ────────────────────────
        for xref_m in re.finditer(r'xref:([^[\]]+)\[', line):
            target = xref_m.group(1)
            # Only check relative targets without version prefix
            if not target.startswith('http') and '.adoc' in target:
                # We'll check existence post-loop (needs file set)
                pass

        # ── V-Q02: Placeholder text ───────────────────────────────────────
        if re.search(r'\b(TODO|FIXME)\b|lorem ipsum|\[placeholder\]|coming soon', line, re.IGNORECASE):
            emit('WARN', lineno, 'V-Q02', f'Placeholder text: {line.strip()!r}')

        # ── V-Q03: Overly long line ───────────────────────────────────────
        if len(line) > 300 and not in_table:
            emit('INFO', lineno, 'V-Q03', f'Line exceeds 300 chars ({len(line)} chars)')

    # ── Post-loop structural checks ───────────────────────────────────────

    # V-C02: Block comment balance
    if block_comment_count % 2 != 0:
        emit('ERROR', None, 'V-C02',
             f'Odd number of //// block comment delimiters ({block_comment_count}) — unclosed block comment')

    # V-S01: Code block delimiter balance
    if code_delim_count % 2 != 0:
        emit('ERROR', None, 'V-S01',
             f'Odd number of ---- delimiters ({code_delim_count}) — unclosed code block')

    # V-S02: Passthrough block balance
    if passthrough_count % 2 != 0:
        emit('ERROR', None, 'V-S02',
             f'Odd number of ++++ delimiters ({passthrough_count}) — unclosed passthrough block')

    # V-S03: Table delimiter balance
    if table_delim_count % 2 != 0:
        emit('ERROR', None, 'V-S03',
             f'Odd number of |=== delimiters ({table_delim_count}) — unclosed table')

    # V-S07: Missing frontmatter attributes
    required = {'title', 'slug', 'category', 'tags', 'page-product'}
    missing = required - frontmatter_attrs
    if missing:
        emit('ERROR', None, 'V-S07',
             f'Missing frontmatter attributes: {", ".join(sorted(missing))}')

    # V-S08: Sidebar/example block balance
    if sidebar_count % 2 != 0:
        emit('WARN', None, 'V-S08',
             f'Odd number of **** sidebar delimiters ({sidebar_count})')
    if example_count % 2 != 0:
        emit('WARN', None, 'V-S08',
             f'Odd number of ==== example delimiters ({example_count})')

    # V-Q01: Empty page body
    non_frontmatter = [l for l in lines[15:] if l.strip()]
    if not non_frontmatter:
        emit('ERROR', None, 'V-Q01', 'Page body is empty after frontmatter')

    # V-L03: External URL reachability (optional)
    if check_links and urls_seen:
        import urllib.request
        import urllib.error
        skip_hosts = {'localhost', '127.0.0.1', 'example.com', 'demo.neo4jlabs.com'}
        for lineno, url in urls_seen:
            host = re.match(r'https?://([^/]+)', url)
            if host and host.group(1) in skip_hosts:
                continue
            try:
                req = urllib.request.Request(url, method='HEAD',
                                             headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code = resp.status
                    if 300 <= code < 400:
                        emit('INFO', lineno, 'V-L03', f'Redirect ({code}): {url}')
            except urllib.error.HTTPError as e:
                if e.code >= 400:
                    emit('WARN', lineno, 'V-L03', f'HTTP {e.code}: {url}')
            except Exception as e:
                emit('WARN', lineno, 'V-L03', f'Unreachable ({e}): {url}')

    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', help='.adoc files to validate')
    parser.add_argument('--check-links', action='store_true')
    parser.add_argument('--strict', action='store_true',
                        help='Treat WARN as ERROR for exit code')
    parser.add_argument('--rule', action='append', default=[], metavar='RULE_ID',
                        dest='rules', help='Run only these rule(s)')
    parser.add_argument('--skip', action='append', default=[], metavar='RULE_ID')
    parser.add_argument('--format', choices=['text', 'json'], default='text')
    parser.add_argument('--summary-only', action='store_true')

    args = parser.parse_args()

    # Resolve files
    if args.files:
        paths = []
        for pattern in args.files:
            p = Path(pattern)
            if p.is_file():
                paths.append(p)
            else:
                # Glob expansion (shell may not have expanded)
                paths.extend(Path('.').glob(pattern))
    else:
        base = Path('_antora-staging/modules/genai-ecosystem/pages/genai-frameworks')
        paths = list(base.glob('**/*.adoc'))

    if not paths:
        print('No .adoc files to validate.')
        sys.exit(0)

    rule_filter = set(args.rules)
    skip = set(args.skip)

    all_findings: list[Finding] = []
    for path in sorted(paths):
        file_findings = validate_file(path, args.check_links, rule_filter, skip)
        all_findings.extend(file_findings)

    errors = sum(1 for f in all_findings if f.severity == 'ERROR')
    warns = sum(1 for f in all_findings if f.severity == 'WARN')
    infos = sum(1 for f in all_findings if f.severity == 'INFO')

    if args.format == 'json':
        data = [{'severity': f.severity, 'file': f.file, 'line': f.line,
                 'rule': f.rule, 'message': f.message} for f in all_findings]
        if not args.summary_only:
            print(json.dumps(data, indent=2))
    else:
        if not args.summary_only:
            for f in all_findings:
                print(f)

    summary = (f'Validated {len(paths)} file(s): '
               f'{errors} error(s), {warns} warning(s), {infos} info')
    print(summary)

    # Exit code
    fail_count = errors
    if args.strict:
        fail_count += warns
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == '__main__':
    main()
