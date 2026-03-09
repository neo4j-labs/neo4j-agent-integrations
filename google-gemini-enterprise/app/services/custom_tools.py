"""Custom tools for the ADK Agent."""
import json
import logging
from neo4j import GraphDatabase
from google.adk.tools.function_tool import FunctionTool

def create_investment_tool(user: str, pwd: str, uri: str, db: str) -> FunctionTool:
    """
    Creates a FunctionTool to get investments for a company.
    A closure is used to securely pass database credentials.
    """
    async def get_investments(company: str) -> str:
        """
        Returns the investments by a company by name.
        Returns a list of investment ids, names, and types.
        """
        query = """
        MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
        WHERE o.name = $company
        RETURN i.id as id, i.name as name, head(labels(i)) as type
        """
        try:
            # Establish a short-lived connection for this tool call
            with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
                records, _, _ = driver.execute_query(query, company=company, database_=db)
                return json.dumps([record.data() for record in records], indent=2)
        except Exception as e:
            logging.error(f"Error executing custom investment tool for company '{company}': {e}")
            return f"Error fetching investments: {str(e)}"

    return FunctionTool(get_investments)
