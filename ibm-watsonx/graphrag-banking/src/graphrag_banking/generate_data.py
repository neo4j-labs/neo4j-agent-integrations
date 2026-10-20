"""Generate the synthetic banking data and write CSVs to data/generated/.

Faker supplies field values and a seeded random.Random supplies structure, so
the same DATA_SEED always produces the same files. Hero records come from
hero_fixtures.yaml. Background records use IDs outside the hero ranges and
never touch a hero customer or account, so they cannot change a hero answer.
The CSV contract is in data/README.md.
"""

import csv
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

from graphrag_banking.config import GENERATED_DIR, load_settings
from graphrag_banking.facts import (
    CREDIT_TYPES,
    DEBIT_TYPES,
    load_hero_fixtures,
    load_policy_facts,
    to_decimal,
)

# Volumes include the hero records (PRD section 6.2).
NUM_CUSTOMERS = 200
NUM_ACCOUNTS = 350
NUM_COUNTERPARTIES = 300
NUM_SCHEDULED_PAYMENTS = 150
NUM_SPOUSE_PAIRS = 20
TRANSACTIONS_PER_ACCOUNT = (4, 12)
WINDOW_DAYS = 90

# US bank holidays that fall in the window or the next 30 days.
BANK_HOLIDAYS = frozenset({date(2026, 9, 7), date(2026, 10, 12)})

CHECKING_TYPE_WEIGHTS = {
    "CARD": 45,
    "ACH_OUT": 20,
    "ACH_IN": 15,
    "CHECK_DEPOSIT": 7,
    "WIRE_OUT": 4,
    "WIRE_IN": 3,
    "TRANSFER": 6,
}
SAVINGS_TYPE_WEIGHTS = {
    "ACH_IN": 40,
    "TRANSFER": 30,
    "ACH_OUT": 15,
    "CHECK_DEPOSIT": 10,
    "WIRE_IN": 5,
}
COUNTERPARTY_KINDS_BY_TYPE = {
    "CARD": ("MERCHANT",),
    "ACH_OUT": ("LENDER", "BUSINESS", "MERCHANT"),
    "ACH_IN": ("BUSINESS",),
    "WIRE_OUT": ("BUSINESS", "INDIVIDUAL"),
    "WIRE_IN": ("BUSINESS", "INDIVIDUAL"),
    "CHECK_DEPOSIT": ("INDIVIDUAL", "BUSINESS"),
}
CATEGORIES_BY_KIND = {
    "MERCHANT": ["Groceries", "Dining", "Utilities", "Travel", "Retail", "Fuel"],
    "BUSINESS": ["Professional Services", "Payroll", "Insurance", "Real Estate"],
    "INDIVIDUAL": ["Personal"],
    "LENDER": ["Mortgage", "Auto Loan", "Credit Card", "Student Loan"],
}
CHANNELS_BY_TYPE = {
    "CARD": ("CARD",),
    "ACH_OUT": ("ACH",),
    "ACH_IN": ("ACH",),
    "WIRE_OUT": ("ONLINE", "BRANCH"),
    "WIRE_IN": ("SYSTEM",),
    "CHECK_DEPOSIT": ("MOBILE", "BRANCH"),
    "TRANSFER": ("ONLINE", "MOBILE"),
}
DESCRIPTIONS_BY_TYPE = {
    "CARD": "{name} purchase",
    "ACH_OUT": "Payment to {name}",
    "ACH_IN": "Direct deposit from {name}",
    "WIRE_OUT": "Wire to {name}",
    "WIRE_IN": "Incoming wire from {name}",
    "CHECK_DEPOSIT": "Check deposit",
    "TRANSFER": "Transfer to linked account",
}
FOREIGN_COUNTRIES = ["CA", "GB", "MX", "DE"]

