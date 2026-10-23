"""Load policy_facts.yaml and hero_fixtures.yaml, shared by the Phase 1 scripts."""

from datetime import date
from decimal import Decimal
from typing import Any

import yaml

from graphrag_banking.config import HERO_FIXTURES_PATH, POLICY_FACTS_PATH

RULE_SECTIONS = (
    "fee_rules",
    "hold_rules",
    "compliance_rules",
    "fraud_rules",
    "lending_rules",
)
CREDIT_TYPES = frozenset({"WIRE_IN", "ACH_IN", "CHECK_DEPOSIT"})
DEBIT_TYPES = frozenset({"WIRE_OUT", "ACH_OUT", "CARD", "FEE", "TRANSFER"})


def load_policy_facts() -> dict[str, Any]:
    with POLICY_FACTS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_hero_fixtures() -> dict[str, Any]:
    with HERO_FIXTURES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def all_rules(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Every fee, hold, compliance, fraud and lending rule, in file order."""
    return [rule for section in RULE_SECTIONS for rule in facts[section]]


def fee_rules_by_code(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {rule["rule_code"]: rule for rule in facts["fee_rules"]}


def to_decimal(value: float | str) -> Decimal:
    """Convert a YAML or CSV amount to an exact two-place Decimal."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def format_money(value: float | str) -> str:
    """$3,000 for whole dollars, $1,137.42 otherwise."""
    amount = to_decimal(value)
    if amount == amount.to_integral_value():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def format_date(value: date) -> str:
    """January 1, 2026."""
    return f"{value:%B} {value.day}, {value.year}"


def placeholder_key(code: str, field: str) -> str:
    """("FEE-WIRE-RETURN", "amount") -> "fee_wire_return_amount"."""
    return f"{code.lower().replace('-', '_')}_{field}"
