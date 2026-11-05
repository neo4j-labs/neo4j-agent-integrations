"""Load the structured and rule layers.

Creates the constraints and the payee full-text index, loads the rules from
``policy_facts.yaml``, then loads the CSVs in ``data/generated/`` and
``data/generated/fraud/`` with batched ``UNWIND ... MERGE``. No LLM is involved. Column formats are in
``data/README.md``.
"""

import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import neo4j
import yaml

from graphrag_banking.config import (
    GENERATED_DIR,
    POLICY_FACTS_PATH,
    Settings,
    get_driver,
    load_settings,
)
from graphrag_banking.tools import COUNTERPARTY_INDEX_NAME

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000

_FLOAT_COLUMNS = frozenset(
    {
        "amount",
        "ledger_balance",
        "available_balance",
        "approval_limit",
        "principal",
        "balance",
        "stated_annual_revenue",
        "percent",
    }
)
_DATE_COLUMNS = frozenset(
    {
        "available_on",
        "next_run_date",
        "opened_date",
        "customer_since",
        "registered_on",
        "first_seen",
        "closed_date",
    }
)
_DATETIME_COLUMNS = frozenset(
    {"initiated_at", "posted_at", "opened_at", "submitted_at"}
)

# Label -> key property, for the structured and rule layers.
_NODE_KEYS = {
    "Customer": "customer_id",
    "Account": "account_id",
    "Transaction": "transaction_id",
    "Counterparty": "counterparty_id",
    "ScheduledPayment": "payment_id",
    "ComplianceAlert": "alert_id",
    "AccountProduct": "product_code",
    "Policy": "policy_id",
    "FeeRule": "rule_code",
    "HoldRule": "rule_code",
    "ComplianceRule": "rule_code",
    "FraudRule": "rule_code",
    "LendingRule": "rule_code",
    "Banker": "banker_id",
    "FraudReviewer": "reviewer_id",
    "FraudReferral": "referral_id",
    "Person": "person_id",
    "Business": "business_id",
    "Phone": "number",
    "Email": "address",
    "Address": "address_id",
    "Device": "device_id",
    "Loan": "loan_id",
    "LoanApplication": "application_id",
}

# File -> label. The first column of each file is the label's key. Account,
# Transaction and Counterparty rows come from both directories.
_NODE_FILES = {
    "customers.csv": "Customer",
    "accounts.csv": "Account",
    "transactions.csv": "Transaction",
    "counterparties.csv": "Counterparty",
    "scheduled_payments.csv": "ScheduledPayment",
    "compliance_alerts.csv": "ComplianceAlert",
    "fraud/bankers.csv": "Banker",
    "fraud/fraud_reviewers.csv": "FraudReviewer",
    "fraud/persons.csv": "Person",
    "fraud/businesses.csv": "Business",
    "fraud/phones.csv": "Phone",
    "fraud/emails.csv": "Email",
    "fraud/addresses.csv": "Address",
    "fraud/devices.csv": "Device",
    "fraud/loans.csv": "Loan",
    "fraud/loan_applications.csv": "LoanApplication",
    "fraud/accounts.csv": "Account",
    "fraud/transactions.csv": "Transaction",
    "fraud/counterparties.csv": "Counterparty",
}

_RULE_SECTIONS = {
    "fee_rules": "FeeRule",
    "hold_rules": "HoldRule",
    "compliance_rules": "ComplianceRule",
    "fraud_rules": "FraudRule",
    "lending_rules": "LendingRule",
}
# Fields of a rule entry that become relationships, not properties.
_RULE_LINK_FIELDS = frozenset({"rule_code", "policy_id", "applies_to", "waived_for"})


@dataclass(frozen=True)
class _RelFile:
    """One relationship CSV. Columns not named here become properties."""

    file: str
    rel_type: str
    start_label: str
    start_column: str
    end_label: str
    end_column: str


