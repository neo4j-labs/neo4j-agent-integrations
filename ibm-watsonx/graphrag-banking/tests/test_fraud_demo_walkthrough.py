"""Unit tests for fraud_demo_walkthrough's parsing and formatting. None need a tenant."""

import argparse

import pytest

from graphrag_banking import fraud_demo_walkthrough as fraud
from graphrag_banking.demo_walkthrough import StepError

TRACE = """
│  Step 1: Called tool 'chat_with_collaborator_credit_analyst'      │
│    Agent: bank_supervisor                                         │
│  Step 2: Tool 'chat_with_collaborator_credit_analyst' responded   │
│  Step 3: Called tool 'check_lending_rules'                        │
│    Agent: credit_analyst                                          │
│  Step 4: Tool 'check_lending_rules' responded                     │
│  Step 5: Called tool 'chat_with_collaborator_fraud_investigator'  │
│    Agent: bank_supervisor                                         │
│  Step 6: Called tool 'screen_business'                            │
│    Agent: fraud_investigator                                      │
"""


class FakeNode:
    def __init__(self, labels: set[str], **props: object) -> None:
        self.labels = labels
        self._props = props

    def keys(self):
        return self._props.keys()

    def __getitem__(self, key: str) -> object:
        return self._props[key]

    def __iter__(self):
        return iter(self._props.items())


class FakeRel:
    def __init__(self, type_: str, **props: object) -> None:
        self.type = type_
        self._props = props

    def keys(self):
        return self._props.keys()

    def __getitem__(self, key: str) -> object:
        return self._props[key]

    def __iter__(self):
        return iter(self._props.items())


class FakePath:
    def __init__(self, nodes: list[FakeNode], relationships: list[FakeRel]) -> None:
        self.nodes = nodes
        self.relationships = relationships


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", [3]),
        ("6-8", [6, 7, 8]),
        ("1,4", [1, 4]),
        ("4,1-2,2", [1, 2, 4]),
        (" 9 , 10 ", [9, 10]),
    ],
)
def test_parse_steps(value: str, expected: list[int]) -> None:
    assert fraud.parse_steps(value, range(1, 11)) == expected


