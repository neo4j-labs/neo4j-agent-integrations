"""Generate the loan fraud data and write CSVs to data/generated/fraud/.

Runs after the customer data with its own seeded random.Random, so the
customer CSVs stay byte-identical. Hero records come from the ``fraud``
section of hero_fixtures.yaml. Background records use IDs outside the hero
ranges and never link to a hero business or account. The background adds
legitimate shared links so the ring is not the only connected group:
registered agent and coworking addresses, families that share a home and a
phone, the Delgado family business group, and one-way supplier payments.
The CSV contract is in data/README.md.
"""

import csv
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

from graphrag_banking.config import GENERATED_DIR
from graphrag_banking.facts import CREDIT_TYPES, to_decimal
from graphrag_banking.generate_data import (
    CSV_COLUMNS,
    WINDOW_DAYS,
    business_day_on_or_before,
    fmt_amount,
    fmt_date,
    fmt_datetime,
)

FRAUD_DIR = GENERATED_DIR / "fraud"

# Volumes include the hero records.
NUM_BACKGROUND_BANKERS = 6
NUM_BUSINESSES = 250
NUM_LOANS = 300
NUM_APPLICATIONS = 100
NUM_COUNTERPARTIES = 60
NUM_COWORKING = 6
NUM_FAMILY_PAIRS = 15
# Share of background businesses that list the registered agent address.
REGISTERED_AGENT_SHARE = 0.88
APPROVAL_LIMIT = Decimal("500000.00")

# Background IDs. Hero IDs are RM-0x, FR-02, P-1xxx, B-1xxx, ADDR-1xxx,
# DEV-1xxx, L-1xxx, APP-1xxx, A-3xxx, CP-3xxx and T-3xxxx.
FIRST_BACKGROUND_BANKER = 11
FIRST_TRANSACTION = 90000

# The Delgado family runs three businesses together. It has no past losses and
# no money loops, so it is a connected group that is not a red flag.
FAMILY_PERSONS = [("P-5001", "Ana Delgado"), ("P-5002", "Marco Delgado")]
FAMILY_BUSINESSES = [
    ("B-5001", "Delgado Landscaping", "Landscaping", {"P-5001": 60, "P-5002": 40}),
    ("B-5002", "Delgado Nursery Supply", "Garden Supply", {"P-5001": 40, "P-5002": 60}),
    ("B-5003", "Delgado Stone & Garden", "Landscaping", {"P-5001": 50, "P-5002": 50}),
]

# Background names may not contain a hero name, so a name search for a hero
# client never matches a background record.
HERO_NAME_TOKENS = frozenset(
    {
        "Becker",
        "Brightline",
        "Castillo",
        "Crestline",
        "Delgado",
        "Hale",
        "Harbor",
        "Holloway",
        "Keystone",
        "Kimball",
        "Lakeview",
        "Okafor",
        "Ortega",
        "Patel",
        "Pratt",
        "Price",
        "Romero",
        "Summit",
        "Vance",
        "Whitfield",
    }
)

INDUSTRIES = [
    "Construction",
    "Restaurant",
    "Retail",
    "Dental Practice",
    "Accounting",
    "Trucking",
    "Auto Repair",
    "Landscaping",
    "Manufacturing",
    "Software",
    "Wholesale",
    "Physical Therapy",
]
COUNTERPARTY_CATEGORIES = ["Customer", "Supplies", "Payroll", "Rent", "Utilities"]
LOAN_TYPES = ["TERM_LOAN", "BUSINESS_LINE", "EQUIPMENT", "COMMERCIAL_REAL_ESTATE"]
LOAN_STATUS_WEIGHTS = {"ACTIVE": 75, "PAID_OFF": 22, "WRITTEN_OFF": 3}
APPLICATION_STATUS_WEIGHTS = {
    "SUBMITTED": 20,
    "IN_REVIEW": 30,
    "APPROVED": 40,
    "DECLINED": 10,
}
BACKGROUND_CITIES = [
    ("Chicago", "IL"),
    ("Naperville", "IL"),
    ("Schaumburg", "IL"),
    ("Oak Park", "IL"),
    ("Skokie", "IL"),
    ("Milwaukee", "WI"),
    ("Gary", "IN"),
]

