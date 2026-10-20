"""Phase 4 checks for the banker-scoped staff tools.

The unit tests need no database. The live tests need the fraud data, and the
connected group tests also need ``ConnectedGroup`` nodes. Each skips until
``make rebuild`` has written what it needs.
"""

import ast
import inspect
from collections.abc import Iterator
from datetime import date
from typing import Any

import neo4j
import pytest

from graphrag_banking import staff_tools
from graphrag_banking.config import Settings, get_driver, load_settings
from graphrag_banking.staff_tools import (
    StaffContext,
    _annualize,
    _beneficial_owners,
    _check_authority,
    _check_line,
    _effective_percent,
    _format_money,
    _parse_date,
    _shares_identifiers,
    _summarize_loops,
)

AS_OF = date(2026, 10, 8)
BANKER = "RM-07"
ORTEGA = "B-1002"
KEYSTONE = "B-1004"
BRIGHTLINE = "B-1007"
HARBOR = "B-1008"
ORTEGA_APPLICATION = "APP-1001"
KEYSTONE_APPLICATION = "APP-1002"
BRIGHTLINE_APPLICATION = "APP-1005"
BALANCE_KEYS = {"ledger_balance", "available_balance", "balance", "loan_balance"}

# The keys each tool returns, on the full path and on every empty one.
FIND_KEYS = {"clients", "outside_my_book"}
CLIENT_KEYS = {"business_id", "name", "industry", "registered_on", "applications"}
APPLICATION_KEYS = {
    "application_id",
    "type",
    "amount",
    "stated_annual_revenue",
    "submitted_at",
    "status",
    "business",
}
LENDING_KEYS = {
    "application",
    "business",
    "revenue",
    "open_fraud_referral",
    "approver",
    "rules",
}
OWNERS_KEYS = {"business", "beneficial_owners", "red_flags", "rules"}
OWNER_KEYS = {
    "owner_id",
    "name",
    "kind",
    "in_my_book",
    "chains",
    "written_off_loans",
    "effective_percent",
}
GROUP_KEYS = {
    "business",
    "group",
    "most_central",
    "members",
    "shared_identifiers",
    "ownership_links",
    "director_links",
    "excluded_links",
    "red_flags",
    "rules",
}
MEMBER_KEYS = {"id", "name", "kind", "centrality", "in_my_book", "banker", "applied_on"}
FLOW_KEYS = {
    "business",
    "date_from",
    "date_to",
    "total_deposits",
    "circular_deposits",
    "circular_share_percent",
    "deposits_outside_loops",
    "sent_into_loops",
    "annual_revenue_without_loops",
    "max_line_without_loops",
    "loops",
    "red_flags",
    "rules",
}
SUMMARY_KEYS = FLOW_KEYS - {
    "business",
    "date_from",
    "date_to",
    "loops",
    "red_flags",
    "rules",
}
RULE_KEYS = {"rule_code", "name", "condition", "policy", "policy_text"}

LINE_RULE = {"rule_code": "LEND-BUSLINE-REV", "percent": 25}
AUTHORITY_RULE = {"rule_code": "AUTH-RM-LIMIT", "amount": 500000}
BANKER_ROW = {"name": "Dana Whitfield", "approval_limit": 500000.0}

TOOLS = [
    staff_tools.find_my_client,
    staff_tools.get_application,
    staff_tools.check_lending_rules,
    staff_tools.get_beneficial_owners,
    staff_tools.get_connected_group,
    staff_tools.find_circular_flows,
]

# Every query that returns details about one business or application.
DETAIL_QUERIES = [
    staff_tools._GET_APPLICATION,
    staff_tools._CHECK_LENDING_RULES,
    staff_tools._BENEFICIAL_OWNERS,
    staff_tools._CONNECTED_GROUP,
    staff_tools._CIRCULAR_FLOWS,
]


class _Record:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def data(self) -> dict[str, Any]:
        return self._data


