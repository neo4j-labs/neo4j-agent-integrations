/**
 * Neo4j — both routes to the Company News knowledge graph.
 *
 * One database (250k Diffbot entities: organizations, people, cities, industry
 * categories, and the news articles that mention them), reached two ways:
 *
 *   MCP  — the default. `connections/neo4j-graph.ts` mounts the official Neo4j
 *          MCP server, which owns schema introspection and read-only Cypher.
 *          Nothing here to maintain but the endpoint and the allow-list.
 *   Bolt — the driver, for the one thing MCP cannot do here: `search_news`
 *          queries a full-text index the MCP server publishes no tool for.
 *
 * They live in one file because they are one decision — how this agent reaches
 * the graph — and reading them apart hides that the second exists only because
 * of a gap in the first.
 *
 * Read-only by construction on both routes: there is no write path in this
 * file, and the MCP server refuses writes on its own side.
 */
import neo4j, { type Driver } from "neo4j-driver";

// ---------------------------------------------------------------------------
// Route 1 — MCP. Consumed by `connections/neo4j-graph.ts`.
//
// The server authenticates with HTTP Basic, not Bearer: it answers an
// unauthenticated request with `WWW-Authenticate: Basic realm="Neo4j MCP
// Server"`. eve's `auth.getToken` always sends `Authorization: Bearer <token>`,
// so the credentials go through `headers` instead — which is why this is a
// header builder rather than an auth provider.
// ---------------------------------------------------------------------------

const DEFAULT_URL = "https://neo4j-mcp-official-1008050579172.us-central1.run.app/mcp";

export const MCP_URL = process.env.MCP_URL ?? DEFAULT_URL;

const MCP_USERNAME = process.env.MCP_NEO4J_USERNAME ?? "companies";
const MCP_PASSWORD = process.env.MCP_NEO4J_PASSWORD ?? "companies";

/**
 * The three tools the server publishes today, all read-only.
 *
 * Kept as an explicit allow-list rather than "whatever the server lists":
 * `read-cypher`'s own description points at a `write-cypher` sibling, so a
 * server-side change could hand the model a write tool against a shared demo
 * instance. Naming the three we want means that can't happen silently.
 */
export const MCP_TOOLS = ["get-schema", "read-cypher", "list-gds-procedures"] as const;

/**
 * Headers that authenticate every request to the MCP server.
 *
 * Passed to `defineMcpClientConnection({ headers })`, which accepts a callback
 * and re-resolves it per request, so rotating the env vars does not require a
 * redeploy of anything holding a cached token.
 */
export function neo4jMcpHeaders(): Record<string, string> {
  const encoded = Buffer.from(`${MCP_USERNAME}:${MCP_PASSWORD}`).toString("base64");
  return { Authorization: `Basic ${encoded}` };
}

// ---------------------------------------------------------------------------
// Route 2 — Bolt. Consumed by `tools/search_news.ts`.
// ---------------------------------------------------------------------------

const BOLT_URI = process.env.NEO4J_URI ?? "neo4j+s://demo.neo4jlabs.com:7687";
const BOLT_USERNAME = process.env.NEO4J_USERNAME ?? "companies";
const BOLT_PASSWORD = process.env.NEO4J_PASSWORD ?? "companies";
const DATABASE = process.env.NEO4J_DATABASE ?? "companies";

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(BOLT_URI, neo4j.auth.basic(BOLT_USERNAME, BOLT_PASSWORD), {
    // Serverless invocations are short-lived; a small pool avoids holding
    // connections open past the request that opened them.
    maxConnectionPoolSize: 10,
    connectionAcquisitionTimeout: 10_000,
  });
  return driver;
}

/**
 * Run a read-only Cypher query and return plain JSON rows.
 *
 * `READ` access mode is pinned at the driver rather than trusted to the query
 * text, so a write clause fails no matter what the query says. Neo4j integers
 * are narrowed to JS numbers so results survive eve's durable JSON boundary.
 */
export async function readQuery<T = Record<string, unknown>>(
  cypher: string,
  params: Record<string, unknown> = {},
): Promise<T[]> {
  const { records } = await getDriver().executeQuery(cypher, params, {
    database: DATABASE,
    routing: "READ",
  });
  return records.map((record) => toPlain(record.toObject()) as T);
}

/** Recursively convert Neo4j Integers (and other driver types) to JSON-safe values. */
function toPlain(value: unknown): unknown {
  if (value === null || value === undefined) return null;
  if (neo4j.isInt(value)) {
    return value.inSafeRange() ? value.toNumber() : value.toString();
  }
  if (Array.isArray(value)) return value.map(toPlain);
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") {
    // Temporal types (Date, DateTime, ...) all stringify usefully.
    if ("toString" in value && value.constructor?.name?.startsWith("Date")) {
      return String(value);
    }
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toPlain(v)]));
  }
  return value;
}
