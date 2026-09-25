${query_neo4j}('
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
    MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
    CALL db.index.vector.queryNodes(''news_sbert'', $limit, $embedding)
    YIELD node, score
    WHERE node = c
    RETURN a.title as title,
           a.date as date,
           c.text as text,
           score
    ORDER BY score DESC',
    {
      'company': COMPANY,
      'limit': LIMIT,
      'embedding': ${generate_embeddings}(QUERY)
    })
