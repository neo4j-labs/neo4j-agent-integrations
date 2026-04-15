# AsciiDoc Conversion Validator — Specification

Validates `.adoc` files produced by `publish-to-labs.py` for conversion artefacts,
structural integrity, and link health. The validator operates on a single file or
a directory glob and exits non-zero if any ERROR-level finding is present.

---

## Severity levels

| Level | Meaning |
|-------|---------|
| `ERROR` | Must be fixed before publish. Indicates broken rendering or unconverted Markdown. |
| `WARN`  | Should be reviewed. May render incorrectly or degrade quality. |
| `INFO`  | Advisory only. Does not block publish. |

---

## Parser state — what the validator must track

Before applying any rule, the validator maintains a line-by-line state machine:

| State flag | Set when | Cleared when |
|------------|----------|--------------|
| `in_code_block` | line is exactly `----` (delimiter) and not in comment | next `----` delimiter |
| `in_listing_block` | line is `[source,…]` followed by `----` | closing `----` |
| `in_passthrough` | line is `++++` | next `++++` |
| `in_block_comment` | line is exactly `////` and not in code block | next `////` |
| `in_sidebar` | line is `****` block delimiter | closing `****` |
| `in_example` | line is `====` block delimiter | closing `====` |
| `in_table` | line is `\|===` | closing `\|===` |

Rules that detect leaked Markdown or AsciiDoc structure issues apply **only when
all of the following are false**: `in_code_block`, `in_listing_block`,
`in_passthrough`, `in_block_comment`.

Single-line AsciiDoc comments (`//` prefix, not `///`) suppress rule checks
**on that line only**.

---

## Rule groups

### Group 1 — Comment handling

#### V-C01 · Single-line comment detection (INFO)
A line whose first non-whitespace characters are `//` followed by a space or end-of-line
(and not `///`, which is valid content) is an AsciiDoc single-line comment.
- The validator must record this line as commented and skip all other rule checks for it.
- If the comment contains what looks like an `xref:` or URL, emit INFO noting it is
  commented-out and will not be validated for link health.

```
// xref:langgraph.adoc[LangGraph]     ← INFO: xref in comment, not validated
// TODO: add authentication section   ← skipped
```

#### V-C02 · Block comment open/close balance (ERROR)
Count `////` delimiters that are:
- Not inside a code block (`in_code_block = false`)
- On a line by themselves (no other content)

The total count must be even. An odd count means an unclosed block comment,
which silently swallows all content that follows it.

#### V-C03 · Markdown comment artefact (WARN)
Detect HTML/Markdown comment syntax that was not converted:
```
<!-- ... -->
```
Pattern: line contains `<!--` outside a passthrough block (`++++`).
These are invisible in AsciiDoc but indicate a conversion miss.

---

### Group 2 — Leaked Markdown syntax

Rules in this group apply only outside state flags (see parser state above).

#### V-M01 · Markdown heading (ERROR)
Line matches `^#{1,6} ` (one to six `#` characters followed by a space).

```
## Overview         ← ERROR: unconverted Markdown heading
### Extension Points ← ERROR
```

Exception: a single `#!` shebang on line 1 is allowed.

