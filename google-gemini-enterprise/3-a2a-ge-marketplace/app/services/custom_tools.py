import json
import logging
from neo4j import GraphDatabase
from google.adk.tools.function_tool import FunctionTool

def create_schema_tool(user: str, pwd: str, uri: str, db: str): # -> FunctionTool if you have the import
    """Creates a tool for the agent to discover the graph's structure."""

    async def get_schema() -> str:
        """
        Retrieves the schema of the Neo4j database. 
        Always use this first to understand the available nodes, labels, and relationships.
        """
        query = """
        CALL apoc.meta.schema({sample: 100})
        YIELD value
        UNWIND keys(value) as key
        WITH key, value[key] as value
        RETURN key, value { .properties, .type, .relationships } as value
        """
        try:
            with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
                records, _, _ = driver.execute_query(query, database_=db)
                if not records:
                    return "The get-schema tool executed successfully; however, since the Neo4j instance contains no data, no schema information was returned."

                structured_output = []
                for record in records:
                    key = record["key"]
                    val = record["value"]

                    cleaned_properties = {}
                    if "properties" in val and val["properties"]:
                        for prop_key, prop_data in val["properties"].items():
                            cleaned_properties[prop_key] = prop_data.get("type", "UNKNOWN")

                    cleaned_rels = {}
                    if "relationships" in val and val["relationships"]:
                        for rel_type, rel_data in val["relationships"].items():
                            cleaned_rels[rel_type] = {
                                "direction": rel_data.get("direction", "out"),
                                "labels": rel_data.get("labels", [])
                            }

                    structured_output.append({
                        "key": key,
                        "value": {
                            "type": val.get("type", "node"),
                            "properties": cleaned_properties,
                            "relationships": cleaned_rels
                        }
                    })
                return json.dumps(structured_output, indent=2)
        except Exception as e:
            logging.error(f"Error fetching schema from {uri}: {e}")
            return f"Error fetching schema: {str(e)}"

    return FunctionTool(get_schema)

def create_cypher_tool(user: str, pwd: str, uri: str, db: str) -> FunctionTool:
    """Creates a tool for the agent to execute raw Cypher queries."""

    async def execute_cypher(cypher_query: str) -> str:
        """
        Executes a Cypher query against the Neo4j database and returns the results.
        If the query fails, an error message will be returned so you can fix your syntax.
        """
        try:
            with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
                records, _, _ = driver.execute_query(cypher_query, database_=db)
                if not records:
                    return "Query executed successfully, but returned no results."

                results = [record.data() for record in records]
                if len(results) > 50:
                    return json.dumps(results[:50], indent=2) + "\n... (results truncated. Please refine your query to be more specific)."

                return json.dumps(results, indent=2)

        except Exception as e:
            logging.error(f"Cypher execution error on {uri}. Query: {cypher_query} | Error: {e}")
            return f"Cypher Error: {str(e)}. Please analyze the error and rewrite your query."

    return FunctionTool(execute_cypher)



def create_investment_tool(user: str, pwd: str, uri: str, db: str) -> FunctionTool:
    """Creates a specialized FunctionTool to get investments for a company."""

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
            with GraphDatabase.driver(uri, auth=(user, pwd)) as driver:
                records, _, _ = driver.execute_query(query, company=company, database_=db)
                if not records:
                    return f"No investments found for company: {company}"
                return json.dumps([record.data() for record in records], indent=2)
        except Exception as e:
            logging.error(f"Error executing custom investment tool for company '{company}': {e}")
            return f"Error fetching investments: {str(e)}"

    return FunctionTool(get_investments)



def get_tenant_tools(user: str, pwd: str, uri: str, db: str) -> list[FunctionTool]:
    """
    Master factory function. 
    Returns the complete suite of dynamically configured tools for a specific tenant.
    """
    return [
        create_schema_tool(user, pwd, uri, db),
        create_cypher_tool(user, pwd, uri, db),
        create_investment_tool(user, pwd, uri, db)
    ]