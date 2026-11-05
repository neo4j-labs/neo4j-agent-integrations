"""Check the generated loan fraud CSVs against the hero fixtures and the rules.

Called from ``validate-data``. The checks follow the "New checks in
validate-data" list in the loan fraud proposal: structure and references, the
ring's ownership, loop, phone and device, reviewers, book coverage, registered
agent volume, and no protected attributes. Rule coverage in the policy
documents is checked by ``check_policies``.
"""

import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from graphrag_banking.config import GENERATED_DIR
from graphrag_banking.facts import CREDIT_TYPES, load_hero_fixtures, to_decimal
from graphrag_banking.generate_data import CSV_COLUMNS
from graphrag_banking.generate_fraud import (
    APPLICATION_STATUS_WEIGHTS,
    FRAUD_CSV_COLUMNS,
    FRAUD_DIR,
    LOAN_STATUS_WEIGHTS,
    LOAN_TYPES,
)
from graphrag_banking.load_structured import _NODE_FILES, _NODE_KEYS, _REL_FILES
from graphrag_banking.validate_data import (
    CONTROLLED,
    Checker,
    _is_amount,
    _is_date,
    _is_utc_datetime,
)

CONTROLLED_FRAUD = {
    ("bankers", "role"): {"RELATIONSHIP_MANAGER"},
    ("addresses", "kind"): {"HOME", "OFFICE", "REGISTERED_AGENT", "COWORKING"},
    ("loans", "type"): set(LOAN_TYPES),
    ("loans", "status"): set(LOAN_STATUS_WEIGHTS),
    ("loan_applications", "type"): set(LOAN_TYPES),
    ("loan_applications", "status"): set(APPLICATION_STATUS_WEIGHTS),
    ("rel_business_holds", "role"): {"PRIMARY"},
    ("transactions", "type"): CONTROLLED[("transactions", "type")],
    ("transactions", "status"): CONTROLLED[("transactions", "status")],
    ("accounts", "status"): CONTROLLED[("accounts", "status")],
}
DATETIME_COLUMNS = {"initiated_at", "posted_at", "submitted_at"}
DATE_COLUMNS = {
    "available_on",
    "opened_date",
    "closed_date",
    "registered_on",
    "first_seen",
}
AMOUNT_COLUMNS = {
    "amount",
    "ledger_balance",
    "available_balance",
    "approval_limit",
    "principal",
    "balance",
    "stated_annual_revenue",
}
POSITIVE_AMOUNT_COLUMNS = {"amount", "principal", "stated_annual_revenue"}
PROTECTED_COLUMNS = {
    "age",
    "date_of_birth",
    "dob",
    "sex",
    "gender",
    "race",
    "ethnicity",
    "religion",
    "national_origin",
    "nationality",
    "citizenship",
    "marital_status",
}

RING_PHONE = "+1-555-0610"
RING_DEVICE = "DEV-1001"
RING_APPLICANTS = {"B-1002", "B-1004", "B-1005", "B-1006"}
DEVICE_SHARERS = {"APP-1001", "APP-1002", "APP-1003"}
RING_ACCOUNTS = {"A-3001", "A-3002", "A-3003", "A-3004"}
HERO_OWNER, HERO_APPLICANT = "P-1001", "B-1002"
EXPECTED_OWNERSHIP = Decimal(56)
ORTEGA_ACCOUNT = "A-3001"
EXPECTED_LOOP_INFLOW = Decimal("455000.00")
MIN_REGISTERED_AGENT_BUSINESSES = 200


def _read(path) -> list[dict[str, str | None]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {k: (v if v != "" else None) for k, v in row.items()}
            for row in csv.DictReader(f)
        ]


def read_fraud_csvs() -> dict[str, list[dict[str, str | None]]]:
    return {name: _read(FRAUD_DIR / f"{name}.csv") for name in FRAUD_CSV_COLUMNS}


def check_fraud(
    c: Checker, t: dict[str, list[dict]], facts: dict[str, Any], as_of: date
) -> None:
    """Run every fraud check. ``t`` holds the fraud tables by file name."""
    check_fraud_structure(c, t)
    check_ring(c, t, facts, as_of)
    check_background(c, t)
    check_no_protected_columns(c, t)


