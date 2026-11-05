// `npm run ontology`: activates the Industry Research ontology on the NAMS workspace.
import {
  MemoryClient,
  NotSupportedError,
  type OntologyDocument,
  type OntologySummary,
} from "@neo4j-labs/agent-memory";
import { join } from "node:path";

try {
  process.loadEnvFile(join(import.meta.dirname, "..", ".env"));
} catch {
  // No .env: use the ambient environment, as npm run chat does.
}

const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
// strict: extraction produces only the types declared below.
const validationMode = args.has("--permissive") ? "permissive" : "strict";

const DOMAIN_ID = "industry-research";
/** The system ontology a workspace starts with. */
const DEFAULT_ID = "nams-default";

/** The research domain's nouns (entity types) and verbs (relationships). */
const ONTOLOGY: OntologyDocument = {
  domain: {
    id: DOMAIN_ID,
    name: "Industry Research",
    description: "Companies, the people who run and fund them, their funding rounds, and the sectors analysts cover.",
  },
  entityTypes: [
    { label: "Company", poleType: "ORGANIZATION", properties: [] },
    { label: "Person", poleType: "PERSON", properties: [] },
    { label: "FundingRound", poleType: "EVENT", properties: [] },
    { label: "Sector", poleType: "OBJECT", properties: [] },
  ],
  relationships: [
    { type: "INVESTED_IN", source: "Company", target: "Company" },
    { type: "INVESTED_IN", source: "Person", target: "Company" },
    { type: "CEO_OF", source: "Person", target: "Company" },
    { type: "RAISED", source: "Company", target: "FundingRound" },
    { type: "OPERATES_IN", source: "Company", target: "Sector" },
    // The analyst using the agent: "I cover the graph database sector, and I track Neo4j."
    { type: "COVERS", source: "Person", target: "Sector" },
    { type: "TRACKS", source: "Person", target: "Company" },
  ],
};

const apiKey = process.env.NAMS_API_KEY?.trim();
if (!apiKey) {
  console.error("No NAMS_API_KEY. Copy .env.example to .env and fill it in.");
  process.exit(1);
}

const client = new MemoryClient({
  apiKey,
  endpoint: process.env.NAMS_ENDPOINT?.trim() || "https://memory.neo4jlabs.com/v1",
  workspaceId: process.env.WORKSPACE_ID?.trim() || undefined,
});

/** One line naming the workspace's active ontology, or saying there is none. */
async function describeActive(): Promise<string> {
  try {
    const active = await client.ontology.getActive();
    const { entityTypes, relationships, domain } = active.document;
    return (
      `${domain.name} (${domain.id}) revision ${active.revision ?? "?"}, ${active.validationMode ?? "?"}: ` +
      `${entityTypes.map((t) => t.label).join(", ")} | ${[...new Set(relationships.map((r) => r.type))].join(", ")}`
    );
  } catch (err) {
    if (err instanceof NotSupportedError) return "none (generic POLE+O extraction)";
    throw err;
  }
}

console.log(`Active ontology now: ${await describeActive()}`);

const summaries = await client.ontology.list();

if (args.has("--restore-default")) {
  const summary = summaries.find((s: OntologySummary) => s.name === DEFAULT_ID);
  if (!summary) throw new Error(`No ${DEFAULT_ID} ontology in this workspace's list.`);
  const { versions } = await client.ontology.get(summary.id);
  const latest = versions.reduce((a, b) => (b.revision > a.revision ? b : a));
  if (dryRun) {
    console.log(`\nWould activate ${DEFAULT_ID} revision ${latest.revision}. Dry run: nothing was written.`);
    process.exit(0);
  }
  await client.ontology.activate(latest.id);
  console.log(`Active ontology now: ${await describeActive()}`);
  process.exit(0);
}

const existing = summaries.find((s: OntologySummary) => !s.isSystem && s.name === DOMAIN_ID);

if (dryRun) {
  console.log(`\nWould ${existing ? `add a revision to ${existing.id}` : "create"} ${DOMAIN_ID} (${validationMode}) and activate it:`);
  console.log(JSON.stringify(ONTOLOGY, null, 2));
  console.log("\nDry run: nothing was written.");
  process.exit(0);
}

const version = existing
  ? await client.ontology.update({ id: existing.id, schema: ONTOLOGY, validationMode })
  : await client.ontology.create({ name: ONTOLOGY.domain.name, schema: ONTOLOGY, validationMode });
console.log(`\n${existing ? "Revised" : "Created"} ${DOMAIN_ID}: revision ${version.revision} (${version.validationMode})`);

await client.ontology.activate(version.id);
console.log(`Active ontology now: ${await describeActive()}`);
console.log("\nNew conversations are extracted with these types. Earlier entities keep theirs.");