@pytest.mark.parametrize("value", ["0", "11", "a", "3-x", "", ","])
def test_parse_steps_rejects(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        fraud.parse_steps(value, range(1, 11))


def test_steps_are_numbered_one_to_eleven_in_order() -> None:
    assert [s.number for s in fraud.STEPS] == list(range(1, 12))
    assert fraud.STEPS[fraud.SCORING_STEP - 1].run is fraud.step_score
    assert [fraud.STEPS[n - 1].run for n in fraud.THREAD_STEPS] == [
        fraud.step_fix,
        fraud.step_follow_up,
    ]


def test_check_inputs_needs_a_thread_for_step_nine() -> None:
    with pytest.raises(StepError, match="thread ID"):
        fraud.check_inputs([9], None)
    fraud.check_inputs([9], "abc")
    fraud.check_inputs([8, 9], None)
    fraud.check_inputs([1, 2], None)


def test_connection_keys_lists_names_only() -> None:
    script = (
        "set -e\n"
        "KEYS=(NEO4J_URI NEO4J_PASSWORD DEMO_BANKER_ID)\n"
        "NEO4J_PASSWORD=hunter2\n"
    )
    assert fraud.connection_keys(script) == [
        "NEO4J_URI",
        "NEO4J_PASSWORD",
        "DEMO_BANKER_ID",
    ]
    assert fraud.connection_keys("echo hi") == []


def test_connection_keys_matches_the_real_script() -> None:
    script = fraud.CONNECTION_SCRIPT.read_text(encoding="utf-8")
    keys = fraud.connection_keys(script)
    assert "DEMO_BANKER_ID" in keys
    assert "NEO4J_PASSWORD" in keys


def test_pick_tools_keeps_the_requested_order() -> None:
    tools = [{"name": "b"}, {"name": "x"}, {"name": "a"}]
    assert fraud.pick_tools(tools, ["a", "b", "missing"]) == [
        {"name": "a"},
        {"name": "b"},
    ]


def test_tool_connections_and_packages() -> None:
    tool = {
        "binding": {
            "python": {
                "connections": {"banker_creds": "id"},
                "requirements": ["neo4j==6.4.0"],
            }
        }
    }
    assert fraud.tool_connections(tool) == ["banker_creds"]
    assert fraud.tool_packages(tool) == ["neo4j==6.4.0"]
    assert fraud.tool_connections({}) == []
    assert fraud.tool_packages({"binding": None}) == []


def test_names_for_keeps_unknown_ids() -> None:
    assert fraud.names_for(["2", "9", "1"], {"1": "b", "2": "a"}) == ["9", "a", "b"]


def test_trace_calls_pairs_each_tool_with_its_agent() -> None:
    assert fraud.trace_calls(TRACE) == [
        ("bank_supervisor", "chat_with_collaborator_credit_analyst"),
        ("credit_analyst", "check_lending_rules"),
        ("bank_supervisor", "chat_with_collaborator_fraud_investigator"),
        ("fraud_investigator", "screen_business"),
    ]
    assert fraud.trace_calls("no trace here") == []


def test_call_kind() -> None:
    assert fraud.call_kind("chat_with_collaborator_banking_policy") == (
        "collaborator call"
    )
    assert fraud.call_kind("screen_business") == "graph tool"
    assert fraud.call_kind("banking_policies") == "knowledge base"
    assert fraud.call_kind("something_else") == "other"


def test_collaborators_called() -> None:
    calls = fraud.trace_calls(TRACE)
    assert fraud.collaborators_called(calls, "bank_supervisor") == [
        "credit_analyst",
        "fraud_investigator",
    ]
    assert fraud.collaborators_called([], "bank_supervisor") == []


def test_group_rows_marks_the_applicants_group() -> None:
    groups = [
        {
            "group_id": "CG-0001",
            "size": 11,
            "most_central": {"name": "Victor Hale", "score": 25.6},
            "has_applicant": True,
        },
        {
            "group_id": "CG-0002",
            "size": 5,
            "most_central": {"name": "A", "score": 0.0},
            "has_applicant": False,
        },
    ]
    assert fraud.group_rows(groups) == [
        ("CG-0001", "11", "Victor Hale", "25.60", "yes"),
        ("CG-0002", "5", "A", "0.00", "-"),
    ]


def test_group_readers_keeps_fraud_group_tools_once() -> None:
    calls = [
        *fraud.trace_calls(TRACE),
        ("fraud_investigator", "get_connected_group"),
        ("fraud_investigator", "screen_business"),
        ("credit_analyst", "get_connected_group"),
    ]
    assert fraud.group_readers(calls) == ["screen_business", "get_connected_group"]
    assert fraud.group_readers([]) == []


def test_member_and_identifier_rows() -> None:
    result = {
        "members": [
            {
                "name": "Victor Hale",
                "kind": "PERSON",
                "centrality": 25.6,
                "banker": None,
            },
            {
                "name": "Ortega Builders",
                "kind": "BUSINESS",
                "centrality": None,
                "banker": "Dana Whitfield",
            },
        ],
        "shared_identifiers": [
            {
                "kind": "PHONE",
                "value": "+1-555-0610",
                "used_by": ["a", "b", "c"],
                "applicants": ["a", "b"],
            },
            {"kind": "ADDRESS", "value": None, "used_by": ["a", "b"], "applicants": []},
        ],
    }
    assert fraud.member_rows(result) == [
        ("Victor Hale", "person", "25.60", "-"),
        ("Ortega Builders", "business", "-", "Dana Whitfield"),
    ]
    assert fraud.identifier_rows(result) == [
        ("phone", "+1-555-0610", "3", "2"),
        ("address", "home address", "2", "0"),
    ]


def test_rule_codes_finds_nested_codes_once() -> None:
    value = {
        "rules": [{"rule_code": "B"}, {"x": {"rule_code": "A"}}, {"rule_code": "B"}],
        "n": 1,
    }
    assert fraud.rule_codes(value) == ["A", "B"]
    assert fraud.rule_codes("text") == []


def test_money() -> None:
    assert fraud.money(2440000.0) == "$2,440,000"


def row(**overrides: object) -> dict[str, object]:
    base = {
        "application_id": "APP-1001",
        "type": "BUSINESS_LINE",
        "amount": 400_000,
        "stated_revenue": 2_440_000,
        "deposits": 610_000,
        "line_percent": 25,
        "banker": "Dana Whitfield",
        "approval_limit": 500_000,
    }
    return {**base, **overrides}


def test_scene_rows_match_the_doc() -> None:
    rows = fraud.scene_rows(row())
    assert [r[3] for r in rows] == ["yes"] * 6
    assert rows[3] == (
        "Verified annual revenue (90-day deposits annualized)",
        "$2,440,000",
        "$2,440,000",
        "yes",
    )
    assert rows[4][1] == "$610,000"
    assert rows[5][0] == "Dana Whitfield's approval limit"


def test_scene_rows_flag_a_difference() -> None:
    rows = fraud.scene_rows(row(deposits=500_000))
    assert [r[3] for r in rows] == ["yes", "yes", "NO", "NO", "NO", "yes"]


def runs() -> list[dict[str, object]]:
    def run(agent: str, passed: dict[str, bool]) -> dict[str, object]:
        return {
            "agent": agent,
            "checks": [
                {"kind": "answer", "fact": f, "passed": p} for f, p in passed.items()
            ]
            + [{"kind": "trace", "fact": "{}", "passed": True}],
            "tool_calls": [],
        }

    return [
        run("credit_analyst", {"names owner": False, "names loop": False}),
        run("bank_supervisor", {"names owner": True, "names loop": True}),
    ]


def test_answer_fact_rows() -> None:
    rows = fraud.answer_fact_rows(runs(), ["credit_analyst", "bank_supervisor"])
    assert rows == [
        ("names owner", "FAIL", "PASS"),
        ("names loop", "FAIL", "PASS"),
    ]


def test_answer_fact_rows_marks_a_missing_agent() -> None:
    rows = fraud.answer_fact_rows(runs(), ["credit_analyst", "nobody"])
    assert rows[0] == ("names owner", "FAIL", "-")


def test_trace_found() -> None:
    assert fraud.trace_found(runs()[0]) == "1 of 1"


def test_markdown_table() -> None:
    table = fraud.markdown_table(("Fact", "A"), [("x", "PASS")])
    assert table == "| Fact | A |\n|---|---|\n| x | PASS |\n"


def test_path_line_with_percents_and_amounts() -> None:
    hale = FakeNode({"Person"}, name="Victor Hale")
    crest = FakeNode({"Business"}, name="Crestline Holdings")
    txn = FakeNode({"Transaction"}, transaction_id="T-1", amount=45000.0)
    account = FakeNode({"Account"}, account_id="A-3001")
    path = FakePath(
        [hale, crest, txn, account],
        [
            FakeRel("OWNS", percent=80.0),
            FakeRel("HAS_TRANSACTION"),
            FakeRel("TO_ACCOUNT"),
        ],
    )
    assert fraud.path_line(path) == (
        "Victor Hale -[OWNS 80%]-> Crestline Holdings -[HAS_TRANSACTION]-> "
        "T-1 ($45,000) -[TO_ACCOUNT]-> A-3001"
    )


def test_node_label_for_loans_groups_and_chunks() -> None:
    loan = FakeNode({"Loan"}, loan_id="L-1", status="WRITTEN_OFF", balance=186400)
    group = FakeNode({"ConnectedGroup"}, group_id="CG-0001", size=11)
    chunk = FakeNode({"Chunk"}, index=2)
    assert fraud.node_label(loan) == "L-1 (WRITTEN_OFF, balance $186,400)"
    assert fraud.node_label(group) == "CG-0001 (11 members)"
    assert fraud.node_label(chunk) == "policy chunk 2"


def test_rel_label_with_centrality() -> None:
    assert fraud.rel_label(FakeRel("IN_GROUP", centrality=25.64)) == (
        "IN_GROUP centrality 25.6"
    )


def test_loop_total_sums_transactions_only() -> None:
    def loop(amount: float) -> FakePath:
        return FakePath(
            [
                FakeNode({"Business"}, name="B"),
                FakeNode({"Transaction"}, transaction_id="T", amount=amount),
            ],
            [FakeRel("HAS_TRANSACTION")],
        )

    assert fraud.loop_total([loop(45000.0), loop(50000.0)]) == 95000.0


def test_proof_query_file_returns_the_seven_collections() -> None:
    query = fraud.PROOF_QUERY_PATH.read_text(encoding="utf-8")
    for column in (
        "hidden_owner",
        "prior_loss",
        "shared_phone",
        "shared_device",
        "loop_in",
        "connected_group",
        "policy_text",
    ):
        assert f"AS {column}" in query
    for write in ("CREATE", "MERGE", "DELETE", "SET "):
        assert write not in query


def test_scene_cypher_is_read_only() -> None:
    for write in ("CREATE", "MERGE", "DELETE", "SET "):
        assert write not in fraud.SCENE_CYPHER
    assert "total_deposits AS deposits" in fraud.SCENE_CYPHER


def test_scenarios_for_the_steps_exist() -> None:
    ids = {s["id"] for s in fraud.load_scenarios()}
    assert {
        fraud.FAILURE_SCENARIO,
        fraud.FOLLOW_UP_SCENARIO,
        fraud.SCORED_SCENARIO,
    } <= ids


def test_graph_tools_drops_repeats_and_collaborator_calls() -> None:
    run = {
        "tool_calls": [
            {"name": "chat_with_collaborator_credit_analyst"},
            {"name": "find_my_client"},
            {"name": "screen_business"},
            {"name": "find_my_client"},
        ]
    }
    assert fraud.graph_tools(run) == "find_my_client, screen_business"
