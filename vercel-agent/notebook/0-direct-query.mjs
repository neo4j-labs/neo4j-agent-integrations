/**
 * 0-direct-query.mjs — Direct Neo4j Query (no AI)
 *
 * Verifies connectivity and explores the schema of the companies knowledge graph.
 * A useful sanity check before running the AI agents.
 *
 * Run:
 *   node 0-direct-query.mjs
 */

import dotenv from 'dotenv';
dotenv.config();

import neo4j from 'neo4j-driver';

const driver = neo4j.driver(
  process.env.NEO4J_URI,
  neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD),
  { disableLosslessIntegers: true }
);
const db = process.env.NEO4J_DATABASE;

// ── Top 10 most-mentioned organizations ───────────────────────────────────────
const { records } = await driver.executeQuery(
  `MATCH (a:Article)-[:MENTIONS]->(o:Organization)
   RETURN o.name AS company, COUNT(a) AS articles
   ORDER BY articles DESC LIMIT 10`,
  {},
  { database: db }
);

console.log('Top 10 Organizations by News Coverage:\n');
console.log('Company'.padEnd(45) + 'Articles');
console.log('-'.repeat(55));
records.forEach(r => {
  const name     = (r.get('company') ?? 'N/A').toString().slice(0, 43).padEnd(45);
  const articles = r.get('articles').toString();
  console.log(`${name}${articles}`);
});

// ── Schema exploration ────────────────────────────────────────────────────────
const { records: labelRecs } = await driver.executeQuery(
  'CALL db.labels()', {}, { database: db }
);
console.log('\nNode labels:', labelRecs.map(r => r.get('label')).join(', '));

const { records: sample } = await driver.executeQuery(
  'MATCH (o:Organization) RETURN o LIMIT 1', {}, { database: db }
);
if (sample.length) {
  const node = sample[0].get('o');
  const props = Object.keys(node.properties).join(', ');
  console.log('Organization properties:', props);
  console.log('Example:', node.properties.name, '|', (node.properties.summary ?? '').slice(0, 80));
}

await driver.close();
