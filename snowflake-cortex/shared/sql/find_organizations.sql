${query_neo4j}(
    'MATCH (o:Organization)
     WHERE toLower(o.name) CONTAINS toLower($name)
     RETURN o.id as organization_id,
            o.name as name,
            left(o.summary, 120) as summary,
            count{(o)--()} as relationships
     ORDER BY relationships DESC
     LIMIT 10',
    {'name': NAME}
)
