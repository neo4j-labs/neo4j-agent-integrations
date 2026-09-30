${query_neo4j}(
    'MATCH (o:Organization {id: $organization_id})
     RETURN o.id as organization_id,
            o.name as name,
            [(o)-[:HAS_INVESTOR]->(i) | i {.id, .name, type: labels(i)[0]}] as investors',
    {'organization_id': ORGANIZATION_ID}
)
