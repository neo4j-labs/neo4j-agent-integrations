from neo4j import GraphDatabase
import socket
import _snowflake

# Snowflake reuses the UDF's process across calls, so one driver (and pool) serves them all.
# No teardown hook exists; the connection closes with the process.
_driver = None

def get_driver():
    global _driver
    if _driver is None:
        credentials = _snowflake.get_username_password('cred')
        _driver = GraphDatabase.driver(
            "neo4j+s://demo.neo4jlabs.com:7687",
            auth=(credentials.username, credentials.password)
        )
    return _driver

def query_neo4j(cypher, params):
    from neo4j.time import DateTime, Date, Time, Duration

    def serialize_neo4j(obj):
        if isinstance(obj, (DateTime, Date, Time, Duration)):
            return obj.iso_format()
        if isinstance(obj, list):
            return [serialize_neo4j(i) for i in obj]
        if isinstance(obj, dict):
            return {k: serialize_neo4j(v) for k, v in obj.items()}
        return obj

    try:
        records, summary, keys = get_driver().execute_query(
            cypher,
            parameters_=params,
            database_="companies"
        )
        return [serialize_neo4j(record.data()) for record in records] if records else []
    except (socket.gaierror, ValueError) as e:
        return {"error": f"Could not resolve Neo4j address: {str(e)}"}
    except Exception as e:
        return {"error": f"Neo4j query failed: {str(e)}"}
