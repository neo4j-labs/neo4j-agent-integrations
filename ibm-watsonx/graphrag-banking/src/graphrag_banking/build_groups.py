"""Find connected groups with Aura Graph Analytics and write them to the graph.

Projects customers, people, and businesses together with the phones, emails,
devices, and addresses they share, plus ownership and director links. An
identifier that only one member uses links nothing, so it is left out. Leaving
it in would add paths through its one member and skew centrality. Registered
agent and coworking addresses are left out, because ``FRAUD-REG-AGENT`` says
they are not red flags on their own. Weakly connected components form the
groups. Betweenness centrality scores each member.

A component becomes a group only when it holds a shared identifier. An owner
and the businesses they own or direct are normal, so a component linked only by
ownership and director links is dropped.

Writes one ``ConnectedGroup`` per group, and an ``IN_GROUP {centrality}`` link
per member (proposal "Connected groups"). Each
run deletes the old groups first, so it can run again without ``reset-db``.

The projection creates an Aura Graph Analytics session, which is billed while
it exists. Dropping the graph when the step ends deletes the session.

Run after ``load-structured``.
"""

import logging
from collections import defaultdict
from typing import Any

import neo4j

from graphrag_banking.config import Settings, get_driver, load_settings

logger = logging.getLogger(__name__)

SESSION_MEMORY = "2GB"
GRAPH_NAME = "connected-groups"
METHOD = "wcc"
EXCLUDED_ADDRESS_KINDS = ["REGISTERED_AGENT", "COWORKING"]

_CREATE_CONSTRAINT = """
CREATE CONSTRAINT connected_group_id IF NOT EXISTS
FOR (g:ConnectedGroup) REQUIRE g.group_id IS UNIQUE
"""

_DELETE_GROUPS = "MATCH (g:ConnectedGroup) DETACH DELETE g"

# Dropping the graph deletes its session. A graph left behind by a failed run
# is dropped before projecting again.
_DROP_GRAPH = "CALL gds.graph.drop($graph, false) YIELD graphName RETURN graphName"

# Shared devices sit on loan applications, so a business links to the device
# its applications were submitted from. UNION keeps one row per (source,
# target) pair, so a person who both owns and directs a business adds one edge.
# The projection creates the session. An idle session expires after ten
# minutes if the drop at the end never runs.
_PROJECTION_ROWS = """
MATCH (source)
WHERE source:Customer OR source:Person OR source:Business
CALL (source) {
    MATCH (source)-[:OWNS|DIRECTOR_OF]->(target)
    RETURN target
    UNION
    MATCH (source)-[:HAS_PHONE|HAS_EMAIL]->(target)
    WHERE COUNT {
        MATCH (member)-[:HAS_PHONE|HAS_EMAIL]->(target)
        WHERE member:Customer OR member:Person OR member:Business
        RETURN DISTINCT member
    } >= 2
    RETURN target
    UNION
    MATCH (source)-[:HAS_ADDRESS]->(target:Address)
    WHERE NOT target.kind IN $excluded_kinds
      AND COUNT {
        MATCH (member)-[:HAS_ADDRESS]->(target)
        WHERE member:Customer OR member:Person OR member:Business
        RETURN DISTINCT member
    } >= 2
    RETURN target
    UNION
    MATCH (source)-[:APPLIED_FOR]->(:LoanApplication)
          -[:SUBMITTED_FROM]->(target:Device)
    WHERE COUNT {
        MATCH (member:Business)-[:APPLIED_FOR]->(:LoanApplication)
              -[:SUBMITTED_FROM]->(target)
        RETURN DISTINCT member
    } >= 2
    RETURN target
}
"""

_PROJECT = (
    _PROJECTION_ROWS
    + """
WITH gds.graph.project(
    $graph,
    source,
    target,
    {},
    {
        memory: $memory,
        ttl: duration({minutes: 10}),
        undirectedRelationshipTypes: ['*']
    }
) AS graph
RETURN graph.nodeCount AS nodes, graph.relationshipCount AS relationships
"""
)

