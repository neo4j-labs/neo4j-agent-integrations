"""Unit tests for ingestion and agent helpers. None need a database or API key."""

import asyncio
from datetime import UTC, date, datetime

import pytest
from neo4j.time import Date, DateTime

from graphrag_banking import tools
from graphrag_banking.agent import _bind, load_instructions
from graphrag_banking.build_policy_graph import HeadingSplitter
from graphrag_banking.load_structured import _parse_cell

POLICY = """# Fee Schedule

## Outgoing wires
A $30 fee applies.
Rule code: FEE-WIRE-OUT

## Overdraft
Rule code: FEE-OVERDRAFT
Rule code: FEE-ODP-TRANSFER

## General
No codes here.
"""


def _chunks(text: str) -> list:
    return asyncio.run(HeadingSplitter().run(text)).chunks


def test_splitter_one_chunk_per_section_with_heading() -> None:
    chunks = _chunks(POLICY)
    assert [c.text.splitlines()[0] for c in chunks] == [
        "## Outgoing wires",
        "## Overdraft",
        "## General",
    ]
    assert [c.index for c in chunks] == [0, 1, 2]


def test_splitter_collects_rule_codes() -> None:
    codes = [c.metadata["rule_codes"] for c in _chunks(POLICY)]
    assert codes == [["FEE-WIRE-OUT"], ["FEE-OVERDRAFT", "FEE-ODP-TRANSFER"], []]


def test_splitter_keeps_preamble_only_with_body_text() -> None:
    chunks = _chunks("# Title\nIntro.\n## A\nx")
    assert [c.text for c in chunks] == ["# Title\nIntro.", "## A\nx"]


def test_splitter_ignores_inline_rule_code_mentions() -> None:
    chunks = _chunks("# T\n## A\nSee Rule code: X in text.\nRule code: Y")
    assert chunks[0].metadata["rule_codes"] == ["Y"]


def test_parse_cell_types() -> None:
    assert _parse_cell("amount", "5000.00") == 5000.0
    assert _parse_cell("available_on", "2026-10-09") == date(2026, 10, 9)
    assert _parse_cell("initiated_at", "2026-10-07T15:42:00Z") == datetime(
        2026, 10, 7, 15, 42, tzinfo=UTC
    )
    assert _parse_cell("posted_at", "") is None
    assert _parse_cell("name", "Acme Corp") == "Acme Corp"


def test_plain_converts_neo4j_temporals() -> None:
    value = {"d": Date(2026, 10, 9), "rows": [DateTime(2026, 10, 7, 15, 42, 0)]}
    assert tools._plain(value) == {
        "d": "2026-10-09",
        "rows": ["2026-10-07T15:42:00.000000000"],
    }


def test_project_balances_counts_deposits_available_by_run_date() -> None:
    result = {
        "available_balance": 1800.0,
        "pending_deposits": [
            {"amount": 2000.0, "available_on": "2026-10-09"},
            {"amount": 500.0, "available_on": "2026-10-20"},
        ],
        "payments": [
            {"amount": 3200.0, "next_run_date": "2026-10-13"},
            {"amount": 1000.0, "next_run_date": "2026-10-21"},
        ],
    }
    tools._project_balances(result)
    first, second = result["payments"]
    assert (first["available_before_payment"], first["covered"]) == (3800.0, True)
    assert (second["available_before_payment"], second["covered"]) == (1100.0, True)


def test_project_balances_not_covered_when_deposit_is_late() -> None:
    result = {
        "available_balance": 1800.0,
        "pending_deposits": [{"amount": 2000.0, "available_on": "2026-10-14"}],
        "payments": [{"amount": 3200.0, "next_run_date": "2026-10-13"}],
    }
    tools._project_balances(result)
    assert result["payments"][0]["covered"] is False


def test_find_my_transactions_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="Unknown transaction type"):
        tools.find_my_transactions(None, type="BOGUS")


def test_find_my_transactions_rejects_bad_date() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        tools.find_my_transactions(None, date_from="October 7")


def test_bind_hides_context_and_records_errors() -> None:
    context = tools.ToolContext(
        driver=None,
        database="neo4j",
        customer_id="C-1001",
        embedding_config={},
        as_of=date(2026, 10, 8),
    )
    calls = []
    tool = _bind(tools.find_my_transactions, context, calls.append)
    schema = tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"payee", "type", "date_from", "date_to"}
    assert "customer_id" not in str(schema)

    result = tool.invoke({"type": "BOGUS"})
    assert result == {"error": "Unknown transaction type 'BOGUS'"}
    assert calls == [
        {
            "name": "find_my_transactions",
            "args": {
                "payee": None,
                "type": "BOGUS",
                "date_from": None,
                "date_to": None,
            },
            "result": result,
            "cypher": [],
        }
    ]


def test_load_instructions_fills_date() -> None:
    text = load_instructions(date(2026, 10, 8))
    assert "Thursday, October 8, 2026" in text
    assert "2026-10-08" in text