def check_fraud_structure(c: Checker, t: dict[str, list[dict]]) -> None:
    for name, columns in FRAUD_CSV_COLUMNS.items():
        header = list(t[name][0]) if t[name] else columns
        c.check(header == columns, f"fraud/{name}.csv columns {header} != {columns}")

    # Keys by label across both directories, so Account, Transaction and
    # Counterparty keys must not collide between the customer and fraud data.
    keys: dict[str, list[str]] = defaultdict(list)
    for file, label in _NODE_FILES.items():
        rows = (
            t[file.removeprefix("fraud/").removesuffix(".csv")]
            if file.startswith("fraud/")
            else _read(GENERATED_DIR / file)
        )
        keys[label] += [row[_NODE_KEYS[label]] for row in rows]
    for label, values in keys.items():
        dupes = [v for v, n in Counter(values).items() if n > 1]
        c.check(not dupes, f"{label} duplicate keys: {dupes[:5]}")
        c.check(all(values), f"{label} has an empty key")
    key_sets = {label: set(values) for label, values in keys.items()}

    for rel in _REL_FILES:
        if not rel.file.startswith("fraud/"):
            continue
        rows = t[rel.file.removeprefix("fraud/").removesuffix(".csv")]
        for column, label in (
            (rel.start_column, rel.start_label),
            (rel.end_column, rel.end_label),
        ):
            missing = {row[column] for row in rows} - key_sets[label]
            c.check(
                not missing,
                f"{rel.file} {column} references missing: {sorted(missing)[:5]}",
            )

    for (name, column), allowed in CONTROLLED_FRAUD.items():
        bad = {row[column] for row in t[name]} - allowed
        c.check(not bad, f"fraud/{name}.csv {column} has uncontrolled values {bad}")

    for name, rows in t.items():
        for row in rows:
            for column, value in row.items():
                if value is None:
                    continue
                if column in DATETIME_COLUMNS:
                    c.check(
                        _is_utc_datetime(value),
                        f"fraud/{name}.{column} bad datetime {value}",
                    )
                elif column in DATE_COLUMNS:
                    c.check(_is_date(value), f"fraud/{name}.{column} bad date {value}")
                elif column in AMOUNT_COLUMNS:
                    c.check(
                        _is_amount(value, column in POSITIVE_AMOUNT_COLUMNS),
                        f"fraud/{name}.{column} bad amount {value}",
                    )

    per_txn = Counter(r["transaction_id"] for r in t["rel_has_transaction"])
    c.check(
        set(per_txn) == key_sets["Transaction"] - _customer_keys("transactions")
        and set(per_txn.values()) == {1},
        "every fraud transaction must belong to exactly one account",
    )
    holders = Counter(r["account_id"] for r in t["rel_business_holds"])
    c.check(
        set(holders) == {r["account_id"] for r in t["accounts"]}
        and set(holders.values()) == {1},
        "every fraud account must have exactly one business holder",
    )
    c.check(len(t["fraud_reviewers"]) >= 1, "at least one fraud reviewer must exist")

    customers = {row["customer_id"] for row in _read(GENERATED_DIR / "customers.csv")}
    for name, column, expected in (
        ("rel_manages_customer", "customer_id", customers),
        ("rel_manages_business", "business_id", key_sets["Business"]),
    ):
        per = Counter(r[column] for r in t[name])
        c.check(
            set(per) == expected and set(per.values()) == {1},
            f"every {column} must have exactly one banker in {name}.csv",
        )


def check_ring(
    c: Checker, t: dict[str, list[dict]], facts: dict[str, Any], as_of: date
) -> None:
    rules = {r["rule_code"]: r for r in facts["fraud_rules"] + facts["lending_rules"]}

    share = _effective_share(t, HERO_OWNER, HERO_APPLICANT)
    c.check(
        share == EXPECTED_OWNERSHIP,
        f"{HERO_OWNER} effective share of {HERO_APPLICANT} is {share}, "
        f"expected {EXPECTED_OWNERSHIP}",
    )
    c.check(
        share >= Decimal(rules["KYC-UBO-25"]["percent"]),
        f"{HERO_OWNER} must be a beneficial owner of {HERO_APPLICANT}",
    )

    loans = {r["loan_id"]: r for r in t["loans"]}
    lookback = as_of.replace(year=as_of.year - rules["FRAUD-PRIOR-LOSS"]["years"])
    prior_losses = [
        r["loan_id"]
        for r in t["rel_borrower_on"]
        if loans[r["loan_id"]]["status"] == "WRITTEN_OFF"
        and date.fromisoformat(loans[r["loan_id"]]["closed_date"]) >= lookback
        and _effective_share(t, HERO_OWNER, r["business_id"]) > 0
    ]
    c.check(
        prior_losses == ["L-1001"],
        f"{HERO_OWNER} prior losses are {prior_losses}, expected ['L-1001']",
    )

    window_start = as_of - timedelta(days=rules["FRAUD-CIRCULAR-FLOW"]["lookback_days"])
    txns = {r["transaction_id"]: r for r in t["transactions"]}
    account_of = {
        r["transaction_id"]: r["account_id"] for r in t["rel_has_transaction"]
    }
    loop_inflow = sum(
        (
            to_decimal(txns[r["transaction_id"]]["amount"])
            for r in t["rel_to_account"]
            if r["account_id"] == ORTEGA_ACCOUNT
            and account_of[r["transaction_id"]] in RING_ACCOUNTS
            and _day(txns[r["transaction_id"]]["initiated_at"]) >= window_start
        ),
        Decimal(0),
    )
    c.check(
        loop_inflow == EXPECTED_LOOP_INFLOW,
        f"loop inflow to {ORTEGA_ACCOUNT} is {loop_inflow}, "
        f"expected {EXPECTED_LOOP_INFLOW}",
    )

    phone_sharers = {
        r["business_id"]
        for r in t["rel_business_has_phone"]
        if r["number"] == RING_PHONE
    }
    c.check(
        phone_sharers == RING_APPLICANTS,
        f"businesses on {RING_PHONE} are {sorted(phone_sharers)}",
    )
    device_sharers = {
        r["application_id"]
        for r in t["rel_submitted_from"]
        if r["device_id"] == RING_DEVICE
    }
    c.check(
        device_sharers == DEVICE_SHARERS,
        f"applications from {RING_DEVICE} are {sorted(device_sharers)}",
    )

    limit = to_decimal(rules["AUTH-RM-LIMIT"]["amount"])
    bad_limits = [
        r["banker_id"] for r in t["bankers"] if to_decimal(r["approval_limit"]) != limit
    ]
    c.check(not bad_limits, f"bankers with a limit other than {limit}: {bad_limits}")

    opening = _hero_opening()
    ledger = _ledger_change(t)
    for account in t["accounts"]:
        account_id = account["account_id"]
        if account_id not in opening:
            continue
        expected = opening[account_id] + ledger[account_id]
        c.check(
            to_decimal(account["ledger_balance"]) == expected,
            f"{account_id}: ledger {account['ledger_balance']} != {expected}",
        )


