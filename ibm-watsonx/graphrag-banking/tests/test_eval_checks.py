"""Unit tests for the eval checks and supervisor_check.py. None need a tenant."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from graphrag_banking.config import EVAL_DIR
from graphrag_banking.eval_local import found_in, load_scenarios, persona, score

sys.path.insert(0, str(EVAL_DIR / "eval-scripts"))
import score as wxo_score
import supervisor_check

FIXTURES = Path(__file__).with_name("fixtures")
YEAR = 2026


def _scenario(**fields: Any) -> dict[str, Any]:
    return {"answer_facts": [], "trace_facts": [], "must_not_appear": []} | fields


def _result(tool_results: list[Any], collaborators: list[str] | None = None) -> dict:
    result = {
        "answer": "",
        "tool_calls": [{"name": "t", "args": {}, "result": r} for r in tool_results],
    }
    if collaborators is not None:
        result["collaborators"] = collaborators
    return result


def _failed(checks: list) -> list[str]:
    return [c.fact for c in checks if not c.passed]


@pytest.fixture
def supervisor_run() -> dict[str, Any]:
    return json.loads((FIXTURES / "supervisor_A_run.json").read_text())


@pytest.fixture
def supervisor_trace() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "supervisor_A_trace.json").read_text())


def test_persona_defaults_to_customer() -> None:
    assert persona({}) == "customer"
    assert persona({"persona": "staff"}) == "staff"


def test_scenarios_split_by_persona() -> None:
    by_persona = {s["id"]: persona(s) for s in load_scenarios()}
    staff = {"E", "F", "G", "H", "I", "I1"}
    assert {sid for sid, p in by_persona.items() if p == "staff"} == staff
    assert {p for sid, p in by_persona.items() if sid not in staff} == {"customer"}
    assert set("ABCD") <= by_persona.keys() - staff


def test_routing_passes_with_expected_collaborators() -> None:
    scenario = _scenario(
        expected_collaborators=["credit_analyst", "fraud_investigator"],
        forbidden_collaborators=["banking_policy"],
    )
    checks = score(
        scenario, _result([], ["fraud_investigator", "credit_analyst"]), YEAR
    )
    assert [c.kind for c in checks] == ["routing"] * 3
    assert _failed(checks) == []


def test_routing_fails_on_missing_and_forbidden_collaborators() -> None:
    scenario = _scenario(
        expected_collaborators=["fraud_investigator"],
        forbidden_collaborators=["credit_analyst", "banking_policy"],
    )
    checks = score(scenario, _result([], ["credit_analyst"]), YEAR)
    assert _failed(checks) == [
        "calls fraud_investigator",
        "does not call credit_analyst",
    ]


def test_routing_absent_adds_no_checks() -> None:
    assert score(_scenario(), _result([]), YEAR) == []


@pytest.mark.parametrize(
    "leak",
    [
        {"balance": 65000.0},
        {"balance": "$65,000.00"},
        {"rows": [{"note": "balance 65,000"}]},
        {"accounts": [{"account_id": "A-3002"}]},
    ],
)
def test_trace_must_not_catches_leaks_in_nested_results(leak: dict) -> None:
    scenario = _scenario(trace_must_not=["A-3002", "65,000"])
    assert _failed(score(scenario, _result([{"business": leak}]), YEAR)) != []


def test_trace_must_not_ignores_other_amounts_and_ids() -> None:
    scenario = _scenario(trace_must_not=["A-3002", "65,000"])
    results = [{"amount": 650000.0, "account": "A-30021"}, {"group": None}, []]
    assert _failed(score(scenario, _result(results), YEAR)) == []


def test_absence_matches_empty_list_and_none() -> None:
    results = [{"business": {"business_id": "B-1007"}, "loops": [], "group": None}]
    assert found_in({"business": {"business_id": "B-1007"}, "loops": []}, results)
    assert found_in({"group": None}, results)
    assert not found_in({"loops": None}, results)
    assert not found_in({"group": []}, results)
    assert not found_in({"shared_identifiers": []}, results)


def test_score_run_keeps_agent_and_collaborators() -> None:
    run = {
        "agent": "bank_supervisor",
        "scenario": "G",
        "run": 1,
        "turn": 1,
        "status": "completed",
        "seconds": 1.0,
        "answer": "",
        "collaborators": ["fraud_investigator"],
        "tool_calls": [
            {
                "name": "get_connected_group",
                "args": {},
                "agent": "fraud_investigator",
                "content": '{"group": null}',
            }
        ],
    }
    scored = wxo_score.score_run(
        run, _scenario(expected_collaborators=["fraud_investigator"]), YEAR
    )
    assert scored["tool_calls"][0]["agent"] == "fraud_investigator"
    assert scored["collaborators"] == ["fraud_investigator"]
    assert scored["passed"]


def test_collaborator_answers_reads_collaborator_observations(supervisor_trace) -> None:
    answers = supervisor_check.collaborator_answers(supervisor_trace)
    assert [name for name, _ in answers] == ["banking_support"]
    assert "not a collaborator answer" not in answers[0][1]


def test_kept_reports_missing_collaborator_facts(
    supervisor_run, supervisor_trace
) -> None:
    scenario = {"expected_collaborators": ["banking_support"]}
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert result.calls == {"banking_support": 1}
    assert result.missing == {"banking_support": ["$5000"]}
    assert (result.kept, result.total) == (5, 6)
    assert not supervisor_check.passed(supervisor_run, result)


def test_kept_counts_names_from_own_tool_results(
    supervisor_run, supervisor_trace
) -> None:
    scenario = {"expected_collaborators": ["banking_support"]}
    supervisor_run["answer"] = supervisor_run["answer"].replace(
        "Outgoing wire fee", "Wire fee"
    )
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert result.missing["banking_support"] == ["$5000", "Outgoing wire fee"]


def test_added_reports_facts_no_collaborator_gave(
    supervisor_run, supervisor_trace
) -> None:
    scenario = {"expected_collaborators": ["banking_support"]}
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert result.added == []
    supervisor_run["answer"] += " See FEE-WIRE-OUT. A $12 fee applies to 15% of wires."
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert result.added == ["$12", "15%", "FEE-WIRE-OUT"]


def test_copy_compares_single_collaborator_answer(
    supervisor_run, supervisor_trace
) -> None:
    scenario = {"expected_collaborators": ["banking_support"]}
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert result.copy is False
    assert 0 < result.ratio < 1

    _, answer = supervisor_check.collaborator_answers(supervisor_trace)[0]
    supervisor_run["answer"] = answer
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert (result.copy, result.ratio) == (True, 1.0)
    assert result.missing == {}
    assert result.added == []
    assert supervisor_check.passed(supervisor_run, result)


def test_copy_not_reported_for_two_collaborators(
    supervisor_run, supervisor_trace
) -> None:
    scenario = {"expected_collaborators": ["credit_analyst", "fraud_investigator"]}
    result = supervisor_check.check_run(
        supervisor_run, scenario, supervisor_trace, YEAR
    )
    assert result.copy is None