#### V-M02 · Markdown fenced code block (ERROR)
Line starts with ` ``` ` (three backticks), optionally followed by a language tag.

```
```python           ← ERROR: unconverted Markdown code fence
```                 ← ERROR
```

#### V-M03 · Markdown bold (WARN)
Line contains `**text**` where `text` is one or more non-asterisk characters.
Pattern: `\*\*[^*]+\*\*`

AsciiDoc bold uses single asterisks `*text*`. Double asterisks are unconstrained
bold in AsciiDoc and may render unexpectedly.

#### V-M04 · Markdown link syntax (ERROR)
Line contains an unconverted Markdown inline link.
Pattern: `\[([^\]]+)\]\(([^)]+)\)` where the leading character is not `!`
(images are covered by V-M06).

```
[LangGraph documentation](https://example.com)   ← ERROR
```

AsciiDoc form: `https://example.com[LangGraph documentation^]`

#### V-M05 · Markdown reference-style link (WARN)
Line matches `\[[^\]]+\]\[[^\]]*\]` — a reference-style link like `[text][ref]`.
These are invisible in AsciiDoc output.

#### V-M06 · Markdown image syntax (ERROR)
Line contains `![alt](url)` — unconverted Markdown image.
Pattern: `!\[([^\]]*)\]\(([^)]+)\)`

AsciiDoc form: `image::url[alt]`

#### V-M07 · Markdown horizontal rule (WARN)
A line consisting entirely of `---` or `***` or `___` (three or more).
AsciiDoc horizontal rule is `'''`.

#### V-M08 · Markdown blockquote (WARN)
Line starts with `> `.
AsciiDoc equivalent is a NOTE/TIP admonition or a `[quote]` block.

#### V-M09 · Markdown task list item (WARN)
Line matches `^\s*[-*] \[[ xX]\]`.
AsciiDoc has no native checkbox list; these should be converted to plain bullets
or a custom callout.

#### V-M10 · Markdown table separator row (ERROR)
Line matches `^\|?[\s\-:]+\|[\s\-:|]+$` — a `|---|---` separator row outside
a code block. These are structural artefacts from an incomplete table conversion.

---

### Group 3 — AsciiDoc structural integrity

#### V-S01 · Code block delimiter balance (ERROR)
Count `----` lines that are:
- Not inside a block comment
- Not inside a passthrough block (`++++`)

The total must be even. An odd count means an unclosed listing block, which
consumes all subsequent content as literal text.

Track delimiter context: a `[source,…]` or `[listing]` attribute line
immediately before a `----` opens a listing block; the next `----` closes it.

#### V-S02 · Passthrough block delimiter balance (ERROR)
Count `++++` lines outside block comments. Total must be even.
Unclosed passthrough blocks cause all subsequent AsciiDoc to be emitted as raw HTML.

#### V-S03 · Table delimiter balance (ERROR)
Count `|===` lines outside code blocks and block comments. Total must be even.

#### V-S04 · Table row structure (WARN)
Inside a table block (between `|===` delimiters), each non-empty, non-attribute line
should start with `|`. Lines that do not start with `|` and are not blank or
attribute lines (e.g. `[cols=…]`) indicate a malformed table row.

#### V-S05 · Heading level skip (WARN)
Track the current heading depth. A heading that jumps more than one level
(e.g. from `==` directly to `====`) should emit a WARN.

Frontmatter heading (`=`) is level 0; `==` is level 1, `===` is level 2, etc.

#### V-S06 · Repeated top-level heading (ERROR)
A file must have exactly one `= Title` line (the page title, in the frontmatter
header block). Any additional `= ` heading in the body indicates the first
Markdown `#` heading was not skipped during conversion.

#### V-S07 · Missing frontmatter attributes (ERROR)
The first 15 lines of the file must contain all of:
- `= ` (page title)
- `:slug:`
- `:category:`
- `:tags:`
- `:page-product:`

Missing attributes cause the page to be excluded from site search and navigation.

#### V-S08 · Sidebar/example block delimiter balance (WARN)
Count `****` (sidebar) and `====` (example) delimiter lines outside code blocks
and block comments. Each must appear an even number of times.

---

### Group 4 — Link and reference health

#### V-L01 · Bare URL without link text (INFO)
A URL (`https?://[^\s\[]+`) that is not followed by `[` is a bare link.
AsciiDoc renders bare URLs as-is, which is often intentional, but worth flagging
for review.

#### V-L02 · Internal xref target exists (WARN — requires file-set context)
An `xref:([^[]+)` reference — the target page path (relative to the current
module's `pages/` root) must exist in the set of pages being validated or in
the known labs-pages page set.

Emit WARN (not ERROR) because cross-repo xrefs may legitimately point at pages
in labs-pages that are not present in this repo's file set.

#### V-L03 · External URL reachability (WARN — optional, slow)
When `--check-links` flag is passed, perform HTTP HEAD requests for all
`https?://[^\s\[]+` URLs found outside comments and code blocks.

- 2xx → OK
- 3xx → INFO (redirect, note final destination)
- 4xx / 5xx / timeout → WARN (not ERROR, because external URLs may have
  rate limits or transient failures)

Skip URLs matching a configurable allowlist (e.g. `localhost`, `demo.neo4jlabs.com`
demo database, `example.com`).

#### V-L04 · Image URL reachability (WARN — optional, with `--check-links`)
`image::url[…]` and `image:url[…]` references are checked the same way as V-L03.

---

### Group 5 — Content quality

#### V-Q01 · Empty page body (ERROR)
After stripping the frontmatter header block (everything up to and including the
first blank line after the last `:attribute:` line), the remaining content must
contain at least one non-blank line. A page with only frontmatter will render as
a blank page.

#### V-Q02 · Placeholder text present (WARN)
Line contains any of:
- `TODO`
- `FIXME`
- `lorem ipsum`
- `coming soon` (case-insensitive)
- `[placeholder]`

#### V-Q03 · Overly long line in prose (INFO)
A non-code, non-table line exceeding 300 characters. Often indicates a paragraph
that was not line-wrapped during conversion, which is harmless but reduces
diff readability.

---

## Output format

Each finding is one line:

```
{severity}  {file}:{line}  [{rule-id}]  {message}
```

Example:

```
ERROR  genai-frameworks/langgraph.adoc:42   [V-M01]  Markdown heading: "## Overview"
WARN   genai-frameworks/crewai.adoc:17      [V-M03]  Markdown bold syntax: "**CrewAI**"
ERROR  genai-frameworks/aws-agentcore.adoc  [V-S01]  Odd number of code block delimiters (3) — unclosed block
WARN   genai-frameworks/databricks.adoc:88  [V-L02]  xref target not found: integrations/mlflow.adoc
INFO   genai-frameworks/langchain.adoc:204  [V-L01]  Bare URL (no link text): https://python.langchain.com/...
```

Summary line at end:

```
Validated 26 files: 0 errors, 3 warnings, 5 info  ← exit 0
Validated 26 files: 2 errors, 3 warnings, 5 info  ← exit 1
```

---

## CLI interface

```
python3 scripts/validate-adoc.py [OPTIONS] [FILES...]

Arguments:
  FILES           One or more .adoc files or glob patterns.
                  Default: modules/genai-ecosystem/pages/genai-frameworks/**/*.adoc

Options:
  --check-links   Enable external URL reachability checks (V-L03, V-L04). Slow.
  --strict        Treat WARN as ERROR for exit code purposes.
  --rule RULE_ID  Run only the specified rule(s). Repeatable.
  --skip RULE_ID  Skip the specified rule(s). Repeatable.
  --format json   Emit findings as JSON array instead of plain text.
  --summary-only  Print only the summary line, suppress per-finding output.
```

---

## Integration points

- **In `publish-to-labs.py`**: call validator automatically after `--convert`.
  Abort if any ERROR is found, print findings inline.
- **In CI (GitHub Actions)**: run `validate-adoc.py --strict` on every PR that
  touches an integration `README.md` or `README.adoc`.
- **In labs-pages pre-build**: run validator before Antora so broken files are
  caught before the Antora build (which may surface errors less clearly).
