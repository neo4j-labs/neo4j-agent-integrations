"""Phase 3 checks for the connected group step.

The live checks need ``make rebuild`` to have written ``ConnectedGroup`` nodes,
and are skipped until then.
"""

from collections.abc import Iterator
from typing import Any

import neo4j
import pytest

from graphrag_banking.build_groups import (
    _PROJECTION_ROWS,
    EXCLUDED_ADDRESS_KINDS,
    _groups,
)
from graphrag_banking.config import Settings, get_driver, load_settings

RING = [
    "Ortega Builders",
    "Keystone Paving",
    "Summit Ridge Supply",
    "Lakeview Interiors",
    "Crestline Holdings",
    "Victor Hale",
]

FAMILY = ["P-5001", "P-5002", "B-5001", "B-5002", "B-5003"]

_GROUP_OF = """
MATCH (n {name: $name})-[:IN_GROUP]->(g:ConnectedGroup)
WHERE n:Customer OR n:Person OR n:Business
RETURN g.group_id AS group_id
"""


def _row(
    element_id: str, key: str | None, value: float, member: bool = True
) -> dict[str, Any]:
    return {"element_id": element_id, "key": key, "member": member, "value": value}


def test_groups_drop_single_members_and_number_largest_first() -> None:
    components = [
        _row("a", "P-1", 7),
        _row("b", "B-9", 3),
        _row("c", "B-8", 3),
        _row("d", "B-7", 3),
        _row("e", "B-1", 7),
        _row("f", "B-5", 5),
        _row("phone", None, 3, member=False),
        _row("device", None, 7, member=False),
    ]
    scores = [_row(element_id, "", 1.0) for element_id in "abcdef"]
    groups = _groups(components, scores)
    assert [group["group_id"] for group in groups] == ["CG-0001", "CG-0002"]
    assert [len(group["members"]) for group in groups] == [3, 2]
    assert {m["element_id"] for m in groups[1]["members"]} == {"a", "e"}


def test_groups_drop_components_without_a_shared_identifier() -> None:
    # An owner and their two businesses, linked only by ownership.
    components = [
        _row("owner", "P-1", 4),
        _row("first", "B-1", 4),
        _row("second", "B-2", 4),
    ]
    scores = [_row(element_id, "", 1.0) for element_id in ["owner", "first", "second"]]
    assert _groups(components, scores) == []


@pytest.fixture(scope="module")
def settings() -> Settings:
    settings = load_settings()
    if not settings.neo4j_uri:
        pytest.skip("NEO4J_URI is not set")
    return settings


@pytest.fixture(scope="module")
def driver(settings: Settings) -> Iterator[neo4j.Driver]:
    with get_driver(settings) as driver:
        records, _, _ = driver.execute_query(
            "MATCH (g:ConnectedGroup) RETURN count(g) AS n",
            database_=settings.neo4j_database,
        )
        if records[0]["n"] == 0:
            pytest.skip("No connected groups. Run make rebuild.")
        yield driver