_REL_FILES = [
    _RelFile(
        "rel_related_to.csv",
        "RELATED_TO",
        "Customer",
        "customer_id",
        "Customer",
        "related_customer_id",
    ),
    _RelFile(
        "rel_holds.csv", "HOLDS", "Customer", "customer_id", "Account", "account_id"
    ),
    _RelFile(
        "rel_is_product.csv",
        "IS_PRODUCT",
        "Account",
        "account_id",
        "AccountProduct",
        "product_code",
    ),
    _RelFile(
        "rel_has_transaction.csv",
        "HAS_TRANSACTION",
        "Account",
        "account_id",
        "Transaction",
        "transaction_id",
    ),
    _RelFile(
        "rel_initiated.csv",
        "INITIATED",
        "Customer",
        "customer_id",
        "Transaction",
        "transaction_id",
    ),
    _RelFile(
        "rel_paid_to.csv",
        "PAID_TO",
        "Transaction",
        "transaction_id",
        "Counterparty",
        "counterparty_id",
    ),
    _RelFile(
        "rel_received_from.csv",
        "RECEIVED_FROM",
        "Transaction",
        "transaction_id",
        "Counterparty",
        "counterparty_id",
    ),
    _RelFile(
        "rel_fee_for.csv",
        "FEE_FOR",
        "Transaction",
        "fee_transaction_id",
        "Transaction",
        "transaction_id",
    ),
    _RelFile(
        "rel_raised.csv",
        "RAISED",
        "Transaction",
        "transaction_id",
        "ComplianceAlert",
        "alert_id",
    ),
    _RelFile(
        "rel_under_rule.csv",
        "UNDER_RULE",
        "ComplianceAlert",
        "alert_id",
        "ComplianceRule",
        "rule_code",
    ),
    _RelFile(
        "rel_has_scheduled_payment.csv",
        "HAS_SCHEDULED_PAYMENT",
        "Account",
        "account_id",
        "ScheduledPayment",
        "payment_id",
    ),
    _RelFile(
        "rel_pays.csv",
        "PAYS",
        "ScheduledPayment",
        "payment_id",
        "Counterparty",
        "counterparty_id",
    ),
    # Loan fraud data
    _RelFile(
        "fraud/rel_manages_customer.csv",
        "MANAGES",
        "Banker",
        "banker_id",
        "Customer",
        "customer_id",
    ),
    _RelFile(
        "fraud/rel_manages_business.csv",
        "MANAGES",
        "Banker",
        "banker_id",
        "Business",
        "business_id",
    ),
    _RelFile(
        "fraud/rel_person_owns.csv",
        "OWNS",
        "Person",
        "person_id",
        "Business",
        "business_id",
    ),
    _RelFile(
        "fraud/rel_business_owns.csv",
        "OWNS",
        "Business",
        "owner_business_id",
        "Business",
        "business_id",
    ),
    _RelFile(
        "fraud/rel_director_of.csv",
        "DIRECTOR_OF",
        "Person",
        "person_id",
        "Business",
        "business_id",
    ),
    _RelFile(
        "fraud/rel_person_has_phone.csv",
        "HAS_PHONE",
        "Person",
        "person_id",
        "Phone",
        "number",
    ),
    _RelFile(
        "fraud/rel_business_has_phone.csv",
        "HAS_PHONE",
        "Business",
        "business_id",
        "Phone",
        "number",
    ),
    _RelFile(
        "fraud/rel_person_has_email.csv",
        "HAS_EMAIL",
        "Person",
        "person_id",
        "Email",
        "address",
    ),
    _RelFile(
        "fraud/rel_business_has_email.csv",
        "HAS_EMAIL",
        "Business",
        "business_id",
        "Email",
        "address",
    ),
    _RelFile(
        "fraud/rel_person_has_address.csv",
        "HAS_ADDRESS",
        "Person",
        "person_id",
        "Address",
        "address_id",
    ),
    _RelFile(
        "fraud/rel_business_has_address.csv",
        "HAS_ADDRESS",
        "Business",
        "business_id",
        "Address",
        "address_id",
    ),
    _RelFile(
        "fraud/rel_business_holds.csv",
        "HOLDS",
        "Business",
        "business_id",
        "Account",
        "account_id",
    ),
    _RelFile(
        "fraud/rel_applied_for.csv",
        "APPLIED_FOR",
        "Business",
        "business_id",
        "LoanApplication",
        "application_id",
    ),
    _RelFile(
        "fraud/rel_submitted_from.csv",
        "SUBMITTED_FROM",
        "LoanApplication",
        "application_id",
        "Device",
        "device_id",
    ),
    _RelFile(
        "fraud/rel_borrower_on.csv",
        "BORROWER_ON",
        "Business",
        "business_id",
        "Loan",
        "loan_id",
    ),
    _RelFile(
        "fraud/rel_has_transaction.csv",
        "HAS_TRANSACTION",
        "Account",
        "account_id",
        "Transaction",
        "transaction_id",
    ),
    _RelFile(
        "fraud/rel_paid_to.csv",
        "PAID_TO",
        "Transaction",
        "transaction_id",
        "Counterparty",
        "counterparty_id",
    ),
    _RelFile(
        "fraud/rel_received_from.csv",
        "RECEIVED_FROM",
        "Transaction",
        "transaction_id",
        "Counterparty",
        "counterparty_id",
    ),
    _RelFile(
        "fraud/rel_to_account.csv",
        "TO_ACCOUNT",
        "Transaction",
        "transaction_id",
        "Account",
        "account_id",
    ),
]


def _parse_cell(column: str, value: str) -> Any:
    if value == "":
        return None
    if column in _FLOAT_COLUMNS:
        return float(value)
    if column in _DATE_COLUMNS:
        return date.fromisoformat(value)
    if column in _DATETIME_COLUMNS:
        return datetime.fromisoformat(value)
    return value


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as file:
        return [
            {column: _parse_cell(column, value) for column, value in row.items()}
            for row in csv.DictReader(file)
        ]


def _write_batches(
    driver: neo4j.Driver, database: str, query: str, rows: list[dict[str, Any]]
) -> int:
    """Run ``query`` once per batch with ``$rows`` and sum its ``count`` column."""
    written = 0
    for start in range(0, len(rows), BATCH_SIZE):
        records, _, _ = driver.execute_query(
            query, rows=rows[start : start + BATCH_SIZE], database_=database
        )
        written += records[0]["count"]
    return written


