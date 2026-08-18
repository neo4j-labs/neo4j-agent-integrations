#!/usr/bin/env python3
"""Custom investment lookup skill — queries Neo4j directly from the sandbox.

Neo4j connection values are rendered by deploy_platform.sh from your .env
(the sandbox has no runtime env injection).
"""
import json
from neo4j import GraphDatabase

NEO4J_URI = "__NEO4J_URI__"
NEO4J_USER = "__NEO4J_USER__"
NEO4J_PASSWORD = "__NEO4J_PASSWORD__"
NEO4J_DATABASE = "__NEO4J_DATABASE__"

QUERY = """
MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
WHERE o.name = $company
RETURN i.id AS id, i.name AS name, head(labels(i)) AS type
"""



def get_investments(company: str) -> str:
    """Return investments/investors linked to a company by exact name."""
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        records, _, _ = driver.execute_query(QUERY, company=company, database_=NEO4J_DATABASE)
    if not records:
        return f"No investments found for company: {company}"
    return json.dumps([r.data() for r in records], indent=2)



if __name__ == "__main__":
    import sys
    print(get_investments(sys.argv[1] if len(sys.argv) > 1 else ""))