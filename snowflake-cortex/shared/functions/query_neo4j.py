from neo4j import GraphDatabase, RoutingControl
import math
import re
import socket
import _snowflake

# Snowflake reuses the UDF's process across calls, so all calls share one driver.
# The connection closes when the process ends.
_driver = None

# EXPLAIN reports these calls as reads, but they reach beyond the graph:
# files, URLs, dynamic Cypher and DBMS internals.
DENIED = re.compile(
    r"\bLOAD\s+CSV\b|\bapoc\.(load|import|export|cypher|periodic|trigger|systemdb)\b|\bdbms\.",
    re.IGNORECASE,
)


def get_driver():
    global _driver
    if _driver is None:
        credentials = _snowflake.get_username_password('cred')
        _driver = GraphDatabase.driver(
            "neo4j+s://demo.neo4jlabs.com:7687",
            auth=(credentials.username, credentials.password)
        )
    return _driver


def execute(cypher, params):
    # In READ access mode, the server rejects any write.
    return get_driver().execute_query(
        cypher,
        parameters_=params,
        database_="companies",
        routing_=RoutingControl.READ
    )


def query_neo4j(cypher, params):
    from neo4j.time import DateTime, Date, Time, Duration

    def serialize_neo4j(obj):
        if isinstance(obj, (DateTime, Date, Time, Duration)):
            return obj.iso_format()
        if isinstance(obj, float) and math.isnan(obj):
            return None  # NaN is not valid JSON. Some Article.sentiment values are NaN.
        if isinstance(obj, list):
            return [serialize_neo4j(i) for i in obj]
        if isinstance(obj, dict):
            return {k: serialize_neo4j(v) for k, v in obj.items()}
        return obj

    # Errors are returned, not raised, so the agent can read them and fix its query.
    if DENIED.search(cypher):
        return {"error": "Rejected: LOAD CSV, dbms.* and apoc.load/import/export/cypher/periodic/trigger/systemdb are not allowed."}
    try:
        _, plan, _ = execute("EXPLAIN " + cypher, params)
        if plan.query_type != "r":
            return {"error": f"Rejected: only read-only queries are allowed, this one is of type '{plan.query_type}'."}
        records, summary, keys = execute(cypher, params)
        return [serialize_neo4j(record.data()) for record in records] if records else []
    except (socket.gaierror, ValueError) as e:
        return {"error": f"Could not resolve Neo4j address: {str(e)}"}
    except Exception as e:
        return {"error": f"Neo4j query failed: {str(e)}"}