class _FakeDriver:
    """Returns the same rows for every query, so pure logic runs offline."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def execute_query(self, query: str, **params: Any) -> tuple[Any, None, None]:
        return [_Record(row) for row in self.rows], None, None


def _offline(rows: list[dict[str, Any]]) -> StaffContext:
    return StaffContext(_FakeDriver(rows), "neo4j", BANKER, AS_OF)  # type: ignore[arg-type]


def _keys(value: Any) -> set[str]:
    """Every dict key anywhere in a tool result."""
    match value:
        case dict():
            return set(value) | {k for item in value.values() for k in _keys(item)}
        case list():
            return {k for item in value for k in _keys(item)}
        case _:
            return set()


def test_effective_percent_multiplies_along_a_chain() -> None:
    assert _effective_percent([[80.0, 70.0]]) == 56.0


def test_effective_percent_adds_chains_together() -> None:
    assert _effective_percent([[50.0, 50.0], [20.0]]) == 45.0


def test_beneficial_owners_keep_the_threshold_and_sort_by_share() -> None:
    owners = [
        {"name": "Small", "chains": [{"path": ["S", "X"], "percents": [10.0]}]},
        {"name": "Edge", "chains": [{"path": ["E", "X"], "percents": [25.0]}]},
        {
            "name": "Deep",
            "chains": [{"path": ["D", "H", "X"], "percents": [80.0, 70.0]}],
        },
    ]
    result = _beneficial_owners(owners, 25)
    assert [owner["name"] for owner in result] == ["Deep", "Edge"]
    assert result[0]["effective_percent"] == 56.0
    assert result[0]["chains"] == [{"path": ["D", "H", "X"], "share_percent": 56.0}]


def test_annualize_uses_a_360_day_year() -> None:
    assert _annualize(610000.0, 90) == 2440000.0


def test_line_check_applies_to_business_lines_only() -> None:
    line = {"type": "BUSINESS_LINE", "amount": 400000.0}
    passed = _check_line(line, 2440000.0, LINE_RULE)
    assert passed["applies"] and passed["passed"]
    assert passed["max_line"] == 610000.0
    assert not _check_line(line, 620000.0, LINE_RULE)["passed"]
    term = _check_line({"type": "TERM_LOAN", "amount": 1.0}, 0.0, LINE_RULE)
    assert not term["applies"] and term["passed"] is None


def test_authority_names_the_approver() -> None:
    mine = _check_authority(400000.0, BANKER_ROW, AUTHORITY_RULE, False)
    assert mine["passed"] and mine["approver"].startswith("Dana Whitfield")
    committee = _check_authority(600000.0, BANKER_ROW, AUTHORITY_RULE, False)
    assert not committee["passed"] and committee["approver"] == "The credit committee"
    blocked = _check_authority(1000.0, BANKER_ROW, AUTHORITY_RULE, True)
    assert not blocked["passed"] and blocked["approver"].startswith("No one")


def test_authority_uses_the_lower_of_banker_and_rule_limits() -> None:
    banker = {"name": "New", "approval_limit": 100000.0}
    result = _check_authority(200000.0, banker, AUTHORITY_RULE, False)
    assert result["approval_limit"] == 100000.0
    assert result["approver"] == "The credit committee"


def test_shared_identifiers_need_two_applicants() -> None:
    one = [{"applicants": ["A"]}]
    two = [{"applicants": ["A", "B"]}]
    assert not _shares_identifiers(one, [])
    assert _shares_identifiers(two, [])


def test_a_director_of_two_applicants_is_shared() -> None:
    links = [
        {"director": "D", "business": "A", "business_has_open_application": True},
        {"director": "D", "business": "B", "business_has_open_application": True},
        {"director": "E", "business": "C", "business_has_open_application": True},
    ]
    assert _shares_identifiers([], links)
    assert not _shares_identifiers([], links[1:])


def test_loop_summary_counts_each_transfer_out_once() -> None:
    loops = [
        {"returned_amount": 50.0, "sent_transaction_id": "T-1", "sent_amount": 40.0},
        {"returned_amount": 30.0, "sent_transaction_id": "T-1", "sent_amount": 40.0},
        {"returned_amount": 20.0, "sent_transaction_id": "T-2", "sent_amount": 10.0},
    ]
    summary = _summarize_loops(loops, 200.0, 90, 25)
    assert summary["circular_deposits"] == 100.0
    assert summary["sent_into_loops"] == 50.0
    assert summary["deposits_outside_loops"] == 100.0
    assert summary["circular_share_percent"] == 50.0
    assert summary["annual_revenue_without_loops"] == 400.0
    assert summary["max_line_without_loops"] == 100.0


def test_loop_summary_with_no_deposits() -> None:
    assert _summarize_loops([], 0.0, 90, 25)["circular_share_percent"] == 0.0


def test_loop_summary_with_no_loops_has_every_key() -> None:
    summary = _summarize_loops([], 300.0, 90, 25)
    assert set(summary) == SUMMARY_KEYS
    assert summary["circular_deposits"] == 0.0
    assert summary["sent_into_loops"] == 0
    assert summary["deposits_outside_loops"] == 300.0


def test_no_owners_and_no_shared_identifiers_are_empty() -> None:
    assert _beneficial_owners([], 25) == []
    assert _shares_identifiers([], []) is False


def test_find_my_client_with_no_matches_has_both_lists() -> None:
    assert staff_tools.find_my_client(_offline([]), "nobody") == {
        "clients": [],
        "outside_my_book": [],
    }


def test_a_rule_keeps_missing_fields_as_none() -> None:
    rule = {
        "rule_code": "FRAUD-SHARED-ID",
        "name": "Shared identifiers",
        "condition": None,
        "policy": None,
        "policy_text": [],
        "percent": None,
        "years": None,
        "lookback_days": None,
        "amount": None,
        "min_red_flags": None,
    }
    found = staff_tools._rules(_offline([{"rule": rule}]), "FRAUD-SHARED-ID")
    result = found["FRAUD-SHARED-ID"]
    assert set(result) == RULE_KEYS
    assert result["policy"] is None and result["policy_text"] == []


def test_money_is_formatted_but_percents_are_not() -> None:
    result = _format_money(
        {"amount": 5000, "rules": [{"percent": 25, "max_line": 1.5}]}
    )
    assert result == {
        "amount": "$5,000.00",
        "rules": [{"percent": 25, "max_line": "$1.50"}],
    }


def test_parse_date() -> None:
    assert _parse_date(None) is None
    assert _parse_date("2026-07-10") == date(2026, 7, 10)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _parse_date("07/10/2026")


def test_every_detail_query_checks_manages() -> None:
    for query in DETAIL_QUERIES:
        first_line = query.lstrip().splitlines()[0]
        assert first_line.startswith("MATCH ("), first_line
        assert "Banker {banker_id: $banker_id})-[:MANAGES]->" in first_line


def test_tools_import_only_the_neo4j_driver() -> None:
    tree = ast.parse(inspect.getsource(staff_tools))
    modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules <= {"math", "dataclasses", "datetime", "typing", "neo4j"}


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
            "MATCH (b:Business {business_id: $id})-[:APPLIED_FOR]->() "
            "RETURN count(b) AS n",
            id=ORTEGA,
            database_=settings.neo4j_database,
        )
        if records[0]["n"] == 0:
            pytest.skip("No loan fraud data. Run make rebuild.")
        yield driver


@pytest.fixture
def context(driver: neo4j.Driver, settings: Settings) -> StaffContext:
    return StaffContext(driver, settings.neo4j_database, BANKER, AS_OF)


@pytest.fixture(scope="module")
def groups(driver: neo4j.Driver, settings: Settings) -> None:
    records, _, _ = driver.execute_query(
        "MATCH (g:ConnectedGroup) RETURN count(g) AS n",
        database_=settings.neo4j_database,
    )
    if records[0]["n"] == 0:
        pytest.skip("No connected groups. Run make rebuild.")


def test_find_my_client_lists_my_application(context: StaffContext) -> None:
    result = staff_tools.find_my_client(context, "ortega")
    [client] = result["clients"]
    assert client["business_id"] == ORTEGA
    assert [a["application_id"] for a in client["applications"]] == [ORTEGA_APPLICATION]


def test_find_my_client_names_other_books_without_details(
    context: StaffContext,
) -> None:
    result = staff_tools.find_my_client(context, "Keystone")
    assert result["clients"] == []
    [other] = result["outside_my_book"]
    assert other["name"] == "Keystone Paving"
    assert set(other) == {"name", "banker", "connected_to_my_clients"}


def test_find_my_client_needs_a_name(context: StaffContext) -> None:
    with pytest.raises(ValueError):
        staff_tools.find_my_client(context, "  ")


def test_get_application(context: StaffContext) -> None:
    result = staff_tools.get_application(context, ORTEGA_APPLICATION)
    assert result["amount"] == "$400,000.00"
    assert result["stated_annual_revenue"] == "$2,440,000.00"
    assert result["business"]["business_id"] == ORTEGA


def test_lending_rules_pass_on_deposits_alone(context: StaffContext) -> None:
    result = staff_tools.check_lending_rules(context, ORTEGA_APPLICATION)
    assert result["revenue"]["total_deposits"] == "$610,000.00"
    line, authority = result["rules"]
    assert line["rule_code"] == "LEND-BUSLINE-REV" and line["passed"]
    assert authority["rule_code"] == "AUTH-RM-LIMIT" and authority["passed"]
    assert all(rule["policy_text"] for rule in result["rules"])


def test_brightline_passes_the_lending_rules(context: StaffContext) -> None:
    result = staff_tools.check_lending_rules(context, BRIGHTLINE_APPLICATION)
    assert result["revenue"]["total_deposits"] == "$300,000.00"
    assert all(rule["passed"] for rule in result["rules"])


def test_hale_owns_56_percent_and_has_a_written_off_loan(
    context: StaffContext,
) -> None:
    result = staff_tools.get_beneficial_owners(context, ORTEGA)
    owners = {owner["name"]: owner for owner in result["beneficial_owners"]}
    hale = owners["Victor Hale"]
    assert hale["effective_percent"] == 56.0
    assert hale["chains"][0]["path"] == [
        "Victor Hale",
        "Crestline Holdings",
        "Ortega Builders",
    ]
    [loan] = hale["written_off_loans"]
    assert loan["loan_id"] == "L-1001"
    assert loan["borrower"] == "Hale Restoration LLC"
    assert loan["within_lookback"]
    assert owners["Luis Ortega"]["effective_percent"] == 30.0
    assert result["red_flags"] == ["FRAUD-PRIOR-LOSS"]
    assert all(rule["policy_text"] for rule in result["rules"])


def test_brightline_owners_are_clean(context: StaffContext) -> None:
    result = staff_tools.get_beneficial_owners(context, BRIGHTLINE)
    [owner] = result["beneficial_owners"]
    assert owner["effective_percent"] == 100.0
    assert owner["written_off_loans"] == []
    assert result["red_flags"] == []


def test_ortega_loops_455_of_610_thousand(context: StaffContext) -> None:
    result = staff_tools.find_circular_flows(context, ORTEGA)
    assert result["date_from"] == "2026-07-10"
    assert result["total_deposits"] == "$610,000.00"
    assert result["circular_deposits"] == "$455,000.00"
    assert result["sent_into_loops"] == "$370,000.00"
    assert len(result["loops"]) == 8
    assert all(loop["route"][0] == loop["route"][-1] for loop in result["loops"])
    assert result["red_flags"] == ["FRAUD-CIRCULAR-FLOW"]
    assert all(rule["policy_text"] for rule in result["rules"])


def test_brightline_has_no_loops(context: StaffContext) -> None:
    result = staff_tools.find_circular_flows(context, BRIGHTLINE)
    assert result["loops"] == []
    assert result["red_flags"] == []


def test_circular_flows_reject_bad_dates(context: StaffContext) -> None:
    with pytest.raises(ValueError):
        staff_tools.find_circular_flows(context, ORTEGA, "2026-10-08", "2026-07-10")


@pytest.mark.usefixtures("groups")
def test_ortega_group_shares_a_phone_and_a_device(context: StaffContext) -> None:
    result = staff_tools.get_connected_group(context, ORTEGA)
    shared = {i["kind"]: i for i in result["shared_identifiers"]}
    assert shared["PHONE"]["value"] == "+1-555-0610"
    assert len(shared["PHONE"]["applicants"]) >= 2
    assert shared["DEVICE"]["value"] == "DEV-1001"
    assert len(shared["DEVICE"]["applicants"]) >= 2
    assert result["most_central"] == "Victor Hale"
    assert result["red_flags"] == ["FRAUD-SHARED-ID"]
    assert all(rule["policy_text"] for rule in result["rules"])


@pytest.mark.usefixtures("groups")
def test_registered_agent_address_is_excluded(context: StaffContext) -> None:
    for business_id in [ORTEGA, BRIGHTLINE, HARBOR]:
        result = staff_tools.get_connected_group(context, business_id)
        assert all(
            i["kind"] != "ADDRESS" or i["address_kind"] != "REGISTERED_AGENT"
            for i in result["shared_identifiers"]
        )
        [agent] = [
            i
            for i in result["excluded_links"]
            if i["address_kind"] == "REGISTERED_AGENT"
        ]
        assert agent["used_by_count"] > 200


@pytest.mark.usefixtures("groups")
def test_brightline_group_is_clean(context: StaffContext) -> None:
    result = staff_tools.get_connected_group(context, BRIGHTLINE)
    assert result["shared_identifiers"] == []
    assert result["red_flags"] == []


def test_another_bankers_business_is_refused(context: StaffContext) -> None:
    error = {"error": f"No business {KEYSTONE} in your book."}
    assert staff_tools.get_beneficial_owners(context, KEYSTONE) == error
    assert staff_tools.get_connected_group(context, KEYSTONE) == error
    assert staff_tools.find_circular_flows(context, KEYSTONE) == error
    for tool in [staff_tools.get_application, staff_tools.check_lending_rules]:
        result = tool(context, KEYSTONE_APPLICATION)
        assert result == {
            "error": f"No application {KEYSTONE_APPLICATION} from a client in your book."
        }


def test_no_tool_returns_a_balance(context: StaffContext) -> None:
    results = [
        staff_tools.find_my_client(context, "Keystone"),
        staff_tools.get_application(context, ORTEGA_APPLICATION),
        staff_tools.check_lending_rules(context, ORTEGA_APPLICATION),
        staff_tools.get_beneficial_owners(context, ORTEGA),
        staff_tools.get_connected_group(context, ORTEGA),
        staff_tools.find_circular_flows(context, ORTEGA),
    ]
    assert not _keys(results) & BALANCE_KEYS


def test_other_businesses_on_a_loop_show_no_amounts(context: StaffContext) -> None:
    result = staff_tools.find_circular_flows(context, ORTEGA)
    for loop in result["loops"]:
        assert all(isinstance(stop, str) for stop in loop["route"])


@pytest.mark.usefixtures("groups")
def test_no_tool_returns_a_home_address(context: StaffContext) -> None:
    results = [
        staff_tools.find_my_client(context, "ortega"),
        staff_tools.get_application(context, ORTEGA_APPLICATION),
        staff_tools.check_lending_rules(context, ORTEGA_APPLICATION),
        staff_tools.get_beneficial_owners(context, ORTEGA),
        staff_tools.get_connected_group(context, ORTEGA),
        staff_tools.find_circular_flows(context, ORTEGA),
    ]
    assert "Birchwood" not in repr(results)
    shared = results[4]["shared_identifiers"]
    [home] = [i for i in shared if i["address_kind"] == "HOME"]
    assert home["value"] is None
    assert "Victor Hale" in home["used_by"]


@pytest.mark.usefixtures("groups")
def test_outside_members_have_no_application_date(context: StaffContext) -> None:
    result = staff_tools.get_connected_group(context, ORTEGA)
    members = {m["name"]: m for m in result["members"]}
    assert members["Summit Ridge Supply"]["applied_on"] is None
    assert members["Ortega Builders"]["applied_on"] is not None
    assert all(m["applied_on"] is None for m in members.values() if not m["in_my_book"])


@pytest.mark.parametrize("name", ["ortega", "brightline"])
def test_find_my_client_has_every_key(context: StaffContext, name: str) -> None:
    result = staff_tools.find_my_client(context, name)
    assert set(result) == FIND_KEYS
    assert result["outside_my_book"] == []
    assert all(set(client) == CLIENT_KEYS for client in result["clients"])


def test_get_application_has_every_key(context: StaffContext) -> None:
    for application_id in [ORTEGA_APPLICATION, BRIGHTLINE_APPLICATION]:
        result = staff_tools.get_application(context, application_id)
        assert set(result) == APPLICATION_KEYS


def test_lending_rules_have_every_key(context: StaffContext) -> None:
    for application_id in [ORTEGA_APPLICATION, BRIGHTLINE_APPLICATION]:
        result = staff_tools.check_lending_rules(context, application_id)
        assert set(result) == LENDING_KEYS
        assert all(RULE_KEYS <= set(rule) for rule in result["rules"])


def test_owners_have_every_key(context: StaffContext) -> None:
    for business_id in [ORTEGA, BRIGHTLINE]:
        result = staff_tools.get_beneficial_owners(context, business_id)
        assert set(result) == OWNERS_KEYS
        assert all(set(o) == OWNER_KEYS for o in result["beneficial_owners"])
        assert all(RULE_KEYS <= set(rule) for rule in result["rules"])


@pytest.mark.usefixtures("groups")
def test_brightline_with_no_group_has_every_key(context: StaffContext) -> None:
    result = staff_tools.get_connected_group(context, BRIGHTLINE)
    assert set(result) == GROUP_KEYS
    assert result["group"] is None
    assert result["most_central"] is None
    assert result["shared_identifiers"] == []
    assert result["ownership_links"] == []
    assert result["director_links"] == []
    assert result["red_flags"] == []
    [member] = result["members"]
    assert set(member) == MEMBER_KEYS
    assert member["centrality"] is None
    assert all(RULE_KEYS <= set(rule) for rule in result["rules"])


@pytest.mark.usefixtures("groups")
def test_ortega_group_has_the_same_keys(context: StaffContext) -> None:
    result = staff_tools.get_connected_group(context, ORTEGA)
    assert set(result) == GROUP_KEYS
    assert all(set(member) == MEMBER_KEYS for member in result["members"])


def test_brightline_with_no_loops_has_every_key(context: StaffContext) -> None:
    result = staff_tools.find_circular_flows(context, BRIGHTLINE)
    assert set(result) == FLOW_KEYS
    assert set(result) == set(staff_tools.find_circular_flows(context, ORTEGA))
    assert result["loops"] == []
    assert result["red_flags"] == []
    assert result["circular_deposits"] == "$0.00"
    assert all(RULE_KEYS <= set(rule) for rule in result["rules"])
