${query_neo4j}('
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)-[:HAS_CHUNK]->(c:Chunk)
    WHERE c.embedding_sbert IS NOT NULL
    WITH DISTINCT a, c, vector.similarity.cosine(c.embedding_sbert, $embedding) AS score
    RETURN a.title as title,
           a.date as date,
           c.text as text,
           score
    ORDER BY score DESC
    LIMIT $limit',
    {
      'company': COMPANY,
      'limit': LIMIT,
      'embedding': ${generate_embeddings}(QUERY)
    })
