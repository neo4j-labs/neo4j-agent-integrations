import { defineTool } from "eve/tools";
import { z } from "zod";
import { readQuery } from "../lib/neo4j";

/**
 * Full-text search across article chunks.
 *
 * The graph also carries vector embeddings on `:Chunk` (index `news`), but
 * those were built with OpenAI `text-embedding-ada-002`; querying them with a
 * different embedding model returns confident nonsense. Full text needs no
 * embedding call at all, so it works whichever model the agent is routed to.
 * See the README for the vector variant.
 */
export default defineTool({
  description:
    "Search news articles about companies and industry themes. " +
    "Returns article titles, dates, publishers, sentiment, and the matching passage. " +
    "Use short keyword queries ('graph database funding', 'chip export controls'), not sentences.",
  inputSchema: z.object({
    query: z.string().min(2).describe("Keywords to search for across news article text"),
    limit: z.number().int().min(1).max(20).default(5),
  }),
  async execute({ query, limit }) {
    const rows = await readQuery<{
      title: string;
      date: string | null;
      site: string | null;
      sentiment: number | null;
      passage: string;
      organizations: string[];
    }>(
      `
      CALL db.index.fulltext.queryNodes('news_fulltext', $query) YIELD node, score
      MATCH (a:Article)-[:HAS_CHUNK]->(node)
      RETURN a.title    AS title,
             toString(a.date) AS date,
             a.siteName AS site,
             a.sentiment AS sentiment,
             left(node.text, 400) AS passage,
             [(a)-[:MENTIONS]->(o:Organization) | o.name][0..5] AS organizations
      ORDER BY score DESC
      LIMIT toInteger($limit)
      `,
      { query, limit },
    );

    return {
      query,
      count: rows.length,
      articles: rows,
      ...(rows.length === 0 && {
        message: `No articles matched "${query}". Try broader or different keywords.`,
      }),
    };
  },
});
