---
description: Use before answering any research question about a company, its competitive position, its investors, or the news written about it — how to query the graph and how to report what it returns.
---

# Research rules

The domain tools are read-only views of one Neo4j graph: `search_news` is
authored over the Bolt driver, the `neo4j-graph__*` tools come from the official
Neo4j MCP server. These are the rules for using them; they are not repeated in
the system prompt, so load this before a research answer rather than guessing at
the procedure.

## Order of resort

1. **`search_news`** — anything of the form "what's been written about X".
   Short keyword queries, not sentences: `graph database funding`, not
   `what has been written about funding rounds in the graph database space`.
2. **`neo4j-graph__get-schema`**, then **`neo4j-graph__read-cypher`** —
   everything structural: investors, subsidiaries, industries, counts. Read the
   schema before writing the query; do not guess at a label or relationship
   type. The server refuses writes, so a query is always safe to try.
   Investors hang off `(:Organization)-[:HAS_INVESTOR]->(i)`, which is not the
   direction or the name "who invested in X" suggests — check the schema rather
   than inverting it from memory.
3. **Nothing** — if the graph does not answer it, say so. Do not fall back to
   background knowledge and present it as a finding.

## Names in the graph are exact

`Organization.name` is a literal string from the source data. A search that
returns nothing is usually a name mismatch, not an absence: retry with the
shorter or more common form (`Neo4j`, not `Neo4j, Inc.`) before concluding the
graph has nothing. When a lookup turns up several near misses, ask which the
analyst meant instead of picking one.

## Report what the graph returned

- Cite article **titles and dates** for anything that came from `search_news`.
  A claim with no title behind it reads as a fact about the world; it is a fact
  about this dataset.
- Say when coverage is thin ("three articles, all from 2022") rather than
  smoothing over it. The dataset is a fixed snapshot, not the live web.
- Keep the graph's answer and your own reading of it in separate sentences.

## Memory is context, not evidence

Anything recalled about the analyst — the sectors they follow, the companies
they track, how they like answers formatted — shapes *what you look up and how
you report it*. It is never a source for a claim about a company. If memory and
the graph disagree, the graph wins and you say so.
