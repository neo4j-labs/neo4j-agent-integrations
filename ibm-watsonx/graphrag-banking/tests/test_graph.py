"""Phase 2 exit checks against the live graph (PRD section 8, Phase 2).

Checks node counts, that every rule links to a chunk, and the hero traversals
in PRD section 4. Skipped until ``make rebuild`` has built the graph.
"""

import csv
from collections.abc import Iterator
from typing import Any

import neo4j
import pytest
import yaml

from graphrag_banking.config import (
    GENERATED_DIR,
    POLICY_FACTS_PATH,
    Settings,
    get_driver,
    load_settings,
)
from graphrag_banking.load_structured import _NODE_FILES
from graphrag_banking.tools import (
    COUNTERPARTY_INDEX_NAME,
    VECTOR_INDEX_NAME,
    ToolContext,
    get_scheduled_payments,
)


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
            "MATCH (c:Chunk) RETURN count(c) AS n", database_=settings.neo4j_database
        )
        if records[0]["n"] == 0:
            pytest.skip("The graph is not built. Run make rebuild.")
        yield driver


@pytest.fixture(scope="module")
def query(driver: neo4j.Driver, settings: Settings):
    def run(cypher: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = driver.execute_query(
            cypher, database_=settings.neo4j_database, **params
        )
        return [record.data() for record in records]

    return run


@pytest.fixture(scope="module")
def facts() -> dict[str, Any]:
    return yaml.safe_load(POLICY_FACTS_PATH.read_text(encoding="utf-8"))


def _count(query, label: str) -> int:
    return query(f"MATCH (n:{label}) RETURN count(n) AS n")[0]["n"]


# Node counts


@pytest.mark.parametrize(("file", "label"), _NODE_FILES.items())
def test_structured_counts_match_csvs(query, file: str, label: str) -> None:
    with (GENERATED_DIR / file).open(newline="", encoding="utf-8") as handle:
        rows = sum(1 for _ in csv.DictReader(handle))
    assert _count(query, label) == rows


def test_rule_layer_counts_match_policy_facts(query, facts) -> None:
    assert _count(query, "AccountProduct") == len(facts["products"])
    assert _count(query, "Policy") == len(facts["policies"])
    assert _count(query, "FeeRule") == len(facts["fee_rules"])
    assert _count(query, "HoldRule") == len(facts["hold_rules"])
    assert _count(query, "ComplianceRule") == len(facts["compliance_rules"])


def test_one_document_per_policy(query, facts) -> None:
    rows = query("MATCH (d:Document) RETURN d.policy_id AS policy_id")
    assert sorted(r["policy_id"] for r in rows) == sorted(
        p["policy_id"] for p in facts["policies"]
    )


def test_every_chunk_has_embedding_and_document(query) -> None:
    rows = query(
        """
        MATCH (c:Chunk)
        WHERE c.embedding IS NULL OR NOT (c)-[:FROM_DOCUMENT]->(:Document)
        RETURN count(c) AS n
        """
    )
    assert rows[0]["n"] == 0


def test_indexes_online(query) -> None:
    rows = query(
        "SHOW INDEXES YIELD name, state WHERE name IN $names RETURN name, state",
        names=[VECTOR_INDEX_NAME, COUNTERPARTY_INDEX_NAME],
    )
    assert {r["name"]: r["state"] for r in rows} == {
        VECTOR_INDEX_NAME: "ONLINE",
        COUNTERPARTY_INDEX_NAME: "ONLINE",
    }


# Rule links


def test_every_rule_links_to_a_chunk(query) -> None:
    rows = query(
        """
        MATCH (r) WHERE (r:FeeRule OR r:HoldRule OR r:ComplianceRule)
          AND NOT (r)-[:FROM_CHUNK]->(:Chunk)
        RETURN r.rule_code AS rule_code
        """
    )
    assert rows == []


def test_every_rule_code_tag_matches_a_rule(query) -> None:
    rows = query(
        """
        MATCH (c:Chunk) UNWIND c.rule_codes AS code
        WITH DISTINCT code
        WHERE NOT EXISTS {
          MATCH (r {rule_code: code})
          WHERE r:FeeRule OR r:HoldRule OR r:ComplianceRule
        }
        RETURN code
        """
    )
    assert rows == []


# Hero traversals, PRD section 4


def test_scenario_a_wire_held_with_alert_and_waived_fees(query) -> None:
    rows = query(
        """
        MATCH (:Customer {customer_id: 'C-1001'})-[:HOLDS]->(a:Account)
              -[:HAS_TRANSACTION]->(t:Transaction {type: 'WIRE_OUT'})
              -[:PAID_TO]->(:Counterparty {name: 'Acme Corp'})
        MATCH (t)-[:RAISED]->(:ComplianceAlert)-[:UNDER_RULE]->
              (cr:ComplianceRule)-[:FROM_CHUNK]->(:Chunk)
        MATCH (a)-[:IS_PRODUCT]->(p:AccountProduct {name: 'Premium Checking'})
        RETURN a.account_id AS account, t.transaction_id AS transaction,
               t.status AS status, t.amount AS amount,
               date(t.initiated_at) AS initiated_on, cr.rule_code AS alert_rule,
               COLLECT {
                 MATCH (f:FeeRule)-[:WAIVED_FOR]->(p)
                 WHERE 'WIRE_OUT' IN f.transaction_types
                   AND (f)-[:FROM_CHUNK]->(:Chunk)
                 RETURN f.rule_code ORDER BY f.rule_code
               } AS waived_fees
        """
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["account"] == "A-1001"
    assert row["transaction"] == "T-1022"
    assert row["status"] == "HELD"
    assert row["amount"] == 5000.0
    assert row["initiated_on"].iso_format() == "2026-10-07"
    assert row["alert_rule"] == "WIRE-REVIEW-01"
    assert row["waived_fees"] == ["FEE-WIRE-OUT", "FEE-WIRE-RETURN"]


def test_scenario_b_joint_deposit_and_mortgage(query) -> None:
    rows = query(
        """
        MATCH (m:Customer {customer_id: 'C-1001'})-[:RELATED_TO {type: 'SPOUSE'}]-
              (s:Customer {name: 'Sarah Okafor'})
        MATCH (m)-[:HOLDS {role: 'JOINT'}]->(a:Account)<-[:HOLDS]-(s)
        MATCH (s)-[:INITIATED]->(t:Transaction {type: 'CHECK_DEPOSIT'})
              <-[:HAS_TRANSACTION]-(a)
        MATCH (a)-[:HAS_SCHEDULED_PAYMENT]->(sp:ScheduledPayment)
              -[:PAYS]->(cp:Counterparty {name: 'Lakeside Home Loans'})
        MATCH (hr:HoldRule {rule_code: 'HOLD-CHECK-NBD'})-[:FROM_CHUNK]->(:Chunk)
        WHERE t.type IN hr.transaction_types
        RETURN s.customer_id AS sarah, a.account_id AS account,
               a.available_balance AS available, t.transaction_id AS deposit,
               t.status AS status, t.amount AS amount,
               t.available_on AS available_on, sp.payment_id AS payment,
               sp.amount AS payment_amount, sp.next_run_date AS run_date,
               cp.name AS payee
        """
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["sarah"] == "C-1002"
    assert row["account"] == "A-1002"
    assert row["available"] == 1800.0
    assert (row["deposit"], row["status"], row["amount"]) == (
        "T-1123",
        "PENDING",
        2000.0,
    )
    assert row["available_on"].iso_format() == "2026-10-09"
    assert (row["payment"], row["payment_amount"]) == ("SP-1001", 3200.0)
    assert row["run_date"].iso_format() == "2026-10-13"
    assert row["payee"] == "Lakeside Home Loans"


def test_scenario_b_pending_deposit_carries_hold_rule(
    driver: neo4j.Driver, settings: Settings
) -> None:
    context = ToolContext(
        driver=driver,
        database=settings.neo4j_database,
        customer_id="C-1001",
        embedding_config=settings.embedding_config,
        as_of=settings.demo_as_of,
    )
    result = get_scheduled_payments(context, "A-1002")
    deposit = next(
        d for d in result["pending_deposits"] if d["transaction_id"] == "T-1123"
    )
    rules = {rule["rule_code"]: rule for rule in deposit["hold_rules"]}
    assert "HOLD-CHECK-NBD" in rules
    assert rules["HOLD-CHECK-NBD"]["policy"]
    assert rules["HOLD-CHECK-NBD"]["policy_text"]


def test_scenario_c_joint_account_overdraft_terms(query) -> None:
    rows = query(
        """
        MATCH (:Customer {customer_id: 'C-1001'})-[:HOLDS]->
              (:Account {account_id: 'A-1002'})-[:IS_PRODUCT]->(p:AccountProduct)
        MATCH (f:FeeRule)-[:APPLIES_TO]->(p)
        WHERE f.rule_code IN ['FEE-OVERDRAFT', 'FEE-ODP-TRANSFER']
          AND NOT (f)-[:WAIVED_FOR]->(p)
          AND (f)-[:FROM_CHUNK]->(:Chunk)
        RETURN p.name AS product, f.rule_code AS rule_code, f.amount AS amount,
               f.threshold AS threshold
        ORDER BY rule_code
        """
    )
    assert [r["product"] for r in rows] == ["Standard Checking"] * 2
    assert [(r["rule_code"], r["amount"]) for r in rows] == [
        ("FEE-ODP-TRANSFER", 10.0),
        ("FEE-OVERDRAFT", 29.0),
    ]
    assert rows[1]["threshold"] == 50.0


def test_scenario_d_sarahs_savings_not_held_by_marcus(query) -> None:
    rows = query(
        """
        MATCH (a:Account {account_id: 'A-2001'})
        RETURN [(c:Customer)-[:HOLDS]->(a) | c.customer_id] AS holders,
               a.available_balance AS balance
        """
    )
    assert rows == [{"holders": ["C-1002"], "balance": 18250.0}]