FRAUD_CSV_COLUMNS = {
    "bankers": ["banker_id", "name", "role", "approval_limit"],
    "fraud_reviewers": ["reviewer_id", "name"],
    "persons": ["person_id", "name"],
    "businesses": ["business_id", "name", "industry", "registered_on"],
    "phones": ["number"],
    "emails": ["address"],
    "addresses": ["address_id", "line1", "city", "state", "kind"],
    "devices": ["device_id", "first_seen"],
    "loans": [
        "loan_id",
        "type",
        "principal",
        "balance",
        "status",
        "opened_date",
        "closed_date",
    ],
    "loan_applications": [
        "application_id",
        "type",
        "amount",
        "stated_annual_revenue",
        "submitted_at",
        "status",
    ],
    "accounts": CSV_COLUMNS["accounts"],
    "transactions": CSV_COLUMNS["transactions"],
    "counterparties": CSV_COLUMNS["counterparties"],
    "rel_manages_customer": ["banker_id", "customer_id"],
    "rel_manages_business": ["banker_id", "business_id"],
    "rel_person_owns": ["person_id", "business_id", "percent"],
    "rel_business_owns": ["owner_business_id", "business_id", "percent"],
    "rel_director_of": ["person_id", "business_id"],
    "rel_person_has_phone": ["person_id", "number"],
    "rel_business_has_phone": ["business_id", "number"],
    "rel_person_has_email": ["person_id", "address"],
    "rel_business_has_email": ["business_id", "address"],
    "rel_person_has_address": ["person_id", "address_id"],
    "rel_business_has_address": ["business_id", "address_id"],
    "rel_business_holds": ["business_id", "account_id", "role"],
    "rel_applied_for": ["business_id", "application_id"],
    "rel_submitted_from": ["application_id", "device_id"],
    "rel_borrower_on": ["business_id", "loan_id"],
    "rel_has_transaction": ["account_id", "transaction_id"],
    "rel_paid_to": ["transaction_id", "counterparty_id"],
    "rel_received_from": ["transaction_id", "counterparty_id"],
    "rel_to_account": ["transaction_id", "account_id"],
}


@dataclass
class Party:
    """A person or business with its contact links, before it becomes rows."""

    party_id: str
    name: str
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)


@dataclass
class FraudDataset:
    rows: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