CSV_COLUMNS = {
    "customers": [
        "customer_id",
        "name",
        "email",
        "phone",
        "segment",
        "risk_rating",
        "kyc_status",
        "customer_since",
    ],
    "accounts": [
        "account_id",
        "nickname",
        "ledger_balance",
        "available_balance",
        "currency",
        "status",
        "opened_date",
    ],
    "transactions": [
        "transaction_id",
        "type",
        "amount",
        "currency",
        "initiated_at",
        "posted_at",
        "available_on",
        "status",
        "channel",
        "description",
    ],
    "counterparties": ["counterparty_id", "name", "kind", "category", "country"],
    "scheduled_payments": [
        "payment_id",
        "amount",
        "frequency",
        "next_run_date",
        "status",
    ],
    "compliance_alerts": ["alert_id", "rule_code", "status", "opened_at", "reason"],
    "rel_related_to": ["customer_id", "related_customer_id", "type"],
    "rel_holds": ["customer_id", "account_id", "role"],
    "rel_is_product": ["account_id", "product_code"],
    "rel_has_transaction": ["account_id", "transaction_id"],
    "rel_initiated": ["customer_id", "transaction_id"],
    "rel_paid_to": ["transaction_id", "counterparty_id"],
    "rel_received_from": ["transaction_id", "counterparty_id"],
    "rel_fee_for": ["fee_transaction_id", "transaction_id"],
    "rel_raised": ["transaction_id", "alert_id"],
    "rel_under_rule": ["alert_id", "rule_code"],
    "rel_has_scheduled_payment": ["account_id", "payment_id"],
    "rel_pays": ["payment_id", "counterparty_id"],
}


@dataclass
class Txn:
    """A transaction with its relationships, before it is split into CSV rows."""

    transaction_id: str
    account_id: str
    type: str
    amount: Decimal
    initiated_at: datetime
    status: str
    channel: str
    description: str
    posted_at: datetime | None = None
    available_on: date | None = None
    counterparty_id: str | None = None
    initiated_by: str | None = None
    fee_for: str | None = None


@dataclass
class Dataset:
    rows: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    txns: list[Txn] = field(default_factory=list)


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in BANK_HOLIDAYS


def add_business_days(day: date, count: int) -> date:
    while count > 0:
        day += timedelta(days=1)
        if is_business_day(day):
            count -= 1
    return day


def business_day_on_or_before(day: date) -> date:
    while not is_business_day(day):
        day -= timedelta(days=1)
    return day


