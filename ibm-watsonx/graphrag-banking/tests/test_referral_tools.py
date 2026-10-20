"""Checks for the fraud referral tools.

The unit tests need no database. The live test needs the fraud data and the
``ConnectedGroup`` nodes, and skips until ``make rebuild`` has written them. It
deletes every ``FraudReferral`` when it finishes, pass or fail.
"""

import ast
import inspect
from collections.abc import Iterator
from datetime import date
from typing import Any

import neo4j
import pytest

from graphrag_banking import referral_tools, staff_tools
from graphrag_banking.config import Settings, get_driver, load_settings
from graphrag_banking.referral_tools import ReferralContext
from graphrag_banking.staff_tools import StaffContext

AS_OF = date(2026, 10, 8)
BANKER = "RM-07"
ORTEGA = "B-1002"
ORTEGA_APPLICATION = "APP-1001"
KEYSTONE_APPLICATION = "APP-1002"
ORTEGA_GROUP = "CG-0001"
RED_FLAGS = ["KYC-UBO-25", "FRAUD-PRIOR-LOSS", "FRAUD-SHARED-ID", "FRAUD-CIRCULAR-FLOW"]
SUMMARY = "Matches four red flags. Shared phone and device, circular flows."
TOOLS = [referral_tools.create_fraud_referral, referral_tools.resolve_fraud_referral]
REFERRAL_KEYS = {
    "referral_id",
    "status",
    "created_at",
    "summary",
    "application",
    "business",
    "group_id",
    "cites",
    "assigned_to",
    "submitted_by",
}


class _Record:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def data(self) -> dict[str, Any]:
        return self._data


class _FakeDriver:
    """Returns the rows keyed by query, so the error paths run offline."""

    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.rows = rows
        self.params: list[dict[str, Any]] = []

    def execute_query(self, query: str, **params: Any) -> tuple[Any, None, None]:
        self.params.append(params)
        return [_Record(row) for row in self.rows.get(query, [])], None, None


def _offline(rows: dict[str, list[dict[str, Any]]] | None = None) -> ReferralContext:
    return ReferralContext(_FakeDriver(rows or {}), "neo4j", BANKER, AS_OF)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("red_flags", "summary"),
    [
        ([], SUMMARY),
        (["FRAUD-MADE-UP"], SUMMARY),
        (["FRAUD-SHARED-ID", "AML-NO-TIPOFF"], SUMMARY),
        (RED_FLAGS, "  "),
    ],
)
def test_create_rejects_bad_arguments(red_flags: list[str], summary: str) -> None:
    context = _offline()
    with pytest.raises(ValueError):
        referral_tools.create_fraud_referral(
            context, ORTEGA_APPLICATION, red_flags, summary
        )
    assert context.executed == []


@pytest.mark.parametrize("status", ["OPEN", "accepted", ""])
def test_resolve_rejects_a_bad_status(status: str) -> None:
    context = _offline()
    with pytest.raises(ValueError):
        referral_tools.resolve_fraud_referral(context, "REF-0001", status)
    assert context.executed == []


def test_create_dedupes_red_flags() -> None:
    created = {"referral": {"referral_id": "REF-0001"}}
    context = _offline({referral_tools._CREATE_FRAUD_REFERRAL: [created]})
    result = referral_tools.create_fraud_referral(
        context, ORTEGA_APPLICATION, ["FRAUD-SHARED-ID", "FRAUD-SHARED-ID"], SUMMARY
    )
    assert result == {"referral_id": "REF-0001"}
    [seen] = context.driver.params  # type: ignore[attr-defined]
    assert seen["red_flags"] == ["FRAUD-SHARED-ID"]
    assert seen["banker_id"] == BANKER
    assert seen["routing_"] == neo4j.RoutingControl.WRITE


@pytest.mark.parametrize(
    ("why", "error"),
    [
        (
            {"in_my_book": False, "open_referral": None},
            f"No application {KEYSTONE_APPLICATION} from a client in your book.",
        ),
        (
            {"in_my_book": True, "open_referral": "REF-0003"},
            (
                f"Application {KEYSTONE_APPLICATION} already has an open referral, "
                "REF-0003."
            ),
        ),
        (
            {"in_my_book": True, "open_referral": None},
            "No fraud reviewer FR-02 in the graph.",
        ),
    ],
)
def test_create_explains_why_nothing_was_written(
    why: dict[str, Any], error: str
) -> None:
    context = _offline({referral_tools._WHY_NOT_CREATED: [why]})
    result = referral_tools.create_fraud_referral(
        context, KEYSTONE_APPLICATION, RED_FLAGS, SUMMARY
    )
    assert result == {"error": error}


def test_resolve_refuses_a_referral_that_is_not_open() -> None:
    result = referral_tools.resolve_fraud_referral(_offline(), "REF-0009", "CLOSED")
    assert result == {
        "error": "No open referral REF-0009. It does not exist or is already resolved."
    }