def _create_schema(driver: neo4j.Driver, database: str) -> None:
    for label, key in _NODE_KEYS.items():
        name = f"{label.lower()}_{key}"
        driver.execute_query(
            f"CREATE CONSTRAINT {name} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE",
            database_=database,
        )
    driver.execute_query(
        f"CREATE FULLTEXT INDEX {COUNTERPARTY_INDEX_NAME} IF NOT EXISTS "
        "FOR (n:Counterparty) ON EACH [n.name]",
        database_=database,
    )
    logger.info("Created %d constraints and the payee index", len(_NODE_KEYS))


def _merge_nodes(
    driver: neo4j.Driver, database: str, label: str, rows: list[dict[str, Any]]
) -> int:
    key = _NODE_KEYS[label]
    query = (
        f"UNWIND $rows AS row MERGE (n:{label} {{{key}: row.{key}}}) "
        "SET n += row RETURN count(*) AS count"
    )
    return _write_batches(driver, database, query, rows)


def _merge_links(
    driver: neo4j.Driver,
    database: str,
    source: str,
    pattern: tuple[str, str, str],
    rows: list[dict[str, Any]],
) -> int:
    """Merge relationships between existing nodes.

    Args:
        driver: Open Neo4j driver.
        database: Neo4j database name.
        source: File the rows came from, for the error message.
        pattern: Start label, relationship type, and end label.
        rows: Each row has ``start`` and ``end`` keys and a ``props`` map.

    Raises:
        ValueError: If a row names a node that does not exist.
    """
    start_label, rel_type, end_label = pattern
    query = (
        "UNWIND $rows AS row "
        f"MATCH (a:{start_label} {{{_NODE_KEYS[start_label]}: row.start}}) "
        f"MATCH (b:{end_label} {{{_NODE_KEYS[end_label]}: row.end}}) "
        f"MERGE (a)-[r:{rel_type}]->(b) SET r += row.props "
        "RETURN count(*) AS count"
    )
    written = _write_batches(driver, database, query, rows)
    if written != len(rows):
        raise ValueError(
            f"{source}: {len(rows) - written} of {len(rows)} {rel_type} rows "
            f"reference a missing {start_label} or {end_label}"
        )
    return written


def _load_rules(driver: neo4j.Driver, database: str) -> None:
    facts = yaml.safe_load(POLICY_FACTS_PATH.read_text(encoding="utf-8"))

    _merge_nodes(driver, database, "AccountProduct", facts["products"])
    policies = [
        {
            "policy_id": policy["policy_id"],
            "name": policy["name"],
            "effective_date": date.fromisoformat(str(policy["effective_date"])),
        }
        for policy in facts["policies"]
    ]
    _merge_nodes(driver, database, "Policy", policies)

    for section, label in _RULE_SECTIONS.items():
        rules = facts[section]
        properties = [
            {k: v for k, v in rule.items() if k not in _RULE_LINK_FIELDS}
            | {"rule_code": rule["rule_code"]}
            for rule in rules
        ]
        _merge_nodes(driver, database, label, properties)
        _merge_links(
            driver,
            database,
            POLICY_FACTS_PATH.name,
            ("Policy", "DEFINES", label),
            [
                {"start": r["policy_id"], "end": r["rule_code"], "props": {}}
                for r in rules
            ],
        )
        logger.info("Loaded %d %s nodes", len(rules), label)

    for field, rel_type in (("applies_to", "APPLIES_TO"), ("waived_for", "WAIVED_FOR")):
        rows = [
            {"start": rule["rule_code"], "end": code, "props": {}}
            for rule in facts["fee_rules"]
            for code in rule.get(field, [])
        ]
        _merge_links(
            driver,
            database,
            POLICY_FACTS_PATH.name,
            ("FeeRule", rel_type, "AccountProduct"),
            rows,
        )


def _load_csvs(driver: neo4j.Driver, database: str) -> None:
    for file, label in _NODE_FILES.items():
        count = _merge_nodes(driver, database, label, _read_csv(GENERATED_DIR / file))
        logger.info("Loaded %d %s nodes", count, label)

    for rel in _REL_FILES:
        rows = [
            {
                "start": row.pop(rel.start_column),
                "end": row.pop(rel.end_column),
                "props": row,
            }
            for row in _read_csv(GENERATED_DIR / rel.file)
        ]
        pattern = (rel.start_label, rel.rel_type, rel.end_label)
        count = _merge_links(driver, database, rel.file, pattern, rows)
        logger.info("Loaded %d %s relationships", count, rel.rel_type)


def load_structured(settings: Settings) -> None:
    """Create the schema, then load the rule layer and the structured layer."""
    database = settings.neo4j_database
    with get_driver(settings) as driver:
        _create_schema(driver, database)
        # Rules first: rel_is_product.csv and rel_under_rule.csv point at them.
        _load_rules(driver, database)
        _load_csvs(driver, database)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_structured(load_settings())
