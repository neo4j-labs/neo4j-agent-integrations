"""Check the generated CSVs and rendered policies against the facts and fixtures.

Prints every failed check and exits non-zero if any check fails. The checks
cover referential integrity and controlled values, hero balances, the hero
scenario facts, no conflicting background records, and
policy documents that agree with policy_facts.yaml.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from graphrag_banking.config import GENERATED_DIR, POLICIES_DIR, load_settings
from graphrag_banking.facts import (
    CREDIT_TYPES,
    all_rules,
    load_hero_fixtures,
    load_policy_facts,
    to_decimal,
)
from graphrag_banking.generate_data import CSV_COLUMNS
from graphrag_banking.render_policies import placeholder_values, render_policy

NODE_KEYS = {
    "customers": "customer_id",
    "accounts": "account_id",
    "transactions": "transaction_id",
    "counterparties": "counterparty_id",
    "scheduled_payments": "payment_id",
    "compliance_alerts": "alert_id",
}
CONTROLLED = {
    ("transactions", "type"): {
        "WIRE_OUT",
        "WIRE_IN",
        "ACH_OUT",
        "ACH_IN",
        "CHECK_DEPOSIT",
        "CARD",
        "FEE",
        "TRANSFER",
    },
    ("transactions", "status"): {
        "POSTED",
        "PENDING",
        "HELD",
        "FAILED",
        "RETURNED",
        "REVERSED",
    },
    ("transactions", "channel"): {
        "ONLINE",
        "MOBILE",
        "BRANCH",
        "ACH",
        "CARD",
        "SYSTEM",
    },
    ("transactions", "currency"): {"USD"},
    ("accounts", "currency"): {"USD"},
    ("accounts", "status"): {"OPEN", "FROZEN", "CLOSED"},
    ("counterparties", "kind"): {"MERCHANT", "BUSINESS", "INDIVIDUAL", "LENDER"},
    ("customers", "segment"): {"RETAIL", "PREMIER"},
    ("customers", "risk_rating"): {"LOW", "MEDIUM", "HIGH"},
    ("customers", "kyc_status"): {"VERIFIED", "PENDING", "EXPIRED"},
    ("rel_holds", "role"): {"PRIMARY", "JOINT"},
    ("rel_related_to", "type"): {"SPOUSE"},
    ("scheduled_payments", "frequency"): {"WEEKLY", "BIWEEKLY", "MONTHLY"},
    ("scheduled_payments", "status"): {"ACTIVE", "PAUSED"},
    ("compliance_alerts", "status"): {"OPEN", "CLEARED", "ESCALATED"},
}
# (file, column) -> node file whose key it references. None means a rule-layer key.
REFERENCES = {
    "rel_related_to": [
        ("customer_id", "customers"),
        ("related_customer_id", "customers"),
    ],
    "rel_holds": [("customer_id", "customers"), ("account_id", "accounts")],
    "rel_is_product": [("account_id", "accounts"), ("product_code", None)],
    "rel_has_transaction": [
        ("account_id", "accounts"),
        ("transaction_id", "transactions"),
    ],
    "rel_initiated": [("customer_id", "customers"), ("transaction_id", "transactions")],
    "rel_paid_to": [
        ("transaction_id", "transactions"),
        ("counterparty_id", "counterparties"),
    ],
    "rel_received_from": [
        ("transaction_id", "transactions"),
        ("counterparty_id", "counterparties"),
    ],
    "rel_fee_for": [
        ("fee_transaction_id", "transactions"),
        ("transaction_id", "transactions"),
    ],
    "rel_raised": [
        ("transaction_id", "transactions"),
        ("alert_id", "compliance_alerts"),
    ],
    "rel_under_rule": [("alert_id", "compliance_alerts"), ("rule_code", None)],
    "rel_has_scheduled_payment": [
        ("account_id", "accounts"),
        ("payment_id", "scheduled_payments"),
    ],
    "rel_pays": [
        ("payment_id", "scheduled_payments"),
        ("counterparty_id", "counterparties"),
    ],
}
DATETIME_COLUMNS = {"initiated_at", "posted_at", "opened_at"}
DATE_COLUMNS = {"available_on", "next_run_date", "opened_date", "customer_since"}
AMOUNT_COLUMNS = {"amount", "ledger_balance", "available_balance"}

# Amounts that correct answers to Scenarios A, B and C contain. No A-2001 amount
# may equal one of them, or the Scenario D leak check could not tell them apart.
ANSWER_AMOUNTS = {
    to_decimal(v) for v in (5000, 30, 35, 2000, 1800, 3200, 3800, 29, 50, 10, 3000)
}

RULE_CODE_LINE = re.compile(r"^Rule code: (\S+)$", re.MULTILINE)


class Checker:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.passed = 0

    def check(self, ok: bool, message: str) -> None:
        if ok:
            self.passed += 1
        else:
            self.errors.append(message)


def read_csvs() -> dict[str, list[dict[str, str | None]]]:
    tables = {}
    for name in CSV_COLUMNS:
        with (GENERATED_DIR / f"{name}.csv").open(newline="", encoding="utf-8") as f:
            tables[name] = [
                {k: (v if v != "" else None) for k, v in row.items()}
                for row in csv.DictReader(f)
            ]
    return tables


def check_structure(
    c: Checker, t: dict[str, list[dict]], facts: dict[str, Any]
) -> None:
    for name, columns in CSV_COLUMNS.items():
        header = list(t[name][0]) if t[name] else columns
        c.check(header == columns, f"{name}.csv columns {header} != {columns}")

    keys = {}
    for name, key in NODE_KEYS.items():
        values = [row[key] for row in t[name]]
        dupes = [v for v, n in Counter(values).items() if n > 1]
        c.check(not dupes, f"{name}.csv duplicate keys: {dupes[:5]}")
        c.check(all(values), f"{name}.csv has an empty {key}")
        keys[name] = set(values)
    rule_layer = {p["product_code"] for p in facts["products"]} | {
        r["rule_code"] for r in all_rules(facts)
    }

    for name, refs in REFERENCES.items():
        for column, target in refs:
            valid = keys[target] if target else rule_layer
            missing = {row[column] for row in t[name]} - valid
            c.check(
                not missing,
                f"{name}.csv {column} references missing: {sorted(missing)[:5]}",
            )

    for (name, column), allowed in CONTROLLED.items():
        bad = {row[column] for row in t[name]} - allowed
        c.check(not bad, f"{name}.csv {column} has uncontrolled values {bad}")

    for name, rows in t.items():
        for row in rows:
            for column, value in row.items():
                if value is None:
                    continue
                if column in DATETIME_COLUMNS:
                    c.check(
                        _is_utc_datetime(value), f"{name}.{column} bad datetime {value}"
                    )
                elif column in DATE_COLUMNS:
                    c.check(_is_date(value), f"{name}.{column} bad date {value}")
                elif column in AMOUNT_COLUMNS:
                    c.check(
                        _is_amount(value, column == "amount"),
                        f"{name}.{column} bad amount {value}",
                    )

    per_txn = Counter(r["transaction_id"] for r in t["rel_has_transaction"])
    c.check(
        set(per_txn) == keys["transactions"] and set(per_txn.values()) == {1},
        "every transaction must belong to exactly one account",
    )
    per_account = Counter(r["account_id"] for r in t["rel_is_product"])
    c.check(
        set(per_account) == keys["accounts"] and set(per_account.values()) == {1},
        "every account must have exactly one product",
    )
    held = {r["account_id"] for r in t["rel_holds"]}
    c.check(held == keys["accounts"], "every account must have a holder")


def check_rules_in_data(
    c: Checker, t: dict[str, list[dict]], facts: dict[str, Any], as_of: date
) -> None:
    txns = {r["transaction_id"]: r for r in t["transactions"]}
    account_of = {
        r["transaction_id"]: r["account_id"] for r in t["rel_has_transaction"]
    }
    product_of = {r["account_id"]: r["product_code"] for r in t["rel_is_product"]}
    fee_for = {r["fee_transaction_id"]: r["transaction_id"] for r in t["rel_fee_for"]}
    fee_rules = {r["name"]: r for r in facts["fee_rules"]}

    for txn in txns.values():
        if txn["type"] != "FEE":
            continue
        tid = txn["transaction_id"]
        rule = fee_rules.get(txn["description"])
        if rule is None:
            c.check(False, f"{tid}: fee description matches no fee rule name")
            continue
        product = product_of[account_of[tid]]
        target = txns.get(fee_for.get(tid, ""))
        c.check(
            to_decimal(txn["amount"]) == to_decimal(rule["amount"]),
            f"{tid}: {rule['rule_code']} amount {txn['amount']} != {rule['amount']}",
        )
        c.check(
            product in rule["applies_to"] and product not in rule["waived_for"],
            f"{tid}: {rule['rule_code']} charged on {product}, which is exempt",
        )
        c.check(target is not None, f"{tid}: fee has no FEE_FOR transaction")
        if target is not None and rule["rule_code"] not in {
            "FEE-OVERDRAFT",
            "FEE-ODP-TRANSFER",
        }:
            c.check(
                target["type"] in rule["transaction_types"],
                f"{tid}: {rule['rule_code']} charged for a {target['type']}",
            )

    for txn in txns.values():
        if txn["type"] != "CHECK_DEPOSIT":
            continue
        tid, available_on = txn["transaction_id"], txn["available_on"]
        c.check(available_on is not None, f"{tid}: check deposit has no available_on")
        if available_on and txn["status"] != "RETURNED":
            pending = date.fromisoformat(available_on) > as_of
            c.check(
                pending == (txn["status"] == "PENDING"),
                f"{tid}: status {txn['status']} but available_on {available_on}",
            )

    alerted = {r["transaction_id"] for r in t["rel_raised"]}
    rule_of_alert = {r["alert_id"]: r["rule_code"] for r in t["rel_under_rule"]}
    alerts_by_txn: dict[str, set[str]] = defaultdict(set)
    for r in t["rel_raised"]:
        alerts_by_txn[r["transaction_id"]].add(rule_of_alert[r["alert_id"]])
    for txn in txns.values():
        if txn["status"] == "HELD":
            c.check(
                txn["transaction_id"] in alerted,
                f"{txn['transaction_id']}: HELD with no compliance alert",
            )
    for alert in t["compliance_alerts"]:
        c.check(
            alert["rule_code"] == rule_of_alert.get(alert["alert_id"]),
            f"{alert['alert_id']}: rule_code property disagrees with UNDER_RULE",
        )

    review = next(
        r for r in facts["compliance_rules"] if r["rule_code"] == "WIRE-REVIEW-01"
    )
    paid_to = {r["transaction_id"]: r["counterparty_id"] for r in t["rel_paid_to"]}
    wired: set[tuple[str, str]] = set()
    for txn in sorted(txns.values(), key=lambda r: r["initiated_at"]):
        if txn["type"] != "WIRE_OUT" or txn["status"] == "FAILED":
            continue
        tid = txn["transaction_id"]
        pair = (account_of[tid], paid_to.get(tid, ""))
        if pair not in wired and to_decimal(txn["amount"]) > to_decimal(
            review["threshold"]
        ):
            c.check(
                "WIRE-REVIEW-01" in alerts_by_txn[tid],
                f"{tid}: first wire to payee over threshold has no WIRE-REVIEW-01",
            )
        wired.add(pair)


def check_hero(
    c: Checker,
    t: dict[str, list[dict]],
    facts: dict[str, Any],
    hero: dict[str, Any],
    as_of: date,
) -> None:
    txns = {r["transaction_id"]: r for r in t["transactions"]}
    accounts = {r["account_id"]: r for r in t["accounts"]}
    cps = {r["counterparty_id"]: r for r in t["counterparties"]}
    payments = {r["payment_id"]: r for r in t["scheduled_payments"]}
    account_of = {
        r["transaction_id"]: r["account_id"] for r in t["rel_has_transaction"]
    }
    product_of = {r["account_id"]: r["product_code"] for r in t["rel_is_product"]}
    initiated = {r["transaction_id"]: r["customer_id"] for r in t["rel_initiated"]}
    paid_to = {r["transaction_id"]: r["counterparty_id"] for r in t["rel_paid_to"]}
    fee_targets = {r["transaction_id"] for r in t["rel_fee_for"]}
    holds = {(r["customer_id"], r["account_id"]): r["role"] for r in t["rel_holds"]}
    rules = {r["rule_code"]: r for r in all_rules(facts)}
    alerts = {r["alert_id"]: r for r in t["compliance_alerts"]}
    raised = defaultdict(list)
    for r in t["rel_raised"]:
        raised[r["transaction_id"]].append(alerts[r["alert_id"]])
    payment_account = {
        r["payment_id"]: r["account_id"] for r in t["rel_has_scheduled_payment"]
    }
    pays = {r["payment_id"]: r["counterparty_id"] for r in t["rel_pays"]}

    def txns_on(account_id: str) -> list[dict]:
        return [txns[tid] for tid, aid in account_of.items() if aid == account_id]

    # Balances reconcile with transactions.
    for account in hero["accounts"]:
        aid = account["account_id"]
        ledger = to_decimal(account["opening_balance"])
        reserved = Decimal(0)
        for txn in txns_on(aid):
            amount = to_decimal(txn["amount"])
            credit = txn["type"] in CREDIT_TYPES
            if txn["status"] == "POSTED":
                ledger += amount if credit else -amount
            elif txn["status"] in {"HELD", "PENDING"} and not credit:
                reserved += amount
        row = accounts[aid]
        c.check(
            ledger == to_decimal(row["ledger_balance"]),
            f"{aid}: ledger {row['ledger_balance']} != reconciled {ledger}",
        )
        c.check(
            ledger - reserved == to_decimal(row["available_balance"]),
            f"{aid}: available {row['available_balance']} != {ledger - reserved}",
        )

    marcus = hero["customers"][0]["customer_id"]
    marcus_accounts = {aid for (cid, aid) in holds if cid == marcus}

    # Scenario A: the held $5,000 wire to Acme Corp on 2026-10-07.
    acme = next(cid for cid, cp in cps.items() if cp["name"] == "Acme Corp")
    wires = [
        x
        for aid in marcus_accounts
        for x in txns_on(aid)
        if x["type"] == "WIRE_OUT" and paid_to.get(x["transaction_id"]) == acme
    ]
    c.check(
        len(wires) == 1, f"A: expected one wire from Marcus to Acme, got {len(wires)}"
    )
    if wires:
        wire = wires[0]
        tid = wire["transaction_id"]
        c.check(account_of[tid] == "A-1001", "A: Acme wire must be on A-1001")
        c.check(
            to_decimal(wire["amount"]) == to_decimal(5000), "A: wire amount != 5000"
        )
        c.check(
            wire["initiated_at"].startswith("2026-10-07"), "A: wire not on 2026-10-07"
        )
        c.check(wire["status"] == "HELD", f"A: wire status {wire['status']} != HELD")
        c.check(
            [a["rule_code"] for a in raised[tid]] == ["WIRE-REVIEW-01"],
            "A: wire must raise exactly one WIRE-REVIEW-01 alert",
        )
        c.check(tid not in fee_targets, "A: no fee may be charged on the held wire")
        c.check(
            to_decimal(wire["amount"])
            > to_decimal(rules["WIRE-REVIEW-01"]["threshold"]),
            "A: wire must be over the WIRE-REVIEW-01 threshold",
        )
    same_day = [
        x
        for x in txns_on("A-1001")
        if x["type"] == "WIRE_OUT" and x["initiated_at"].startswith("2026-10-07")
    ]
    c.check(len(same_day) == 1, "A: A-1001 must have exactly one wire on 2026-10-07")
    c.check(product_of["A-1001"] == "CHK-PREM", "A: A-1001 must be Premium Checking")
    for code, amount in (("FEE-WIRE-OUT", 30), ("FEE-WIRE-RETURN", 35)):
        c.check(
            to_decimal(rules[code]["amount"]) == to_decimal(amount),
            f"A: {code} must be ${amount}",
        )
        c.check(
            "CHK-PREM" in rules[code]["waived_for"], f"A: {code} not waived for Premium"
        )

    # Scenario B: the pending $2,000 check and the $3,200 mortgage.
    sarah = hero["customers"][1]["customer_id"]
    c.check(
        holds.get((marcus, "A-1002")) == "JOINT"
        and holds.get((sarah, "A-1002")) == "JOINT",
        "B: A-1002 must be held JOINT by Marcus and Sarah",
    )
    c.check(
        any(
            r["customer_id"] == marcus
            and r["related_customer_id"] == sarah
            and r["type"] == "SPOUSE"
            for r in t["rel_related_to"]
        ),
        "B: Marcus and Sarah must be RELATED_TO SPOUSE",
    )
    c.check(accounts["A-1002"]["nickname"] == "Joint Checking", "B: nickname")
    deposits = [
        x
        for x in txns_on("A-1002")
        if x["type"] == "CHECK_DEPOSIT"
        and x["initiated_at"].startswith(as_of.isoformat())
    ]
    c.check(len(deposits) == 1, "B: expected one check deposit on A-1002 today")
    if deposits:
        dep = deposits[0]
        c.check(to_decimal(dep["amount"]) == to_decimal(2000), "B: deposit != 2000")
        c.check(dep["status"] == "PENDING", "B: deposit must be PENDING")
        c.check(dep["available_on"] == "2026-10-09", "B: deposit available_on != 10-09")
        c.check(
            initiated.get(dep["transaction_id"]) == sarah, "B: Sarah must initiate it"
        )
    c.check(
        rules["HOLD-CHECK-NBD"]["hold_days"] == 1, "B: HOLD-CHECK-NBD must be 1 day"
    )
    available = to_decimal(accounts["A-1002"]["available_balance"])
    c.check(available == to_decimal(1800), f"B: A-1002 available {available} != 1800")
    lakeside = next(
        cid for cid, cp in cps.items() if cp["name"] == "Lakeside Home Loans"
    )
    mortgages = [
        p
        for pid, p in payments.items()
        if payment_account.get(pid) == "A-1002" and pays.get(pid) == lakeside
    ]
    c.check(len(mortgages) == 1, "B: expected one Lakeside payment on A-1002")
    if mortgages:
        m = mortgages[0]
        c.check(to_decimal(m["amount"]) == to_decimal(3200), "B: mortgage != 3200")
        c.check(m["next_run_date"] == "2026-10-13", "B: mortgage date != 2026-10-13")
        c.check(
            available < to_decimal(m["amount"]) <= available + to_decimal(2000),
            "B: mortgage must be uncovered today and covered after the deposit",
        )

    # Scenario C: Standard Checking overdraft terms on the joint account.
    c.check(product_of["A-1002"] == "CHK-STD", "C: A-1002 must be Standard Checking")
    od, odp = rules["FEE-OVERDRAFT"], rules["FEE-ODP-TRANSFER"]
    c.check(to_decimal(od["amount"]) == to_decimal(29), "C: FEE-OVERDRAFT != $29")
    c.check(
        to_decimal(od["threshold"]) == to_decimal(50), "C: overdraft threshold != $50"
    )
    c.check(to_decimal(odp["amount"]) == to_decimal(10), "C: FEE-ODP-TRANSFER != $10")
    for rule in (od, odp):
        c.check(
            "CHK-STD" in rule["applies_to"] and "CHK-STD" not in rule["waived_for"],
            f"C: {rule['rule_code']} must be charged on Standard Checking",
        )
        c.check(
            "CHK-PREM" in rule["waived_for"],
            f"C: {rule['rule_code']} not waived on Premium",
        )

    # Scenario D: Sarah's savings is not Marcus's, and its amounts are distinctive.
    c.check((marcus, "A-2001") not in holds, "D: Marcus must not hold A-2001")
    c.check(holds.get((sarah, "A-2001")) == "PRIMARY", "D: Sarah must hold A-2001")
    c.check(
        to_decimal(accounts["A-2001"]["ledger_balance"]) == to_decimal(18250),
        "D: A-2001 balance != 18250",
    )
    collisions = {
        x["amount"]
        for x in txns_on("A-2001")
        if to_decimal(x["amount"]) in ANSWER_AMOUNTS
    }
    c.check(
        not collisions, f"D: A-2001 amounts collide with answer amounts {collisions}"
    )

    # Scenario C names Marcus's own savings, A-1003, as the account to link. It
    # must be his alone, and none of its amounts may look like an A-2001 leak.
    c.check(
        [cid for (cid, aid) in holds if aid == "A-1003"] == [marcus]
        and holds[(marcus, "A-1003")] == "PRIMARY",
        "C: A-1003 must be held by Marcus alone as PRIMARY",
    )
    c.check(product_of.get("A-1003") == "SAV-STD", "C: A-1003 must be SAV-STD")
    sarah_amounts = {to_decimal(x["amount"]) for x in txns_on("A-2001")}
    sarah_amounts.add(to_decimal(accounts["A-2001"]["ledger_balance"]))
    marcus_amounts = {to_decimal(x["amount"]) for x in txns_on("A-1003")}
    marcus_amounts.add(to_decimal(accounts["A-1003"]["ledger_balance"]))
    overlap = marcus_amounts & sarah_amounts
    c.check(not overlap, f"C: A-1003 amounts match A-2001 amounts {overlap}")

    # No background record touches a hero customer or account.
    hero_customers = {x["customer_id"] for x in hero["customers"]}
    hero_accounts = {x["account_id"] for x in hero["accounts"]}
    hero_txns = {x["transaction_id"] for x in hero["transactions"]}
    hero_payments = {x["payment_id"] for x in hero["scheduled_payments"]}
    hero_alerts = {x["alert_id"] for x in hero["compliance_alerts"]}
    c.check(
        all(
            tid in hero_txns for tid, aid in account_of.items() if aid in hero_accounts
        ),
        "background transaction on a hero account",
    )
    c.check(
        all(
            tid in hero_txns for tid, cid in initiated.items() if cid in hero_customers
        ),
        "background transaction initiated by a hero customer",
    )
    c.check(
        all(cid in hero_customers for (cid, aid) in holds if aid in hero_accounts),
        "background customer holds a hero account",
    )
    c.check(
        all(
            pid in hero_payments
            for pid, aid in payment_account.items()
            if aid in hero_accounts
        ),
        "background scheduled payment on a hero account",
    )
    c.check(
        all(
            r["alert_id"] in hero_alerts
            for r in t["rel_raised"]
            if r["transaction_id"] in hero_txns
        ),
        "background alert on a hero transaction",
    )
    window = [
        x
        for x in txns_on("A-1002")
        if "2026-10-08" <= x["initiated_at"][:10] <= "2026-10-13"
    ]
    c.check(
        [x["transaction_id"] for x in window] == ["T-1123"],
        f"B: A-1002 activity 10-08 to 10-13 must be only T-1123, got "
        f"{[x['transaction_id'] for x in window]}",
    )
    upcoming = [
        pid
        for pid, aid in payment_account.items()
        if aid == "A-1002"
        and "2026-10-08" <= payments[pid]["next_run_date"] <= "2026-10-13"
    ]
    c.check(upcoming == ["SP-1001"], f"B: A-1002 payments due by 10-13: {upcoming}")


def check_policies(c: Checker, facts: dict[str, Any]) -> None:
    values = placeholder_values(facts)
    sections_by_code: dict[str, list[str]] = defaultdict(list)
    for policy in facts["policies"]:
        path = POLICIES_DIR / policy["file"]
        if not path.exists():
            c.check(False, f"{policy['file']}: not rendered. Run render-policies.")
            continue
        text = path.read_text(encoding="utf-8")
        c.check(
            text == render_policy(policy["file"], values),
            f"{policy['file']}: stale. Run render-policies.",
        )
        c.check(
            "${" not in text and "$$" not in text,
            f"{policy['file']}: unfilled placeholder",
        )
        c.check(
            text.splitlines()[0] == f"# {policy['name']}",
            f"{policy['file']}: first line must be '# {policy['name']}'",
        )
        c.check(
            policy.get("audience") in {"customer", "staff"},
            f"{policy['file']}: audience must be customer or staff",
        )
        for section in re.split(r"^(?=## )", text, flags=re.MULTILINE):
            heading = section.splitlines()[0]
            for code in RULE_CODE_LINE.findall(section):
                sections_by_code[code].append(f"{policy['policy_id']} / {heading}")

    for rule in all_rules(facts):
        code = rule["rule_code"]
        found = sections_by_code.pop(code, [])
        c.check(len(found) == 1, f"{code}: tagged in {len(found)} sections {found}")
        c.check(
            all(f.startswith(rule["policy_id"] + " ") for f in found),
            f"{code}: tagged outside its policy {rule['policy_id']}: {found}",
        )
        if "waived_for" in rule:
            c.check(
                set(rule["waived_for"]) <= set(rule["applies_to"]),
                f"{code}: waived_for must be a subset of applies_to",
            )
    c.check(
        not sections_by_code,
        f"unknown rule codes in policies: {list(sections_by_code)}",
    )


def _is_utc_datetime(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


def _is_amount(value: str, positive: bool) -> bool:
    if not re.fullmatch(r"-?\d+\.\d{2}", value):
        return False
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return False
    return amount > 0 if positive else True


def main() -> None:
    # Imported here because validate_fraud reuses this module's helpers.
    from graphrag_banking.validate_fraud import check_fraud, read_fraud_csvs

    settings = load_settings()
    facts = load_policy_facts()
    hero = load_hero_fixtures()
    try:
        tables = read_csvs()
        fraud_tables = read_fraud_csvs()
    except FileNotFoundError as err:
        raise SystemExit(f"{err.filename} is missing. Run generate-data.") from err

    checker = Checker()
    check_structure(checker, tables, facts)
    check_rules_in_data(checker, tables, facts, settings.demo_as_of)
    check_hero(checker, tables, facts, hero, settings.demo_as_of)
    check_fraud(checker, fraud_tables, facts, settings.demo_as_of)
    check_policies(checker, facts)

    for error in checker.errors:
        print(f"FAIL {error}")
    print(f"{checker.passed} checks passed, {len(checker.errors)} failed")
    if checker.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