def check_background(c: Checker, t: dict[str, list[dict]]) -> None:
    kind = {r["address_id"]: r["kind"] for r in t["addresses"]}
    registered = {
        r["business_id"]
        for r in t["rel_business_has_address"]
        if kind[r["address_id"]] == "REGISTERED_AGENT"
    }
    c.check(
        len(registered) > MIN_REGISTERED_AGENT_BUSINESSES,
        f"{len(registered)} businesses list a registered agent address, "
        f"expected more than {MIN_REGISTERED_AGENT_BUSINESSES}",
    )

    # Money loops must exist only among the ring accounts.
    account_of = {
        r["transaction_id"]: r["account_id"] for r in t["rel_has_transaction"]
    }
    edges: dict[str, set[str]] = defaultdict(set)
    for r in t["rel_to_account"]:
        edges[account_of[r["transaction_id"]]].add(r["account_id"])
    looped = {a for a in edges if _reaches(edges, a, a)}
    c.check(
        looped <= RING_ACCOUNTS,
        f"money loops outside the ring: {sorted(looped - RING_ACCOUNTS)[:5]}",
    )


def check_no_protected_columns(c: Checker, t: dict[str, list[dict]]) -> None:
    columns = {
        (f"fraud/{name}", column)
        for name, columns in FRAUD_CSV_COLUMNS.items()
        for column in columns
    } | {(name, column) for name, columns in CSV_COLUMNS.items() for column in columns}
    bad = sorted(f"{name}.{col}" for name, col in columns if col in PROTECTED_COLUMNS)
    c.check(not bad, f"protected attribute columns: {bad}")


def _customer_keys(name: str) -> set[str]:
    key = next(
        _NODE_KEYS[label]
        for file, label in _NODE_FILES.items()
        if file == f"{name}.csv"
    )
    return {row[key] for row in _read(GENERATED_DIR / f"{name}.csv")}


def _effective_share(t: dict[str, list[dict]], person_id: str, business_id: str):
    """Sum over ownership chains of the product of the percents along each chain."""
    owned_by: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    for r in t["rel_person_owns"]:
        owned_by[r["person_id"]].append((r["business_id"], Decimal(r["percent"])))
    for r in t["rel_business_owns"]:
        owned_by[r["owner_business_id"]].append(
            (r["business_id"], Decimal(r["percent"]))
        )

    def share(owner: str) -> Decimal:
        total = Decimal(0)
        for owned, percent in owned_by[owner]:
            if owned == business_id:
                total += percent
            else:
                total += percent * share(owned) / 100
        return total

    return share(person_id)


def _ledger_change(t: dict[str, list[dict]]) -> dict[str, Decimal]:
    """Net change per account. A transfer also credits the account it points to."""
    account_of = {
        r["transaction_id"]: r["account_id"] for r in t["rel_has_transaction"]
    }
    to_account = {r["transaction_id"]: r["account_id"] for r in t["rel_to_account"]}
    net: dict[str, Decimal] = defaultdict(Decimal)
    for txn in t["transactions"]:
        amount = to_decimal(txn["amount"])
        txn_id = txn["transaction_id"]
        net[account_of[txn_id]] += amount if txn["type"] in CREDIT_TYPES else -amount
        if txn_id in to_account:
            net[to_account[txn_id]] += amount
    return net


def _hero_opening() -> dict[str, Decimal]:
    return {
        a["account_id"]: to_decimal(a["opening_balance"])
        for a in load_hero_fixtures()["fraud"]["accounts"]
    }


def _reaches(edges: dict[str, set[str]], start: str, target: str) -> bool:
    seen: set[str] = set()
    stack = list(edges[start])
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(edges.get(node, ()))
    return False


def _day(value: str) -> date:
    return date.fromisoformat(value[:10])
