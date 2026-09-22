// Connection settings for the Company News graph.
// MCP runs Cypher; Bolt runs full-text search, which MCP can't.
import neo4j, { type Driver } from "neo4j-driver";

// Hosted Neo4j MCP server, used by connections/neo4j-graph.ts

const DEFAULT_URL = "https://neo4j-mcp-official-1008050579172.us-central1.run.app/mcp";

export const MCP_URL = process.env.MCP_URL ?? DEFAULT_URL;

const MCP_USERNAME = process.env.MCP_NEO4J_USERNAME ?? "companies";
const MCP_PASSWORD = process.env.MCP_NEO4J_PASSWORD ?? "companies";

export const MCP_TOOLS = ["get-schema", "read-cypher", "list-gds-procedures"] as const;

export function neo4jMcpHeaders(): Record<string, string> {
  const encoded = Buffer.from(`${MCP_USERNAME}:${MCP_PASSWORD}`).toString("base64");
  return { Authorization: `Basic ${encoded}` };
}

// Local MCP server, used by connections/neo4j-investments.ts.
// Keep this default in sync with scripts/chat.mjs.

export const INVESTMENTS_MCP_URL =
  process.env.INVESTMENTS_MCP_URL?.trim() || "http://localhost:8100/mcp";

// Direct database connection (Bolt), used by tools/search_news.ts

const BOLT_URI = process.env.NEO4J_URI ?? "neo4j+s://demo.neo4jlabs.com:7687";
const BOLT_USERNAME = process.env.NEO4J_USERNAME ?? "companies";
const BOLT_PASSWORD = process.env.NEO4J_PASSWORD ?? "companies";
const DATABASE = process.env.NEO4J_DATABASE ?? "companies";

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(BOLT_URI, neo4j.auth.basic(BOLT_USERNAME, BOLT_PASSWORD), {
    maxConnectionPoolSize: 10,
    connectionAcquisitionTimeout: 10_000,
  });
  return driver;
}

/** Run a read-only Cypher query and return plain JSON rows. */
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

/** Turn Neo4j values (big ints, dates) into plain JSON. */
function toPlain(value: unknown): unknown {
  if (value === null || value === undefined) return null;
  if (neo4j.isInt(value)) {
    return value.inSafeRange() ? value.toNumber() : value.toString();
  }
  if (Array.isArray(value)) return value.map(toPlain);
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") {
    // Neo4j dates and times: use their string form.
    if ("toString" in value && value.constructor?.name?.startsWith("Date")) {
      return String(value);
    }
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, toPlain(v)]));
  }
  return value;
}
