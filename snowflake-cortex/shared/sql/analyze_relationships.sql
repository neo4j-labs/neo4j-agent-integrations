${query_neo4j}(
    CONCAT('MATCH path = (o1:Organization {id: $organization_id})-[]-{1,', MAX_DEPTH, '}(o2:Organization)
    WHERE o1 <> o2
    RETURN DISTINCT o2.id as organization_id,
           o2.name as organization,
           [r in relationships(path) | type(r)] as relationships,
           length(path) as distance
    ORDER BY distance
    LIMIT $limit'),
    {'organization_id': ORGANIZATION_ID, 'limit': LIMIT}
)