def test_create_query_checks_the_book_and_uses_the_lending_rule_names() -> None:
    query = referral_tools._CREATE_FRAUD_REFERRAL
    assert "(banker:Banker {banker_id: $banker_id})-[:MANAGES]->" in query
    assert "CREATE (referral:FraudReferral {" in query
    assert "CREATE (referral)-[:FOR_APPLICATION]->(app)" in query
    assert "(referral)-[:FOR_APPLICATION]->(app)" in staff_tools._CHECK_LENDING_RULES
    assert "referral:FraudReferral" in staff_tools._CHECK_LENDING_RULES


def test_tools_import_only_the_neo4j_driver_at_module_level() -> None:
    tree = ast.parse(inspect.getsource(referral_tools))
    modules = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules <= {
        "argparse",
        "logging",
        "dataclasses",
        "datetime",
        "typing",
        "neo4j",
    }


def test_every_tool_takes_the_context_first_and_has_a_description() -> None:
    for tool in TOOLS:
        parameters = list(inspect.signature(tool).parameters)
        assert parameters[0] == "context", tool.__name__
        assert tool.__doc__ and "—" not in tool.__doc__, tool.__name__


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
            "MATCH (g:ConnectedGroup)<-[:IN_GROUP]-(:Business {business_id: $id}) "
            "RETURN count(g) AS n",
            id=ORTEGA,
            database_=settings.neo4j_database,
        )
        if records[0]["n"] == 0:
            pytest.skip("No loan fraud data or connected groups. Run make rebuild.")
        yield driver


def _count_referrals(driver: neo4j.Driver, database: str) -> int:
    records, _, _ = driver.execute_query(
        "MATCH (r:FraudReferral) RETURN count(r) AS n", database_=database
    )
    return records[0]["n"]


def test_referral_links_the_evidence_and_cleans_up(
    driver: neo4j.Driver, settings: Settings
) -> None:
    database = settings.neo4j_database
    if _count_referrals(driver, database):
        pytest.skip("FraudReferral nodes already exist. Run referral_tools --cleanup.")
    context = ReferralContext(driver, database, BANKER, AS_OF)
    staff = StaffContext(driver, database, BANKER, AS_OF)
    try:
        referral = referral_tools.create_fraud_referral(
            context, ORTEGA_APPLICATION, RED_FLAGS, SUMMARY
        )
        assert set(referral) == REFERRAL_KEYS
        assert referral["referral_id"] == "REF-0001"
        assert referral["status"] == "OPEN"
        assert referral["created_at"].startswith(AS_OF.isoformat())
        assert referral["summary"] == SUMMARY
        assert referral["application"] == ORTEGA_APPLICATION
        assert referral["business"]["business_id"] == ORTEGA
        assert referral["group_id"] == ORTEGA_GROUP
        assert sorted(referral["cites"]) == sorted(RED_FLAGS)
        assert referral["assigned_to"] == {"reviewer_id": "FR-02", "name": "Sam Price"}
        assert referral["submitted_by"]["banker_id"] == BANKER

        records, _, _ = driver.execute_query(
            """
            MATCH (r:FraudReferral {referral_id: $id})
            RETURN [(r)-[:FOR_APPLICATION]->(a) | a.application_id] AS apps,
                   [(r)-[:ABOUT_GROUP]->(g) | g.group_id] AS groups,
                   [(r)-[:CITES]->(rule) | rule.rule_code] AS cites,
                   [(r)-[:ASSIGNED_TO]->(f) | f.reviewer_id] AS reviewers,
                   [(b)-[:SUBMITTED]->(r) | b.banker_id] AS bankers
            """,
            id=referral["referral_id"],
            database_=database,
        )
        links = records[0]
        assert links["apps"] == [ORTEGA_APPLICATION]
        assert links["groups"] == [ORTEGA_GROUP]
        assert sorted(links["cites"]) == sorted(RED_FLAGS)
        assert links["reviewers"] == ["FR-02"]
        assert links["bankers"] == [BANKER]

        lending = staff_tools.check_lending_rules(staff, ORTEGA_APPLICATION)
        assert lending["open_fraud_referral"] is True

        again = referral_tools.create_fraud_referral(
            context, ORTEGA_APPLICATION, RED_FLAGS, SUMMARY
        )
        assert again == {
            "error": f"Application {ORTEGA_APPLICATION} already has an open "
            "referral, REF-0001."
        }
        assert referral_tools.create_fraud_referral(
            context, KEYSTONE_APPLICATION, RED_FLAGS, SUMMARY
        ) == {
            "error": f"No application {KEYSTONE_APPLICATION} from a client in your "
            "book."
        }

        resolved = referral_tools.resolve_fraud_referral(
            context, "REF-0001", "ACCEPTED"
        )
        assert resolved["status"] == "ACCEPTED"
        lending = staff_tools.check_lending_rules(staff, ORTEGA_APPLICATION)
        assert lending["open_fraud_referral"] is False
        assert "error" in referral_tools.resolve_fraud_referral(
            context, "REF-0001", "CLOSED"
        )
    finally:
        referral_tools.delete_demo_referrals(driver, database)
    assert _count_referrals(driver, database) == 0
