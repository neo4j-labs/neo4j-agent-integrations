${query_neo4j}(
    'MATCH (o:Organization {name: $company})
    RETURN o.name as name,
    [(o)-[:HAS_INVESTOR]->(p:Person) | p.name] as investor
    LIMIT 1',
    {'company': COMPANY}
)