class FraudGenerator:
    def __init__(self, seed: int, as_of: date) -> None:
        # A separate stream, so adding fraud data never shifts customer data.
        self.rng = random.Random(f"fraud-{seed}")
        self.fake = Faker("en_US")
        self.fake.seed_instance(seed + 1)
        self.as_of = as_of
        self.window_start = as_of - timedelta(days=WINDOW_DAYS)
        self.data = FraudDataset()
        self.persons: list[Party] = []
        self.businesses: list[Party] = []
        self.used_names: set[str] = set()
        self.next_phone = 1000
        self.next_address = 6000
        self.next_txn = FIRST_TRANSACTION

    # ---- helpers -----------------------------------------------------------

    def money(self, low: float, high: float) -> Decimal:
        return to_decimal(round(self.rng.uniform(low, high), 2))

    def unique_name(self, make: Any) -> str:
        while True:
            name = make()
            tokens = set(re.findall(r"[A-Za-z]+", name))
            if name not in self.used_names and not tokens & HERO_NAME_TOKENS:
                self.used_names.add(name)
                return name

    def new_phone(self) -> str:
        self.next_phone += 1
        return f"+1-312-555-{self.next_phone - 1:04d}"

    def new_address(self, kind: str) -> str:
        self.next_address += 1
        address_id = f"ADDR-{self.next_address - 1}"
        city, state = self.rng.choice(BACKGROUND_CITIES)
        self.data.rows["addresses"].append(
            {
                "address_id": address_id,
                "line1": self.fake.street_address(),
                "city": city,
                "state": state,
                "kind": kind,
            }
        )
        return address_id

    def window_day(self) -> date:
        offset = self.rng.randint(1, WINDOW_DAYS - 1)
        return business_day_on_or_before(self.window_start + timedelta(days=offset))

    def add_txn(
        self,
        account_id: str,
        txn_type: str,
        amount: Decimal,
        day: date,
        description: str,
        counterparty_id: str | None = None,
        to_account_id: str | None = None,
    ) -> None:
        txn_id = f"T-{self.next_txn}"
        self.next_txn += 1
        hour = 12 if txn_type in CREDIT_TYPES else 13
        moment = datetime.combine(day, time(hour, 0), tzinfo=UTC)
        self.add_txn_row(
            {
                "transaction_id": txn_id,
                "account_id": account_id,
                "type": txn_type,
                "amount": amount,
                "initiated_at": fmt_datetime(moment),
                "status": "POSTED",
                "channel": "ONLINE" if txn_type == "WIRE_OUT" else "ACH",
                "description": description,
                "counterparty_id": counterparty_id,
                "to_account_id": to_account_id,
            }
        )

    def add_txn_row(self, txn: dict[str, Any]) -> None:
        """Split one transaction into its node row and relationship rows."""
        rows = self.data.rows
        posted = txn["initiated_at"] if txn["status"] == "POSTED" else None
        rows["transactions"].append(
            {
                "transaction_id": txn["transaction_id"],
                "type": txn["type"],
                "amount": fmt_amount(to_decimal(txn["amount"])),
                "currency": "USD",
                "initiated_at": txn["initiated_at"],
                "posted_at": posted,
                "available_on": None,
                "status": txn["status"],
                "channel": txn["channel"],
                "description": txn["description"],
            }
        )
        rows["rel_has_transaction"].append(
            {"account_id": txn["account_id"], "transaction_id": txn["transaction_id"]}
        )
        if txn["counterparty_id"]:
            rel = "rel_received_from" if txn["type"] in CREDIT_TYPES else "rel_paid_to"
            rows[rel].append(
                {
                    "transaction_id": txn["transaction_id"],
                    "counterparty_id": txn["counterparty_id"],
                }
            )
        if txn["to_account_id"]:
            rows["rel_to_account"].append(
                {
                    "transaction_id": txn["transaction_id"],
                    "account_id": txn["to_account_id"],
                }
            )

    # ---- hero records ------------------------------------------------------

    def hero(self, hero: dict[str, Any]) -> dict[str, Decimal]:
        """Copy the hero records. Returns each hero account's opening balance."""
        rows = self.data.rows
        rows["bankers"].extend(
            b | {"approval_limit": fmt_amount(to_decimal(b["approval_limit"]))}
            for b in hero["bankers"]
        )
        rows["fraud_reviewers"].extend(hero["fraud_reviewers"])
        rows["addresses"].extend(hero["addresses"])
        rows["counterparties"].extend(hero["counterparties"])
        rows["devices"].extend(hero["devices"])
        for person in hero["persons"]:
            self.persons.append(
                Party(
                    person["person_id"],
                    person["name"],
                    person["phones"],
                    person["emails"],
                    person["addresses"],
                )
            )
        for business in hero["businesses"]:
            rows["businesses"].append(
                {
                    "business_id": business["business_id"],
                    "name": business["name"],
                    "industry": business["industry"],
                    "registered_on": business["registered_on"],
                }
            )
            rows["rel_manages_business"].append(
                {
                    "banker_id": business["banker_id"],
                    "business_id": business["business_id"],
                }
            )
            self.businesses.append(
                Party(
                    business["business_id"],
                    business["name"],
                    business["phones"],
                    business["emails"],
                    business["addresses"],
                )
            )
        for owner in hero["ownership"]:
            self.add_owner(owner["owner_id"], owner["business_id"], owner["percent"])
        rows["rel_director_of"].extend(hero["directors"])
        for loan in hero["loans"]:
            self.add_loan({k: v for k, v in loan.items() if k != "business_id"})
            rows["rel_borrower_on"].append(
                {"business_id": loan["business_id"], "loan_id": loan["loan_id"]}
            )
        for app in hero["applications"]:
            self.add_application(app)
        for account in hero["accounts"]:
            self.add_account(account, account["business_id"])
        for txn in hero["transactions"]:
            self.add_txn_row(txn)
        self.used_names.update(p.name for p in self.persons + self.businesses)
        return {
            a["account_id"]: to_decimal(a["opening_balance"]) for a in hero["accounts"]
        }

    def add_owner(self, owner_id: str, business_id: str, percent: int) -> None:
        if owner_id.startswith("B-"):
            self.data.rows["rel_business_owns"].append(
                {
                    "owner_business_id": owner_id,
                    "business_id": business_id,
                    "percent": percent,
                }
            )
        else:
            self.data.rows["rel_person_owns"].append(
                {"person_id": owner_id, "business_id": business_id, "percent": percent}
            )

    def add_loan(self, loan: dict[str, Any]) -> None:
        self.data.rows["loans"].append(
            loan
            | {
                "principal": fmt_amount(to_decimal(loan["principal"])),
                "balance": fmt_amount(to_decimal(loan["balance"])),
            }
        )

    def add_application(self, app: dict[str, Any]) -> None:
        rows = self.data.rows
        rows["loan_applications"].append(
            {
                "application_id": app["application_id"],
                "type": app["type"],
                "amount": fmt_amount(to_decimal(app["amount"])),
                "stated_annual_revenue": fmt_amount(
                    to_decimal(app["stated_annual_revenue"])
                ),
                "submitted_at": app["submitted_at"],
                "status": app["status"],
            }
        )
        rows["rel_applied_for"].append(
            {"business_id": app["business_id"], "application_id": app["application_id"]}
        )
        rows["rel_submitted_from"].append(
            {"application_id": app["application_id"], "device_id": app["device_id"]}
        )

    def add_account(self, account: dict[str, Any], business_id: str) -> None:
        self.data.rows["accounts"].append(
            {k: v for k, v in account.items() if k in CSV_COLUMNS["accounts"]}
        )
        self.data.rows["rel_business_holds"].append(
            {
                "business_id": business_id,
                "account_id": account["account_id"],
                "role": "PRIMARY",
            }
        )

    # ---- background population -----------------------------------------

    def bankers(self, customer_ids: list[str]) -> list[str]:
        ids = []
        for i in range(NUM_BACKGROUND_BANKERS):
            banker_id = f"RM-{FIRST_BACKGROUND_BANKER + i}"
            ids.append(banker_id)
            self.data.rows["bankers"].append(
                {
                    "banker_id": banker_id,
                    "name": self.unique_name(self.fake.name),
                    "role": "RELATIONSHIP_MANAGER",
                    "approval_limit": fmt_amount(APPROVAL_LIMIT),
                }
            )
        self.data.rows["fraud_reviewers"].append(
            {"reviewer_id": "FR-01", "name": self.unique_name(self.fake.name)}
        )
        for customer_id in customer_ids:
            self.data.rows["rel_manages_customer"].append(
                {"banker_id": self.rng.choice(ids), "customer_id": customer_id}
            )
        return ids

    def background_person(self, person_id: str, name: str | None = None) -> Party:
        name = name or self.unique_name(
            lambda: f"{self.fake.first_name()} {self.fake.last_name()}"
        )
        person = Party(person_id, name, [self.new_phone()], [])
        if self.rng.random() < 0.6:
            first, last = name.split()[0], name.split()[-1]
            person.emails.append(
                f"{_slug(first)}.{_slug(last)}{person_id[2:]}@example.net"
            )
        person.addresses.append(self.new_address("HOME"))
        self.persons.append(person)
        return person

    def background_businesses(self, banker_ids: list[str]) -> list[str]:
        rows = self.data.rows
        coworking = [self.new_address("COWORKING") for _ in range(NUM_COWORKING)]
        family = [self.background_person(pid, name) for pid, name in FAMILY_PERSONS]
        # The Delgados share a home and a phone.
        family[1].phones = family[0].phones
        family[1].addresses = family[0].addresses

        plan = list(FAMILY_BUSINESSES)
        family_ids = {b[0] for b in FAMILY_BUSINESSES}
        next_person = 5000 + len(FAMILY_PERSONS) + 1
        num_background = NUM_BUSINESSES - len(self.businesses)
        for i in range(len(FAMILY_BUSINESSES), num_background):
            owners = (
                {f"P-{next_person}": 100}
                if self.rng.random() < 0.7
                else {f"P-{next_person}": 50, f"P-{next_person + 1}": 50}
            )
            next_person += len(owners)
            for pid in owners:
                self.background_person(pid)
            name = self.unique_name(self.fake.company)
            plan.append((f"B-{5001 + i}", name, self.rng.choice(INDUSTRIES), owners))

        sole_owners = []
        ids = []
        for business_id, name, industry, owners in plan:
            ids.append(business_id)
            rows["businesses"].append(
                {
                    "business_id": business_id,
                    "name": name,
                    "industry": industry,
                    "registered_on": fmt_date(
                        self.fake.date_between(date(2000, 1, 1), date(2025, 12, 31))
                    ),
                }
            )
            rows["rel_manages_business"].append(
                {"banker_id": self.rng.choice(banker_ids), "business_id": business_id}
            )
            for owner_id, percent in owners.items():
                self.add_owner(owner_id, business_id, percent)
                rows["rel_director_of"].append(
                    {"person_id": owner_id, "business_id": business_id}
                )
            if len(owners) == 1 and business_id not in family_ids:
                sole_owners.append(next(iter(owners)))

            business = Party(business_id, name, [self.new_phone()])
            business.emails.append(f"office@{_slug(name)}{business_id[2:]}.example")
            if self.rng.random() < 0.6:
                business.addresses.append(self.new_address("OFFICE"))
            else:
                business.addresses.append(self.rng.choice(coworking))
            if self.rng.random() < REGISTERED_AGENT_SHARE:
                business.addresses.append("ADDR-1900")
            self.businesses.append(business)

        # Families: the second owner shares the first one's home and phone.
        by_id = {p.party_id: p for p in self.persons}
        chosen = self.rng.sample(sole_owners, 2 * NUM_FAMILY_PAIRS)
        for first, second in zip(chosen[::2], chosen[1::2], strict=True):
            by_id[second].phones = by_id[first].phones
            by_id[second].addresses = by_id[first].addresses
        return ids

    def contact_rows(self) -> None:
        """Write Phone, Email and HAS_* rows for every person and business."""
        rows = self.data.rows
        phones: dict[str, None] = {}
        emails: dict[str, None] = {}
        for prefix, parties, key in (
            ("person", self.persons, "person_id"),
            ("business", self.businesses, "business_id"),
        ):
            if prefix == "person":
                rows["persons"].extend(
                    {"person_id": p.party_id, "name": p.name} for p in parties
                )
            for party in parties:
                for number in party.phones:
                    phones[number] = None
                    rows[f"rel_{prefix}_has_phone"].append(
                        {key: party.party_id, "number": number}
                    )
                for address in party.emails:
                    emails[address] = None
                    rows[f"rel_{prefix}_has_email"].append(
                        {key: party.party_id, "address": address}
                    )
                for address_id in party.addresses:
                    rows[f"rel_{prefix}_has_address"].append(
                        {key: party.party_id, "address_id": address_id}
                    )
        rows["phones"] = [{"number": n} for n in phones]
        rows["emails"] = [{"address": a} for a in emails]
        # A family member's own home was replaced by the shared one. Drop it.
        used = {
            r["address_id"]
            for name in ("rel_person_has_address", "rel_business_has_address")
            for r in rows[name]
        }
        rows["addresses"] = [a for a in rows["addresses"] if a["address_id"] in used]

    def background_counterparties(self) -> list[str]:
        ids = []
        for i in range(NUM_COUNTERPARTIES):
            counterparty_id = f"CP-{7000 + i}"
            ids.append(counterparty_id)
            self.data.rows["counterparties"].append(
                {
                    "counterparty_id": counterparty_id,
                    "name": self.unique_name(self.fake.company),
                    "kind": "BUSINESS",
                    "category": self.rng.choice(COUNTERPARTY_CATEGORIES),
                    "country": "US",
                }
            )
        return ids

    def background_accounts(
        self, business_ids: list[str], counterparty_ids: list[str]
    ) -> dict[str, str]:
        """One operating account per business, with deposits and payments.

        Supplier payments between clients only go from a lower business index
        to a higher one, so the background has no money loops.
        """
        account_of = {bid: f"A-{7000 + i}" for i, bid in enumerate(business_ids)}
        registered = {
            r["business_id"]: r["registered_on"] for r in self.data.rows["businesses"]
        }
        name_of = {b.party_id: b.name for b in self.businesses}
        family_ids = [b[0] for b in FAMILY_BUSINESSES]
        for i, business_id in enumerate(business_ids):
            account_id = account_of[business_id]
            opened = max(date.fromisoformat(registered[business_id]), date(2005, 1, 1))
            self.add_account(
                {
                    "account_id": account_id,
                    "nickname": "Operating",
                    "currency": "USD",
                    "status": "OPEN",
                    "opened_date": fmt_date(opened),
                },
                business_id,
            )
            for _ in range(self.rng.randint(4, 10)):
                self.add_txn(
                    account_id,
                    "ACH_IN",
                    self.money(2000, 40000),
                    self.window_day(),
                    "Customer payment",
                    counterparty_id=self.rng.choice(counterparty_ids),
                )
            for _ in range(self.rng.randint(2, 6)):
                self.add_txn(
                    account_id,
                    "ACH_OUT",
                    self.money(1000, 25000),
                    self.window_day(),
                    self.rng.choice(["Payroll", "Supplies", "Rent"]),
                    counterparty_id=self.rng.choice(counterparty_ids),
                )
            later = business_ids[i + 1 :]
            if business_id in family_ids[:-1]:
                payees = [family_ids[family_ids.index(business_id) + 1]]
            elif later and self.rng.random() < 0.35:
                payees = self.rng.sample(later, min(len(later), self.rng.randint(1, 2)))
            else:
                payees = []
            for payee in payees:
                txn_type = self.rng.choice(["WIRE_OUT", "ACH_OUT"])
                self.add_txn(
                    account_id,
                    txn_type,
                    self.money(1000, 30000),
                    self.window_day(),
                    f"Payment to {name_of[payee]} - invoice",
                    to_account_id=account_of[payee],
                )
        return account_of

    def background_loans(self, business_ids: list[str]) -> None:
        family_ids = {b[0] for b in FAMILY_BUSINESSES}
        for i in range(NUM_LOANS - len(self.data.rows["loans"])):
            business_id = self.rng.choice(business_ids)
            status = self.rng.choices(
                list(LOAN_STATUS_WEIGHTS), list(LOAN_STATUS_WEIGHTS.values())
            )[0]
            if business_id in family_ids and status == "WRITTEN_OFF":
                status = "ACTIVE"
            principal = to_decimal(self.rng.randrange(25, 751) * 1000)
            opened = self.fake.date_between(date(2016, 1, 1), date(2026, 6, 30))
            closed = None
            balance = Decimal("0.00")
            if status == "ACTIVE":
                balance = to_decimal(principal * Decimal(self.rng.uniform(0.2, 0.95)))
            else:
                closed = self.fake.date_between(opened + timedelta(days=90), self.as_of)
                if status == "WRITTEN_OFF":
                    balance = to_decimal(
                        principal * Decimal(self.rng.uniform(0.3, 0.8))
                    )
            loan_id = f"L-{5001 + i}"
            self.add_loan(
                {
                    "loan_id": loan_id,
                    "type": self.rng.choice(LOAN_TYPES),
                    "principal": principal,
                    "balance": balance,
                    "status": status,
                    "opened_date": fmt_date(opened),
                    "closed_date": fmt_date(closed),
                }
            )
            self.data.rows["rel_borrower_on"].append(
                {"business_id": business_id, "loan_id": loan_id}
            )

    def background_applications(
        self, business_ids: list[str], account_of: dict[str, str]
    ) -> None:
        """Applications from distinct businesses, each on its own device."""
        rows = self.data.rows
        deposits: dict[str, Decimal] = defaultdict(Decimal)
        txn_account = {
            r["transaction_id"]: r["account_id"] for r in rows["rel_has_transaction"]
        }
        for txn in rows["transactions"]:
            if txn["type"] in CREDIT_TYPES:
                deposits[txn_account[txn["transaction_id"]]] += Decimal(txn["amount"])
        count = NUM_APPLICATIONS - len(rows["loan_applications"])
        for i, business_id in enumerate(self.rng.sample(business_ids, count)):
            day = self.window_day()
            device_id = f"DEV-{5001 + i}"
            rows["devices"].append(
                {"device_id": device_id, "first_seen": fmt_date(day)}
            )
            revenue = deposits[account_of[business_id]] * 4
            stated = to_decimal(
                round(revenue * Decimal(self.rng.uniform(0.95, 1.1)), -3)
            )
            moment = datetime.combine(day, time(self.rng.randint(13, 21)), tzinfo=UTC)
            self.add_application(
                {
                    "application_id": f"APP-{5001 + i}",
                    "business_id": business_id,
                    "device_id": device_id,
                    "type": self.rng.choice(LOAN_TYPES),
                    "amount": to_decimal(self.rng.randrange(25, 501) * 1000),
                    "stated_annual_revenue": stated,
                    "submitted_at": fmt_datetime(moment),
                    "status": self.rng.choices(
                        list(APPLICATION_STATUS_WEIGHTS),
                        list(APPLICATION_STATUS_WEIGHTS.values()),
                    )[0],
                }
            )

    def balances(self, hero_opening: dict[str, Decimal]) -> None:
        """Set ledger and available balances from the posted transactions.

        A transfer is a debit on its own account and a credit on the account it
        points to. Background opening balances cover any net outflow.
        """
        rows = self.data.rows
        net: dict[str, Decimal] = defaultdict(Decimal)
        txn_account = {
            r["transaction_id"]: r["account_id"] for r in rows["rel_has_transaction"]
        }
        to_account = {
            r["transaction_id"]: r["account_id"] for r in rows["rel_to_account"]
        }
        for txn in rows["transactions"]:
            amount = Decimal(txn["amount"])
            txn_id = txn["transaction_id"]
            sign = 1 if txn["type"] in CREDIT_TYPES else -1
            net[txn_account[txn_id]] += sign * amount
            if txn_id in to_account:
                net[to_account[txn_id]] += amount
        for account in rows["accounts"]:
            account_id = account["account_id"]
            opening = hero_opening.get(account_id)
            if opening is None:
                opening = self.money(20000, 150000) + max(Decimal(0), -net[account_id])
            ledger = fmt_amount(opening + net[account_id])
            account["ledger_balance"] = ledger
            account["available_balance"] = ledger

    def run(self, hero: dict[str, Any], customer_ids: list[str]) -> FraudDataset:
        hero_opening = self.hero(hero)
        banker_ids = self.bankers(customer_ids)
        business_ids = self.background_businesses(banker_ids)
        self.contact_rows()
        counterparty_ids = self.background_counterparties()
        account_of = self.background_accounts(business_ids, counterparty_ids)
        self.background_loans(business_ids)
        self.background_applications(business_ids, account_of)
        self.balances(hero_opening)
        return self.data


def write_fraud_csvs(data: FraudDataset) -> None:
    FRAUD_DIR.mkdir(parents=True, exist_ok=True)
    for name, columns in FRAUD_CSV_COLUMNS.items():
        path = FRAUD_DIR / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data.rows[name])
        print(f"fraud/{path.name}: {len(data.rows[name])} rows")
