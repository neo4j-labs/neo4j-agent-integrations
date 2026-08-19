/**
 * Access to the Company News knowledge graph.
 *
 * Defaults to the public Neo4j demo instance (250k Diffbot entities:
 * organizations, people, cities, industry categories, and news articles with
 * vector embeddings). Point the NEO4J_* vars at your own database to swap it.
 *
 * Reads are always available. Writes are opt-in behind `NEO4J_BRIDGE=on`,
 * because the default target is a shared read-only instance and the only thing
 * this agent writes is bridge edges from memory to domain nodes — which only
 * makes sense in a database you own. See `./bridge`.
 */
import neo4j, { type Driver } from "neo4j-driver";

const URI = process.env.NEO4J_URI ?? "neo4j+s://demo.neo4jlabs.com:7687";
const USERNAME = process.env.NEO4J_USERNAME ?? "companies";
const PASSWORD = process.env.NEO4J_PASSWORD ?? "companies";
const DATABASE = process.env.NEO4J_DATABASE ?? "companies";

/**
 * True when the configured Neo4j is one you own and bridge writes are allowed.
 *
 * Deliberately an explicit opt-in rather than something inferred from the URI:
 * "can I write here" is an operator's statement, not a guess.
 */
export const GRAPH_WRITABLE = process.env.NEO4J_BRIDGE?.trim().toLowerCase() === "on";

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(URI, neo4j.auth.basic(USERNAME, PASSWORD), {
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
 * `READ` access mode is enforced here rather than trusted to the query text,
 * and Neo4j integers are narrowed to JS numbers so results survive eve's
 * durable JSON boundary.
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

/**
 * Run a write query. Refuses unless `NEO4J_BRIDGE=on`.
 *
 * `WRITE` routing is set here rather than trusted to the query text, the same
 * way `readQuery` pins `READ` — so a read helper can never be talked into a
 * write, and a write can never be issued against the demo instance by accident.
 */
export async function writeQuery<T = Record<string, unknown>>(
  cypher: string,
  params: Record<string, unknown> = {},
): Promise<T[]> {
  if (!GRAPH_WRITABLE) {
    throw new Error(
      "Refusing to write: set NEO4J_BRIDGE=on and point NEO4J_URI at a database you own. " +
        "The default demo instance is shared and read-only.",
    );
  }
  const { records } = await getDriver().executeQuery(cypher, params, {
    database: DATABASE,
    routing: "WRITE",
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