def fmt_datetime(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def fmt_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def fmt_amount(value: Decimal) -> str:
    return f"{value:.2f}"


def parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Generator:
    def __init__(self, seed: int, as_of: date, facts: dict[str, Any]) -> None:
        self.rng = random.Random(seed)
        self.fake = Faker("en_US")
        self.fake.seed_instance(seed)
        self.as_of = as_of
        self.window_start = as_of - timedelta(days=WINDOW_DAYS)
        self.facts = facts
        self.data = Dataset()
        self.holders: dict[str, list[str]] = defaultdict(list)
        self.product_of: dict[str, str] = {}
        self.counterparties_by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.counterparty_by_id: dict[str, dict[str, Any]] = {}
        self.next_txn = 50000
        self.next_alert = 5000

    # ---- helpers -----------------------------------------------------------

    def money(self, low: float, high: float) -> Decimal:
        return to_decimal(round(self.rng.uniform(low, high), 2))

    def new_txn_id(self) -> str:
        self.next_txn += 1
        return f"T-{self.next_txn - 1}"

    def new_alert_id(self) -> str:
        self.next_alert += 1
        return f"AL-{self.next_alert - 1}"

    def random_datetime(self, business_only: bool) -> datetime:
        day = self.window_start + timedelta(days=self.rng.randint(1, WINDOW_DAYS))
        if business_only:
            day = business_day_on_or_before(day)
        # 12:00Z to 23:00Z is 8 AM to 7 PM ET, before the 8 PM deposit cutoff.
        # Activity on DEMO_AS_OF itself happens in the morning.
        latest_hour = 15 if day == self.as_of else 22
        moment = time(self.rng.randint(12, latest_hour), self.rng.randint(0, 59))
        return datetime.combine(day, moment, tzinfo=UTC)

    # ---- background population -----------------------------------------

    def customers(self, hero_names: set[str]) -> list[str]:
        ids = []
        last_names: list[str] = []
        used_names = set(hero_names)
        hero_last_names = {name.split()[-1] for name in hero_names}
        count = NUM_CUSTOMERS - len(hero_names)
        for i in range(count):
            # The second customer of each spouse pair shares the first's last name.
            pair_index = i - NUM_SPOUSE_PAIRS
            while True:
                last = (
                    last_names[pair_index]
                    if 0 <= pair_index < NUM_SPOUSE_PAIRS
                    else self.fake.last_name()
                )
                name = f"{self.fake.first_name()} {last}"
                if name not in used_names and last not in hero_last_names:
                    break
            used_names.add(name)
            last_names.append(last)
            customer_id = f"C-{5000 + i}"
            ids.append(customer_id)
            first = name.split()[0].lower()
            self.data.rows["customers"].append(
                {
                    "customer_id": customer_id,
                    "name": name,
                    "email": f"{first}.{last.lower()}{i}@example.com",
                    "phone": f"+1-555-{self.rng.randint(1000, 9999)}",
                    "segment": self.rng.choices(["RETAIL", "PREMIER"], [80, 20])[0],
                    "risk_rating": self.rng.choices(
                        ["LOW", "MEDIUM", "HIGH"], [75, 20, 5]
                    )[0],
                    "kyc_status": self.rng.choices(
                        ["VERIFIED", "PENDING", "EXPIRED"], [92, 5, 3]
                    )[0],
                    "customer_since": fmt_date(
                        self.fake.date_between(date(2008, 1, 1), date(2025, 12, 31))
                    ),
                }
            )
        for i in range(NUM_SPOUSE_PAIRS):
            self.data.rows["rel_related_to"].append(
                {
                    "customer_id": ids[i],
                    "related_customer_id": ids[NUM_SPOUSE_PAIRS + i],
                    "type": "SPOUSE",
                }
            )
        return ids

    def counterparties(self, hero: list[dict[str, Any]]) -> None:
        used = {cp["name"] for cp in hero}
        for cp in hero:
            self.counterparties_by_kind[cp["kind"]].append(cp)
            self.counterparty_by_id[cp["counterparty_id"]] = cp
        for i in range(NUM_COUNTERPARTIES - len(hero)):
            kind = self.rng.choices(
                ["MERCHANT", "BUSINESS", "INDIVIDUAL", "LENDER"], [50, 30, 12, 8]
            )[0]
            while True:
                name = self.fake.name() if kind == "INDIVIDUAL" else self.fake.company()
                if name not in used:
                    break
            used.add(name)
            foreign = kind in {"BUSINESS", "INDIVIDUAL"} and self.rng.random() < 0.1
            cp = {
                "counterparty_id": f"CP-{5000 + i}",
                "name": name,
                "kind": kind,
                "category": self.rng.choice(CATEGORIES_BY_KIND[kind]),
                "country": self.rng.choice(FOREIGN_COUNTRIES) if foreign else "US",
            }
            self.data.rows["counterparties"].append(cp)
            self.counterparties_by_kind[kind].append(cp)
            self.counterparty_by_id[cp["counterparty_id"]] = cp

    def accounts(self, customer_ids: list[str], num_hero_accounts: int) -> list[str]:
        plan: list[tuple[list[str], str, str]] = []
        for i in range(NUM_SPOUSE_PAIRS):
            pair = [customer_ids[i], customer_ids[NUM_SPOUSE_PAIRS + i]]
            product = self.rng.choices(["CHK-STD", "CHK-PREM"], [70, 30])[0]
            plan.append((pair, product, "JOINT"))
        for customer_id in customer_ids:
            product = self.rng.choices(["CHK-STD", "CHK-PREM"], [75, 25])[0]
            plan.append(([customer_id], product, "PRIMARY"))
        while len(plan) < NUM_ACCOUNTS - num_hero_accounts:
            product = self.rng.choices(["SAV-STD", "CHK-STD"], [70, 30])[0]
            plan.append(([self.rng.choice(customer_ids)], product, "PRIMARY"))

        names = {p["product_code"]: p["name"] for p in self.facts["products"]}
        ids = []
        for i, (owners, product, role) in enumerate(plan):
            account_id = f"A-{5000 + i}"
            ids.append(account_id)
            self.product_of[account_id] = product
            if role == "JOINT" and product.startswith("CHK"):
                nickname = "Joint Checking"
            elif product == "SAV-STD":
                nickname = self.rng.choice(
                    [names[product], "Emergency Fund", "Vacation Savings", "Rainy Day"]
                )
            else:
                nickname = names[product]
            self.data.rows["accounts"].append(
                {
                    "account_id": account_id,
                    "nickname": nickname,
                    "currency": "USD",
                    "status": self.rng.choices(["OPEN", "FROZEN"], [98, 2])[0],
                    "opened_date": fmt_date(
                        self.fake.date_between(date(2010, 1, 1), date(2026, 3, 31))
                    ),
                }
            )
            self.data.rows["rel_is_product"].append(
                {"account_id": account_id, "product_code": product}
            )
            for owner in owners:
                self.holders[account_id].append(owner)
                self.data.rows["rel_holds"].append(
                    {"customer_id": owner, "account_id": account_id, "role": role}
                )
        return ids

    def transactions(self, account_ids: list[str]) -> None:
        for account_id in account_ids:
            weights = (
                SAVINGS_TYPE_WEIGHTS
                if self.product_of[account_id] == "SAV-STD"
                else CHECKING_TYPE_WEIGHTS
            )
            for _ in range(self.rng.randint(*TRANSACTIONS_PER_ACCOUNT)):
                txn_type = self.rng.choices(list(weights), list(weights.values()))[0]
                self.data.txns.append(self.background_txn(account_id, txn_type))

    def background_txn(self, account_id: str, txn_type: str) -> Txn:
        initiated_at = self.random_datetime(business_only=txn_type != "CARD")
        amount = self.amount_for(txn_type)
        counterparty = None
        if txn_type in COUNTERPARTY_KINDS_BY_TYPE:
            kind = self.rng.choice(COUNTERPARTY_KINDS_BY_TYPE[txn_type])
            counterparty = self.rng.choice(self.counterparties_by_kind[kind])
        description = DESCRIPTIONS_BY_TYPE[txn_type].format(
            name=counterparty["name"] if counterparty else ""
        )
        initiated_by = None
        if txn_type in DEBIT_TYPES or txn_type == "CHECK_DEPOSIT":
            initiated_by = self.rng.choice(self.holders[account_id])

        txn = Txn(
            transaction_id=self.new_txn_id(),
            account_id=account_id,
            type=txn_type,
            amount=amount,
            initiated_at=initiated_at,
            status="POSTED",
            channel=self.rng.choice(CHANNELS_BY_TYPE[txn_type]),
            description=description,
            counterparty_id=counterparty["counterparty_id"] if counterparty else None,
            initiated_by=initiated_by,
        )
        roll = self.rng.random()
        if txn_type == "WIRE_OUT" and roll < 0.04:
            txn.status = "FAILED"
        elif (txn_type == "WIRE_OUT" and roll < 0.10) or (
            txn_type == "CHECK_DEPOSIT" and roll < 0.03
        ):
            txn.status = "RETURNED"
        elif txn_type == "CARD" and roll < 0.01:
            txn.status = "REVERSED"
        elif initiated_at.date() == self.as_of:
            txn.status = "PENDING"
        if txn.status in {"POSTED", "RETURNED", "REVERSED"}:
            minutes = self.rng.randint(30, 180) if txn_type == "WIRE_OUT" else 0
            txn.posted_at = initiated_at + timedelta(minutes=minutes)
        return txn

    def amount_for(self, txn_type: str) -> Decimal:
        match txn_type:
            case "CARD":
                return self.money(5, 300)
            case "ACH_OUT":
                return self.money(40, 2500)
            case "ACH_IN":
                return self.money(500, 5000)
            case "CHECK_DEPOSIT":
                if self.rng.random() < 0.05:
                    return self.money(6000, 12000)
                return self.money(50, 3000)
            case "WIRE_OUT":
                if self.rng.random() < 0.35:
                    return self.money(3000.01, 25000)
                return self.money(200, 2999)
            case "WIRE_IN":
                return self.money(1000, 20000)
            case _:
                return self.money(50, 2000)

    # ---- rules applied to the background --------------------------------

    def check_holds(self) -> None:
        nbd, large = (
            next(r for r in self.facts["hold_rules"] if r["rule_code"] == code)
            for code in ("HOLD-CHECK-NBD", "HOLD-CHECK-LARGE")
        )
        for txn in self.data.txns:
            if txn.type != "CHECK_DEPOSIT":
                continue
            days = (
                large["hold_days"]
                if txn.amount > to_decimal(large["threshold"])
                else nbd["hold_days"]
            )
            txn.available_on = add_business_days(txn.initiated_at.date(), days)
            if txn.status != "RETURNED" and txn.available_on > self.as_of:
                txn.status, txn.posted_at = "PENDING", None

    def alerts(self) -> None:
        rules = {r["rule_code"]: r for r in self.facts["compliance_rules"]}
        review_threshold = to_decimal(rules["WIRE-REVIEW-01"]["threshold"])
        velocity_threshold = to_decimal(rules["AML-VELOCITY-01"]["threshold"])
        velocity_types = set(rules["AML-VELOCITY-01"]["transaction_types"])
        # Alerts on yesterday's or today's activity are still open.
        recent = self.as_of - timedelta(days=1)

        by_account: dict[str, list[Txn]] = defaultdict(list)
        for txn in sorted(self.data.txns, key=lambda t: t.initiated_at):
            by_account[txn.account_id].append(txn)

        for txns in by_account.values():
            wired_payees: set[str] = set()
            for txn in txns:
                if txn.type != "WIRE_OUT" or txn.status == "FAILED":
                    continue
                first_to_payee = txn.counterparty_id not in wired_payees
                wired_payees.add(txn.counterparty_id)
                if first_to_payee and txn.amount > review_threshold:
                    self.raise_alert(
                        txn,
                        "WIRE-REVIEW-01",
                        "First outgoing wire to this payee and above the "
                        "review threshold",
                        recent,
                    )
            for txn in txns:
                cp = self.counterparty_by_id.get(txn.counterparty_id or "")
                if (
                    txn.type in {"WIRE_OUT", "WIRE_IN"}
                    and cp
                    and cp["country"] != "US"
                    and txn.status != "FAILED"
                    and self.rng.random() < 0.4
                ):
                    self.raise_alert(
                        txn,
                        "SANCTIONS-SCREEN-01",
                        "Potential name match on a sanctions list",
                        recent,
                    )
            outgoing = [
                t for t in txns if t.type in velocity_types and t.status != "FAILED"
            ]
            for i, txn in enumerate(outgoing):
                window = [
                    t
                    for t in outgoing[: i + 1]
                    if txn.initiated_at - t.initiated_at <= timedelta(hours=24)
                ]
                total = sum((t.amount for t in window), Decimal(0))
                if (
                    total > velocity_threshold
                    and total - txn.amount <= velocity_threshold
                ):
                    self.raise_alert(
                        txn,
                        "AML-VELOCITY-01",
                        "Outgoing payments above the 24-hour threshold",
                        recent,
                        hold=False,
                    )

    def raise_alert(
        self, txn: Txn, rule_code: str, reason: str, recent: date, hold: bool = True
    ) -> None:
        is_recent = txn.initiated_at.date() >= recent
        if is_recent:
            status = "OPEN"
            if hold and txn.status in {"POSTED", "PENDING"}:
                txn.status, txn.posted_at = "HELD", None
        else:
            status = self.rng.choices(["CLEARED", "ESCALATED"], [85, 15])[0]
        alert_id = self.new_alert_id()
        self.data.rows["compliance_alerts"].append(
            {
                "alert_id": alert_id,
                "rule_code": rule_code,
                "status": status,
                "opened_at": fmt_datetime(txn.initiated_at + timedelta(seconds=5)),
                "reason": reason,
            }
        )
        self.data.rows["rel_raised"].append(
            {"transaction_id": txn.transaction_id, "alert_id": alert_id}
        )
        self.data.rows["rel_under_rule"].append(
            {"alert_id": alert_id, "rule_code": rule_code}
        )

    def fees(self) -> None:
        """Charge fees that match policy_facts.yaml for each account's product."""
        rules = {r["rule_code"]: r for r in self.facts["fee_rules"]}
        fees: list[Txn] = []
        for txn in self.data.txns:
            due = []
            if txn.type == "WIRE_OUT" and txn.status in {"POSTED", "RETURNED"}:
                due.append("FEE-WIRE-OUT")
            if txn.type == "WIRE_OUT" and txn.status == "RETURNED":
                due.append("FEE-WIRE-RETURN")
            if txn.type == "WIRE_IN" and txn.status == "POSTED":
                due.append("FEE-WIRE-IN")
            if txn.type == "CHECK_DEPOSIT" and txn.status == "RETURNED":
                due.append("FEE-DEPOSIT-RETURN")
            if (
                txn.type in {"CARD", "ACH_OUT"}
                and txn.status == "POSTED"
                and self.product_of[txn.account_id] == "CHK-STD"
                and self.rng.random() < 0.02
            ):
                due.append(self.rng.choice(["FEE-OVERDRAFT", "FEE-ODP-TRANSFER"]))
            for code in due:
                rule = rules[code]
                product = self.product_of[txn.account_id]
                if product not in rule["applies_to"] or product in rule["waived_for"]:
                    continue
                charged_at = (txn.posted_at or txn.initiated_at) + timedelta(hours=1)
                fees.append(
                    Txn(
                        transaction_id=self.new_txn_id(),
                        account_id=txn.account_id,
                        type="FEE",
                        amount=to_decimal(rule["amount"]),
                        initiated_at=charged_at,
                        posted_at=charged_at,
                        status="POSTED",
                        channel="SYSTEM",
                        description=rule["name"],
                        fee_for=txn.transaction_id,
                    )
                )
        self.data.txns.extend(fees)

    def balances(self, account_ids: list[str]) -> None:
        reserved: dict[str, Decimal] = defaultdict(Decimal)
        for txn in self.data.txns:
            if txn.type in DEBIT_TYPES and txn.status in {"HELD", "PENDING"}:
                reserved[txn.account_id] += txn.amount
        ranges = {
            "CHK-STD": (200, 8000),
            "CHK-PREM": (5000, 60000),
            "SAV-STD": (500, 40000),
        }
        rows = {row["account_id"]: row for row in self.data.rows["accounts"]}
        for account_id in account_ids:
            ledger = self.money(*ranges[self.product_of[account_id]])
            ledger = max(ledger, reserved[account_id] + self.money(100, 2000))
            rows[account_id]["ledger_balance"] = fmt_amount(ledger)
            rows[account_id]["available_balance"] = fmt_amount(
                ledger - reserved[account_id]
            )

    def scheduled_payments(self, account_ids: list[str], num_hero: int) -> None:
        checking = [a for a in account_ids if self.product_of[a] != "SAV-STD"]
        payees = (
            self.counterparties_by_kind["LENDER"]
            + self.counterparties_by_kind["BUSINESS"]
        )
        for i in range(NUM_SCHEDULED_PAYMENTS - num_hero):
            payment_id = f"SP-{5000 + i}"
            account_id = self.rng.choice(checking)
            payee = self.rng.choice(payees)
            next_run = business_day_on_or_before(
                self.as_of + timedelta(days=self.rng.randint(2, 30))
            )
            self.data.rows["scheduled_payments"].append(
                {
                    "payment_id": payment_id,
                    "amount": fmt_amount(self.money(25, 3000)),
                    "frequency": self.rng.choices(
                        ["WEEKLY", "BIWEEKLY", "MONTHLY"], [10, 20, 70]
                    )[0],
                    "next_run_date": fmt_date(next_run),
                    "status": self.rng.choices(["ACTIVE", "PAUSED"], [90, 10])[0],
                }
            )
            self.data.rows["rel_has_scheduled_payment"].append(
                {"account_id": account_id, "payment_id": payment_id}
            )
            self.data.rows["rel_pays"].append(
                {"payment_id": payment_id, "counterparty_id": payee["counterparty_id"]}
            )

    # ---- hero fixtures ---------------------------------------------------

    def merge_hero(self, hero: dict[str, Any]) -> None:
        rows = self.data.rows
        for customer in hero["customers"]:
            rows["customers"].append(dict(customer))
        rows["rel_related_to"].extend(dict(r) for r in hero["relationships"])
        rows["counterparties"].extend(dict(cp) for cp in hero["counterparties"])
        for account in hero["accounts"]:
            rows["accounts"].append(
                {
                    "account_id": account["account_id"],
                    "nickname": account["nickname"],
                    "ledger_balance": fmt_amount(to_decimal(account["ledger_balance"])),
                    "available_balance": fmt_amount(
                        to_decimal(account["available_balance"])
                    ),
                    "currency": account["currency"],
                    "status": account["status"],
                    "opened_date": account["opened_date"],
                }
            )
            rows["rel_is_product"].append(
                {
                    "account_id": account["account_id"],
                    "product_code": account["product_code"],
                }
            )
            for holder in account["holders"]:
                rows["rel_holds"].append(
                    {
                        "customer_id": holder["customer_id"],
                        "account_id": account["account_id"],
                        "role": holder["role"],
                    }
                )
        for t in hero["transactions"]:
            self.data.txns.append(
                Txn(
                    transaction_id=t["transaction_id"],
                    account_id=t["account_id"],
                    type=t["type"],
                    amount=to_decimal(t["amount"]),
                    initiated_at=parse_datetime(t["initiated_at"]),
                    posted_at=parse_datetime(t["posted_at"]),
                    available_on=date.fromisoformat(t["available_on"])
                    if t["available_on"]
                    else None,
                    status=t["status"],
                    channel=t["channel"],
                    description=t["description"],
                    counterparty_id=t["counterparty_id"],
                    initiated_by=t["initiated_by"],
                    fee_for=t.get("fee_for"),
                )
            )
        for alert in hero["compliance_alerts"]:
            rows["compliance_alerts"].append(
                {k: alert[k] for k in CSV_COLUMNS["compliance_alerts"]}
            )
            rows["rel_raised"].append(
                {
                    "transaction_id": alert["transaction_id"],
                    "alert_id": alert["alert_id"],
                }
            )
            rows["rel_under_rule"].append(
                {"alert_id": alert["alert_id"], "rule_code": alert["rule_code"]}
            )
        for payment in hero["scheduled_payments"]:
            rows["scheduled_payments"].append(
                {
                    "payment_id": payment["payment_id"],
                    "amount": fmt_amount(to_decimal(payment["amount"])),
                    "frequency": payment["frequency"],
                    "next_run_date": payment["next_run_date"],
                    "status": payment["status"],
                }
            )
            rows["rel_has_scheduled_payment"].append(
                {
                    "account_id": payment["account_id"],
                    "payment_id": payment["payment_id"],
                }
            )
            rows["rel_pays"].append(
                {
                    "payment_id": payment["payment_id"],
                    "counterparty_id": payment["counterparty_id"],
                }
            )

    def transaction_rows(self) -> None:
        rows = self.data.rows
        for txn in sorted(self.data.txns, key=lambda t: t.transaction_id):
            rows["transactions"].append(
                {
                    "transaction_id": txn.transaction_id,
                    "type": txn.type,
                    "amount": fmt_amount(txn.amount),
                    "currency": "USD",
                    "initiated_at": fmt_datetime(txn.initiated_at),
                    "posted_at": fmt_datetime(txn.posted_at),
                    "available_on": fmt_date(txn.available_on),
                    "status": txn.status,
                    "channel": txn.channel,
                    "description": txn.description,
                }
            )
            rows["rel_has_transaction"].append(
                {"account_id": txn.account_id, "transaction_id": txn.transaction_id}
            )
            if txn.initiated_by:
                rows["rel_initiated"].append(
                    {
                        "customer_id": txn.initiated_by,
                        "transaction_id": txn.transaction_id,
                    }
                )
            if txn.counterparty_id:
                target = (
                    "rel_received_from" if txn.type in CREDIT_TYPES else "rel_paid_to"
                )
                rows[target].append(
                    {
                        "transaction_id": txn.transaction_id,
                        "counterparty_id": txn.counterparty_id,
                    }
                )
            if txn.fee_for:
                rows["rel_fee_for"].append(
                    {
                        "fee_transaction_id": txn.transaction_id,
                        "transaction_id": txn.fee_for,
                    }
                )

    def run(self, hero: dict[str, Any]) -> Dataset:
        hero_names = {c["name"] for c in hero["customers"]}
        customer_ids = self.customers(hero_names)
        self.counterparties(hero["counterparties"])
        account_ids = self.accounts(customer_ids, len(hero["accounts"]))
        self.transactions(account_ids)
        self.check_holds()
        self.alerts()
        self.fees()
        self.balances(account_ids)
        self.scheduled_payments(account_ids, len(hero["scheduled_payments"]))
        self.merge_hero(hero)
        self.transaction_rows()
        return self.data


def write_csvs(data: Dataset) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for name, columns in CSV_COLUMNS.items():
        path = GENERATED_DIR / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data.rows[name])
        print(f"{path.name}: {len(data.rows[name])} rows")


def main() -> None:
    # Imported here because generate_fraud reuses this module's helpers.
    from graphrag_banking.generate_fraud import FraudGenerator, write_fraud_csvs

    settings = load_settings()
    hero = load_hero_fixtures()
    generator = Generator(settings.data_seed, settings.demo_as_of, load_policy_facts())
    data = generator.run(hero)
    write_csvs(data)
    customer_ids = [row["customer_id"] for row in data.rows["customers"]]
    fraud = FraudGenerator(settings.data_seed, settings.demo_as_of)
    write_fraud_csvs(fraud.run(hero["fraud"], customer_ids))


if __name__ == "__main__":
    main()
