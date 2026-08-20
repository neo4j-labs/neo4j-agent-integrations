import assert from 'node:assert/strict';
import test from 'node:test';
import { createNeo4jMcpDefinition } from '../src/connections/neo4j-mcp.ts';

test('uses the local endpoint and read-only tool allowlist by default', () => {
  const definition = createNeo4jMcpDefinition({});

  assert.equal(definition.url, 'http://localhost:8000/mcp');
  assert.deepEqual(definition.tools, ['get-schema', 'read-cypher']);
  assert.equal(definition.auth, undefined);
  assert.deepEqual(definition.headers, {
    Authorization: `Basic ${Buffer.from('companies:companies').toString('base64')}`,
  });
});

test('uses the configured Neo4j endpoint and credentials', () => {
  const definition = createNeo4jMcpDefinition({
    NEO4J_MCP_URL: 'https://mcp.example.com/mcp',
    NEO4J_USERNAME: 'neo4j',
    NEO4J_PASSWORD: 'password',
  });

  assert.equal(definition.url, 'https://mcp.example.com/mcp');
  assert.deepEqual(definition.headers, {
    Authorization: `Basic ${Buffer.from('neo4j:password').toString('base64')}`,
  });
});
