import json
import logging
import os
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("custom_investments_skill")

def get_investments(company: str) -> str:
    """
    Returns the investments made by a specific company or organization by its name.
    Use this specialized tool when a user explicitly asks about investment portfolios.

    Args:
        company: The exact string name of the company/organization to look up.

    Returns:
        A JSON string listing the target investment IDs, names, and entity types.
    """
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    pwd = os.environ.get("NEO4J_PASSWORD")
    db = os.environ.get("NEO4J_DATABASE", "neo4j")

    if not all([uri, user, pwd]):
        logger.error("Missing database environment variables in sandbox configuration.")
        return "Error: Database connection credentials are not properly configured in the runtime sandbox."

    query = """
    MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
    WHERE o.name = $company
    RETURN i.id as id, i.name as name, head(labels(i)) as type
    """

    try:
        logger.info(f"Executing investment lookup for target company: {company}")
        with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
            records, _, _ = driver.execute_query(query, company=company, database_=db)
            if not records:
                return f"No investments found in the graph database for company: {company}"

            results = [record.data() for record in records]
            return json.dumps(results, indent=2)

    except Exception as e:
        logger.error(f"Skill execution failed for company '{company}': {str(e)}")
        return f"Error executing custom investment tool: {str(e)}"