@pytest.fixture(scope="module")
def query(driver: neo4j.Driver, settings: Settings):
    def run(cypher: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = driver.execute_query(
            cypher, database_=settings.neo4j_database, **params
        )
        return [record.data() for record in records]

    return run


def _projection_rows(settings: Settings, tail: str) -> list[dict[str, Any]]:
    """Run the projection's row query, which needs no GDS session."""
    with get_driver(settings) as driver:
        records, _, _ = driver.execute_query(
            _PROJECTION_ROWS + tail,
            excluded_kinds=EXCLUDED_ADDRESS_KINDS,
            database_=settings.neo4j_database,
        )
    return [record.data() for record in records]


def test_projection_has_one_edge_per_pair(settings: Settings) -> None:
    rows = _projection_rows(
        settings,
        """
        WITH source, target, count(*) AS edges
        WHERE edges > 1
        RETURN count(*) AS pairs
        """,
    )
    assert rows[0]["pairs"] == 0


def test_projection_keeps_only_shared_identifiers(settings: Settings) -> None:
    rows = _projection_rows(
        settings,
        """
        WITH target, count(DISTINCT source) AS members
        WHERE (target:Phone OR target:Email OR target:Address OR target:Device)
          AND (members < 2 OR target.kind IN $excluded_kinds)
        RETURN count(*) AS bad
        """,
    )
    assert rows[0]["bad"] == 0


def _group_of(query, name: str) -> str:
    rows = query(_GROUP_OF, name=name)
    assert len(rows) == 1, f"{name} should be in exactly one group"
    return rows[0]["group_id"]


def test_ring_shares_one_group(query) -> None:
    assert len({_group_of(query, name) for name in RING}) == 1


def test_hale_has_top_centrality_in_ring(query) -> None:
    rows = query(
        """
        MATCH (:Person {name: 'Victor Hale'})-[:IN_GROUP]->(g:ConnectedGroup)
        MATCH (n)-[r:IN_GROUP]->(g)
        RETURN n.name AS name, r.centrality AS centrality
        ORDER BY centrality DESC
        """
    )
    assert rows[0]["name"] == "Victor Hale"
    assert rows[0]["centrality"] > rows[1]["centrality"]


def test_registered_agent_address_does_not_join_groups(query) -> None:
    rows = query(
        """
        UNWIND ['Brightline Dental', 'Harbor Physical Therapy'] AS name
        MATCH (b:Business {name: name})
        OPTIONAL MATCH (b)-[:IN_GROUP]->(g:ConnectedGroup)
        RETURN name, g.group_id AS group_id
        """
    )
    assert len(rows) == 2
    groups = [row["group_id"] for row in rows]
    assert None in groups or groups[0] != groups[1]


@pytest.fixture(scope="module")
def family_group(query) -> str:
    rows = query(
        """
        UNWIND $keys AS key
        MATCH (n)-[:IN_GROUP]->(g:ConnectedGroup)
        WHERE n.person_id = key OR n.business_id = key
        RETURN DISTINCT g.group_id AS group_id
        """,
        keys=FAMILY,
    )
    assert len(rows) == 1, "The family members should share exactly one group"
    return rows[0]["group_id"]


def test_family_group_has_every_member(query, family_group: str) -> None:
    rows = query(
        """
        MATCH (n)-[:IN_GROUP]->(:ConnectedGroup {group_id: $group_id})
        WHERE n.person_id IN $keys OR n.business_id IN $keys
        RETURN count(n) AS n
        """,
        group_id=family_group,
        keys=FAMILY,
    )
    assert rows[0]["n"] == len(FAMILY)


def test_family_group_has_no_past_losses(query, family_group: str) -> None:
    rows = query(
        """
        MATCH (n)-[:IN_GROUP]->(:ConnectedGroup {group_id: $group_id})
        MATCH (n)-[:BORROWER_ON]->(loan:Loan {status: 'WRITTEN_OFF'})
        RETURN loan.loan_id AS loan_id
        """,
        group_id=family_group,
    )
    assert rows == []


def test_family_group_has_no_money_loops(query, family_group: str) -> None:
    rows = query(
        """
        MATCH (:ConnectedGroup {group_id: $group_id})<-[:IN_GROUP]-(:Business)
              -[:HOLDS]->(a:Account)
        MATCH (a)(()-[:HAS_TRANSACTION]->(:Transaction)-[:TO_ACCOUNT]->()){1,6}(a)
        RETURN DISTINCT a.account_id AS account_id
        """,
        group_id=family_group,
    )
    assert rows == []


def test_every_group_has_a_shared_identifier(query) -> None:
    rows = query(
        """
        MATCH (g:ConnectedGroup)
        OPTIONAL CALL (g) {
            MATCH (m)-[:IN_GROUP]->(g)
            MATCH (m)-[:HAS_PHONE|HAS_EMAIL]->(x)
            RETURN x, m
            UNION
            MATCH (m)-[:IN_GROUP]->(g)
            MATCH (m)-[:HAS_ADDRESS]->(x:Address)
            WHERE NOT x.kind IN $excluded_kinds
            RETURN x, m
            UNION
            MATCH (m:Business)-[:IN_GROUP]->(g)
            MATCH (m)-[:APPLIED_FOR]->(:LoanApplication)-[:SUBMITTED_FROM]->(x)
            RETURN x, m
        }
        WITH g, x, count(DISTINCT m) AS sharers
        WITH g, max(sharers) AS most_sharers
        WHERE most_sharers < 2
        RETURN g.group_id AS group_id
        """,
        excluded_kinds=EXCLUDED_ADDRESS_KINDS,
    )
    assert rows == []


def test_group_sizes_match_members(query) -> None:
    rows = query(
        """
        MATCH (g:ConnectedGroup)
        OPTIONAL MATCH (n)-[:IN_GROUP]->(g)
        WITH g, count(n) AS members
        WHERE members <> g.size OR members < 2
        RETURN g.group_id AS group_id
        """
    )
    assert rows == []
