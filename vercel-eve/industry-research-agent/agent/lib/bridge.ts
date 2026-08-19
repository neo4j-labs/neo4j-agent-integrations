/**
 * Bridge edges — the join between what the agent remembers and what your app
 * actually knows.
 *
 * NAMS stores a `(:User)` node and hangs the user's memories off it. Your
 * product has its own graph: organizations, orders, documents, patients,
 * whatever your domain is. Keep those in two databases and memory can only
 * ever be recalled as text. Put them in **one** database and write an edge
 * from the memory graph's `User` to the real node each time a preference is
 * stored, and memory becomes traversable:
 *
 *     (u:User {userId})-[:TRACKS   {statedAs, since}]->(o:Organization)
 *     (u:User {userId})-[:FOCUSES_ON {statedAs, since}]->(c:IndustryCategory)
 *
 * Two properties of this that a vector store cannot reproduce:
 *
 *   - **Canonicalization.** "I follow neo4j" resolves to the one
 *     `Organization` node the rest of your product already uses, so a
 *     preference and a domain query mean the same thing by the same identity.
 *     An unmatched name links nothing rather than inventing a node.
 *   - **Explanation.** `statedAs` keeps the user's own words on the edge, so a
 *     recommendation can say why in their language, and the reason is read off
 *     the same edges that produced the row rather than generated next to it.
 *
 * Everything here needs a database you own; `NEO4J_BRIDGE=on` is the switch,
 * and `BRIDGE_ENABLED` gates the tools that use it.
 */
import { GRAPH_WRITABLE, readQuery, writeQuery } from "./neo4j";

export const BRIDGE_ENABLED = GRAPH_WRITABLE;

/** The interests a user can declare. Whitelisted, so the model picks an edge but never writes Cypher. */
const INTEREST = {
  company: {
    relType: "TRACKS",
    label: "Organization",
    /** Exact name first, then the graph's own full-text entity index. */
    match: `
      CALL {
        MATCH (n:Organization) WHERE n.name = $name RETURN n LIMIT 1
        UNION
        CALL db.index.fulltext.queryNodes('entity', $name) YIELD node, score
        WITH node WHERE node:Organization
        RETURN node AS n LIMIT 1
      }
      WITH n LIMIT 1`,
  },
  sector: {
    relType: "FOCUSES_ON",
    label: "IndustryCategory",
    match: `
      MATCH (n:IndustryCategory)
      WHERE toLower(n.name) = toLower($name)
      RETURN n LIMIT 1`,
  },
} as const;

export type InterestKind = keyof typeof INTEREST;

export interface BridgeResult {
  readonly linked: boolean;
  readonly kind: InterestKind;
  /** The canonical node name the edge points at, when one was found. */
  readonly canonical?: string;
  /** Near matches, when nothing matched exactly — so the agent can ask rather than guess. */
  readonly suggestions?: string[];
}

/**
 * Link a user to a domain node they said they care about.
 *
 * The `User` node is MERGEd (memory may not have created it yet) but the domain
 * node is only ever MATCHed: a misspelled company must fail to link, not
 * quietly add a second `Organization` that shadows the real one.
 */
export async function linkInterest(
  userId: string,
  kind: InterestKind,
  name: string,
  statedAs: string,
): Promise<BridgeResult> {
  const { relType, match } = INTEREST[kind];

  const rows = await writeQuery<{ canonical: string }>(
    `
    ${match}
    MERGE (u:User {userId: $userId})
    MERGE (u)-[r:${relType}]->(n)
      ON CREATE SET r.since = datetime(), r.statedAs = $statedAs
      ON MATCH  SET r.statedAs = $statedAs, r.lastConfirmed = datetime()
    RETURN n.name AS canonical
    `,
    { userId, name, statedAs },
  );

  if (rows.length > 0) return { linked: true, kind, canonical: rows[0].canonical };
  return { linked: false, kind, suggestions: await suggest(kind, name) };
}

/** Names close to what the user said, so an unmatched interest becomes a question. */
async function suggest(kind: InterestKind, name: string): Promise<string[]> {
  const { label } = INTEREST[kind];
  const rows = await readQuery<{ name: string }>(
    `MATCH (n:${label}) WHERE toLower(n.name) CONTAINS toLower($name)
     RETURN n.name AS name LIMIT 5`,
    { name },
  );
  return rows.map((r) => r.name);
}

export interface BriefRow {
  readonly company: string;
  readonly becauseYouFollow: string[];
  readonly headlines: string[];
}

/**
 * The payoff query: what should this user read that they are not already following?
 *
 * One traversal, and `becauseYouFollow` is the explanation — read off the very
 * edges that produced the row, so it cannot drift from the recommendation the
 * way a generated rationale can. Without bridge edges this is a vector lookup
 * plus a post-filter plus a second call to explain the result.
 */
export async function dailyBrief(
  userId: string,
  { days = 90, limit = 10 }: { days?: number; limit?: number } = {},
): Promise<BriefRow[]> {
  return readQuery<BriefRow>(
    `
    // "Recent" is relative to the newest article the graph actually has, not to
    // today. A live news feed puts that at ~now and this behaves as expected; a
    // loaded dataset stops silently returning nothing the moment it ages past
    // the window. Future-dated rows are excluded first — real corpora carry
    // them, and one bad row would drag the anchor years forward.
    CALL {
      MATCH (a:Article)
      WHERE a.date IS NOT NULL AND a.date <= datetime()
      RETURN max(a.date) AS newest
    }
    WITH coalesce(newest, datetime()) AS anchor

    MATCH (u:User {userId: $userId})-[:FOCUSES_ON]->(cat:IndustryCategory)
    MATCH (o:Organization)-[:HAS_CATEGORY]->(cat)
    WHERE NOT (u)-[:TRACKS]->(o)                       // novelty: not already followed
    MATCH (a:Article)-[:MENTIONS]->(o)
      // datetime(), not date(): a.date is a DateTime, and comparing a DateTime
      // to a Date yields null rather than false, so a date() bound silently
      // filters out every row instead of failing.
      WHERE a.date >= anchor - duration({days: toInteger($days)})
    RETURN o.name                          AS company,
           collect(DISTINCT cat.name)      AS becauseYouFollow,
           collect(DISTINCT a.title)[0..3] AS headlines
    ORDER BY size(headlines) DESC
    LIMIT toInteger($limit)
    `,
    { userId, days, limit },
  );
}

/** Everything this user is linked to, for a "what do you know about me?" answer. */
export async function listInterests(userId: string): Promise<{
  tracking: string[];
  focusedOn: string[];
}> {
  const rows = await readQuery<{ tracking: string[]; focusedOn: string[] }>(
    `
    MATCH (u:User {userId: $userId})
    RETURN [(u)-[:TRACKS]->(o:Organization)      | o.name] AS tracking,
           [(u)-[:FOCUSES_ON]->(c:IndustryCategory) | c.name] AS focusedOn
    `,
    { userId },
  );
  return rows[0] ?? { tracking: [], focusedOn: [] };
}