# Phones, emails, devices, and addresses are in the projection but are not
# group members. They are returned with member false, so a component can be
# checked for a shared identifier.
_STREAM_NODES = """
CALL gds.{algorithm}.stream($graph)
YIELD nodeId, {column}
MATCH (n)
WHERE id(n) = nodeId
RETURN elementId(n) AS element_id,
       coalesce(n.customer_id, n.person_id, n.business_id) AS key,
       n:Customer OR n:Person OR n:Business AS member,
       {column} AS value
"""

_WRITE_GROUPS = """
UNWIND $groups AS group
CREATE (g:ConnectedGroup {
    group_id: group.group_id, size: size(group.members), method: $method
})
WITH g, group
UNWIND group.members AS member
MATCH (n) WHERE elementId(n) = member.element_id
CREATE (n)-[:IN_GROUP {centrality: member.centrality}]->(g)
"""


def _stream(
    driver: neo4j.Driver, database: str, algorithm: str, column: str
) -> list[dict[str, Any]]:
    cypher = _STREAM_NODES.replace("{algorithm}", algorithm).replace("{column}", column)
    records, _, _ = driver.execute_query(cypher, graph=GRAPH_NAME, database_=database)
    return [record.data() for record in records]


def _groups(
    components: list[dict[str, Any]], scores: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return groups that hold a shared identifier, largest first.

    Every identifier in the projection is shared by two or more members, so a
    component with one has at least two members. Group IDs follow that order,
    with ties broken by the smallest member key, so the same data gives the
    same IDs on every run.
    """
    centrality = {row["element_id"]: row["value"] for row in scores}
    with_identifier = {row["value"] for row in components if not row["member"]}
    members_by_component: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in components:
        if not row["member"]:
            continue
        members_by_component[row["value"]].append(
            {
                "element_id": row["element_id"],
                "key": row["key"],
                "centrality": centrality[row["element_id"]],
            }
        )
    groups = [
        members
        for component, members in members_by_component.items()
        if component in with_identifier and len(members) > 1
    ]
    groups.sort(key=lambda members: (-len(members), min(m["key"] for m in members)))
    return [
        {
            "group_id": f"CG-{index:04d}",
            "members": [
                {"element_id": m["element_id"], "centrality": m["centrality"]}
                for m in members
            ],
        }
        for index, members in enumerate(groups, start=1)
    ]


def _compute_groups(driver: neo4j.Driver, database: str) -> list[dict[str, Any]]:
    driver.execute_query(_DROP_GRAPH, graph=GRAPH_NAME, database_=database)
    try:
        records, _, _ = driver.execute_query(
            _PROJECT,
            graph=GRAPH_NAME,
            memory=SESSION_MEMORY,
            excluded_kinds=EXCLUDED_ADDRESS_KINDS,
            database_=database,
        )
        nodes = records[0]["nodes"] if records else None
        if not nodes:
            logger.info("No shared links to project, so there are no groups")
            return []
        logger.info(
            "Projected %d nodes and %d relationships",
            nodes,
            records[0]["relationships"],
        )
        components = _stream(driver, database, "wcc", "componentId")
        scores = _stream(driver, database, "betweenness", "score")
    finally:
        driver.execute_query(_DROP_GRAPH, graph=GRAPH_NAME, database_=database)
        logger.info("Dropped graph %s and its GDS session", GRAPH_NAME)
    return _groups(components, scores)


def build_groups(settings: Settings) -> None:
    """Replace the connected groups with freshly computed ones."""
    database = settings.neo4j_database
    with get_driver(settings) as driver:
        driver.execute_query(_CREATE_CONSTRAINT, database_=database)
        driver.execute_query(_DELETE_GROUPS, database_=database)
        groups = _compute_groups(driver, database)
        driver.execute_query(
            _WRITE_GROUPS, groups=groups, method=METHOD, database_=database
        )
        logger.info(
            "Wrote %d connected groups with %d members",
            len(groups),
            sum(len(group["members"]) for group in groups),
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    build_groups(load_settings())
