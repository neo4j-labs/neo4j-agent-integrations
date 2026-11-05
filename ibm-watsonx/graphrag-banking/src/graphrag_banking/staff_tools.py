"""Banker-scoped tools for the credit and fraud specialists in the loan fraud demo.

Portability rule: this module imports only the ``neo4j`` driver, so the tools
move into watsonx Orchestrate unchanged. It repeats the small helpers it needs
from ``tools.py`` instead of importing them.

Each tool takes a ``StaffContext`` first, then the arguments the model sees.
The context carries the signed-in banker, so the model never supplies one.
Every query that returns details about a business starts from
``(:Banker {banker_id: $banker_id})-[:MANAGES]->(:Business)``. A business
outside the banker's book returns an error. Other businesses and people reached
from the banker's client show up by name and link only, with no balances or
transactions.

Every rule a tool reports comes back with its policy name and the text of the
policy section it links to through ``FROM_CHUNK``.
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import neo4j
from neo4j.time import Date, DateTime

_CREDIT_TYPES = ["CHECK_DEPOSIT", "ACH_IN", "WIRE_IN"]
_OPEN_APPLICATION_STATUSES = ["SUBMITTED", "IN_REVIEW"]
# Matches build_groups.EXCLUDED_ADDRESS_KINDS. FRAUD-REG-AGENT excludes them.
_EXCLUDED_ADDRESS_KINDS = ["REGISTERED_AGENT", "COWORKING"]
_LINE_TYPE = "BUSINESS_LINE"
# Verified revenue comes from this many days of deposits.
_REVENUE_DAYS = 90
# A 360-day banking year, so 90 days of deposits times four is a year.
_DAYS_PER_YEAR = 360
_MAX_LOOP_HOPS = 4
_CLIENT_RESULTS = 10
# Dollar fields the model quotes to the banker. Formatted last, so the rule
# checks still run on numbers.
_MONEY_FIELDS = frozenset(
    {
        "amount",
        "principal",
        "stated_annual_revenue",
        "approval_limit",
        "total_deposits",
        "circular_deposits",
        "deposits_outside_loops",
        "sent_into_loops",
        "returned_amount",
        "sent_amount",
        "annual_revenue_from_deposits",
        "annual_revenue_without_loops",
        "verified_annual_revenue",
        "max_line",
        "max_line_without_loops",
    }
)
# Settings that only some rules have. A rule leaves out the ones it lacks and
# returns every other field, with None when the graph has no value.
_RULE_SETTINGS = frozenset(
    {"percent", "years", "lookback_days", "amount", "min_red_flags"}
)


@dataclass(frozen=True)
class StaffContext:
    """Settings the staff tools need that the model must not supply.

    Attributes:
        driver: Open Neo4j driver.
        database: Neo4j database name.
        banker_id: The signed-in banker. Every detail query checks MANAGES.
        as_of: Today's date for the demo.
        executed: Cypher run by the tools, in order. Used for the trace.
    """

    driver: neo4j.Driver
    database: str
    banker_id: str
    as_of: date
    executed: list[str] = field(default_factory=list)


def find_my_client(context: StaffContext, name: str) -> dict[str, Any]:
    """Find businesses in your book by name, with their loan applications.

    Use this first to turn a business name into a business ID. Partial names
    match, such as "Ortega". A matching business in another banker's book is
    listed under ``outside_my_book`` by name only, with its banker and any of
    your clients it shares a connected group with. Its details cannot be shown.

    Args:
        name: The business name or part of it.

    Returns:
        Matching clients in your book, each with its applications, and
        matching businesses outside your book.
    """
    if not name.strip():
        raise ValueError("Give a business name to search for")
    records = _run(context, _FIND_MY_CLIENT, name=name.strip(), limit=_CLIENT_RESULTS)
    return {
        "clients": [r["business"] for r in records if r["in_my_book"]],
        "outside_my_book": [r["business"] for r in records if not r["in_my_book"]],
    }


def get_application(context: StaffContext, application_id: str) -> dict[str, Any]:
    """Get one loan application with its amount, stated revenue, and status.

    Args:
        application_id: An application ID from find_my_client.

    Returns:
        The application and its business, or an error if the application is
        not from a client in your book.
    """
    records = _run(context, _GET_APPLICATION, application_id=application_id)
    if not records:
        return {"error": f"No application {application_id} from a client in your book."}
    return _format_money(records[0])


def check_lending_rules(context: StaffContext, application_id: str) -> dict[str, Any]:
    """Check a loan application against the lending and approval rules.

    Checks ``LEND-BUSLINE-REV``, the size limit for a business line against
    verified revenue, and ``AUTH-RM-LIMIT``, who may approve the request.
    Verified revenue is the last 90 days of posted deposits, annualized over a
    360-day year. Stated revenue is shown for comparison. This check does not
    look for fraud red flags.

    Args:
        application_id: An application ID from find_my_client.

    Returns:
        The application, the revenue figures, and each rule with whether it
        passed, who must approve, and its policy text. Returns an error if the
        application is not from a client in your book.
    """
    rules = _rules(context, "LEND-BUSLINE-REV", "AUTH-RM-LIMIT")
    date_to = context.as_of
    date_from = date_to - timedelta(days=_REVENUE_DAYS)
    records = _run(
        context,
        _CHECK_LENDING_RULES,
        application_id=application_id,
        date_from=date_from,
        date_to=date_to,
        credit_types=_CREDIT_TYPES,
    )
    if not records:
        return {"error": f"No application {application_id} from a client in your book."}
    row = records[0]
    application = row["application"]
    revenue = _annualize(row["total_deposits"], _REVENUE_DAYS)
    line = _check_line(application, revenue, rules["LEND-BUSLINE-REV"])
    authority = _check_authority(
        application["amount"],
        row["banker"],
        rules["AUTH-RM-LIMIT"],
        row["open_fraud_referral"],
    )
    return _format_money(
        {
            "application": application,
            "business": row["business"],
            "revenue": {
                "deposits_from": date_from.isoformat(),
                "deposits_to": date_to.isoformat(),
                "total_deposits": row["total_deposits"],
                "annual_revenue_from_deposits": revenue,
                "stated_annual_revenue": application["stated_annual_revenue"],
            },
            "open_fraud_referral": row["open_fraud_referral"],
            "approver": authority["approver"],
            "rules": [line, authority],
        }
    )


def get_beneficial_owners(context: StaffContext, business_id: str) -> dict[str, Any]:
    """Find the real owners of a business, however deep the ownership chain.

    Follows ownership chains of any length up to the business. A person who
    owns a holding company that owns the business is an owner too. The
    effective share multiplies the shares along each chain and adds the chains
    together. Returns every owner at the ``KYC-UBO-25`` threshold or above.
    Each owner lists any written-off loan of a business they own, and whether
    it falls in the ``FRAUD-PRIOR-LOSS`` look-back period. Owners outside your
    book are shown by name and link only.

    Args:
        business_id: A business ID from find_my_client.

    Returns:
        The beneficial owners with their chains, effective shares, and
        written-off loans, the red flags matched, and the rules with their
        policy text. Returns an error if the business is not in your book.
    """
    rules = _rules(context, "KYC-UBO-25", "FRAUD-PRIOR-LOSS")
    years = rules["FRAUD-PRIOR-LOSS"]["years"]
    loss_since = context.as_of.replace(year=context.as_of.year - years)
    records = _run(
        context, _BENEFICIAL_OWNERS, business_id=business_id, loss_since=loss_since
    )
    if not records:
        return {"error": f"No business {business_id} in your book."}
    row = records[0]
    owners = _beneficial_owners(row["owners"], rules["KYC-UBO-25"]["percent"])
    prior_loss = any(
        loan["within_lookback"]
        for owner in owners
        for loan in owner["written_off_loans"]
    )
    return _format_money(
        {
            "business": row["business"],
            "beneficial_owners": owners,
            "red_flags": ["FRAUD-PRIOR-LOSS"] if prior_loss else [],
            "rules": list(rules.values()),
        }
    )


def get_connected_group(context: StaffContext, business_id: str) -> dict[str, Any]:
    """Show the connected group a business is in and what links its members.

    Groups are found ahead of time by Neo4j Graph Data Science. They join
    people and businesses that share a phone, email, device, or address, or
    are linked by ownership or a director. ``centrality`` scores how often a
    member sits between the others, so the highest score is the center of the
    group. ``shared_identifiers`` lists each identifier used by more than one
    party, with the applicants among them, for ``FRAUD-SHARED-ID``.
    ``excluded_links`` lists registered agent and coworking addresses, which
    ``FRAUD-REG-AGENT`` says are not a red flag on their own. Members outside
    your book are shown by name and link only. A shared home address has a
    null ``value``, so only who shares it is shown.

    Args:
        business_id: A business ID from find_my_client.

    Returns:
        The group, its members, shared identifiers, ownership and director
        links, excluded links, the red flags matched, and the rules with their
        policy text. ``group`` is null when the business is in no group.
        Returns an error if the business is not in your book.
    """
    rules = _rules(context, "FRAUD-SHARED-ID", "FRAUD-REG-AGENT")
    records = _run(
        context,
        _CONNECTED_GROUP,
        business_id=business_id,
        excluded_kinds=_EXCLUDED_ADDRESS_KINDS,
        open_statuses=_OPEN_APPLICATION_STATUSES,
    )
    if not records:
        return {"error": f"No business {business_id} in your book."}
    row = records[0]
    members = sorted(
        row["members"], key=lambda m: (-(m["centrality"] or 0.0), m["name"])
    )
    shared = [
        {key: value for key, value in i.items() if key in _SHARED_FIELDS}
        for i in row["identifiers"]
        if not i["excluded"]
    ]
    excluded = [
        {key: value for key, value in i.items() if key in _EXCLUDED_FIELDS}
        for i in row["identifiers"]
        if i["excluded"]
    ]
    shared_id = _shares_identifiers(shared, row["directors"])
    return {
        "business": row["business"],
        "group": row["group"],
        "most_central": members[0]["name"] if row["group"] else None,
        "members": members,
        "shared_identifiers": shared,
        "ownership_links": row["ownership"],
        "director_links": row["directors"],
        "excluded_links": excluded,
        "red_flags": ["FRAUD-SHARED-ID"] if shared_id else [],
        "rules": list(rules.values()),
    }


def find_circular_flows(
    context: StaffContext,
    business_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Find money that left a business and came back to it as deposits.

    A loop is a transfer into the business whose sender was reached earlier by
    a chain of transfers out of the business, each after the one before. The
    chain can pass through any number of other businesses, up to four hops.
    Loop deposits are a ``FRAUD-CIRCULAR-FLOW`` red flag and do not count as
    verified revenue, so the result also gives the revenue and the largest
    business line under ``LEND-BUSLINE-REV`` with the loops removed. Other
    businesses on a route are shown by name only.

    Args:
        business_id: A business ID from find_my_client.
        date_from: First day, YYYY-MM-DD. Defaults to the rule's 90-day
            look-back.
        date_to: Last day, YYYY-MM-DD. Defaults to today.

    Returns:
        Total deposits, loop deposits and their share, each loop with its
        route, the red flags matched, and the rules with their policy text.
        Returns an error if the business is not in your book.
    """
    rules = _rules(context, "FRAUD-CIRCULAR-FLOW", "LEND-BUSLINE-REV")
    end = _parse_date(date_to) or context.as_of
    lookback = rules["FRAUD-CIRCULAR-FLOW"]["lookback_days"]
    start = _parse_date(date_from) or end - timedelta(days=lookback)
    if start >= end:
        raise ValueError("date_from must be before date_to")
    records = _run(
        context,
        _CIRCULAR_FLOWS,
        business_id=business_id,
        date_from=start,
        date_to=end,
        credit_types=_CREDIT_TYPES,
    )
    if not records:
        return {"error": f"No business {business_id} in your book."}
    row = records[0]
    summary = _summarize_loops(
        row["loops"],
        row["total_deposits"],
        (end - start).days,
        rules["LEND-BUSLINE-REV"]["percent"],
    )
    return _format_money(
        {
            "business": row["business"],
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            **summary,
            "loops": sorted(row["loops"], key=lambda loop: loop["returned_on"]),
            "red_flags": ["FRAUD-CIRCULAR-FLOW"] if row["loops"] else [],
            "rules": list(rules.values()),
        }
    )


def screen_business(context: StaffContext, business_id: str) -> dict[str, Any]:
    """Run every fraud check on a business in one call.

    Runs the beneficial owner, connected group, and circular flow checks on the
    business. Each key holds that check's full result. ``beneficial_owners``
    gives the real owners, their ownership chains and effective shares, and any
    written-off loans for ``KYC-UBO-25`` and ``FRAUD-PRIOR-LOSS``.
    ``connected_group`` gives the group, its members and centrality, the shared
    identifiers for ``FRAUD-SHARED-ID``, and the registered agent and coworking
    addresses that ``FRAUD-REG-AGENT`` excludes. ``circular_flows`` gives loop
    deposits over the 90-day look-back for ``FRAUD-CIRCULAR-FLOW``, with the
    revenue and largest business line once the loops are removed. Each result
    lists its own red flags and the rules with their policy text.

    Args:
        business_id: A business ID from find_my_client.

    Returns:
        ``beneficial_owners``, ``connected_group``, and ``circular_flows``.
        Returns an error if the business is not in your book.
    """
    if not _run(context, _CHECK_MY_BUSINESS, business_id=business_id):
        return {"error": f"No business {business_id} in your book."}
    return {
        "beneficial_owners": get_beneficial_owners(context, business_id),
        "connected_group": get_connected_group(context, business_id),
        "circular_flows": find_circular_flows(context, business_id),
    }


def _effective_percent(chains: list[list[float]]) -> float:
    """Multiply the percents along each chain, then add the chains together."""
    total = sum(math.prod(percent / 100 for percent in chain) for chain in chains)
    return round(total * 100, 2)


def _beneficial_owners(
    owners: list[dict[str, Any]], threshold: float
) -> list[dict[str, Any]]:
    """Add each chain's share and the effective share, keep owners at the
    threshold or above, and sort them by share."""
    result = []
    for owner in owners:
        chains = [
            {
                "path": chain["path"],
                "share_percent": _effective_percent([chain["percents"]]),
            }
            for chain in owner["chains"]
        ]
        effective = _effective_percent([chain["percents"] for chain in owner["chains"]])
        if effective >= threshold:
            result.append(owner | {"effective_percent": effective, "chains": chains})
    return sorted(
        result, key=lambda owner: (-owner["effective_percent"], owner["name"])
    )


def _annualize(amount: float, days: int) -> float:
    return round(amount * _DAYS_PER_YEAR / days, 2)


def _check_line(
    application: dict[str, Any], revenue: float, rule: dict[str, Any]
) -> dict[str, Any]:
    """Check ``LEND-BUSLINE-REV``, which applies to business lines only."""
    applies = application["type"] == _LINE_TYPE
    max_line = round(revenue * rule["percent"] / 100, 2)
    return rule | {
        "applies": applies,
        "verified_annual_revenue": revenue,
        "max_line": max_line,
        "passed": application["amount"] <= max_line if applies else None,
    }


def _check_authority(
    amount: float,
    banker: dict[str, Any],
    rule: dict[str, Any],
    open_referral: bool,
) -> dict[str, Any]:
    """Check ``AUTH-RM-LIMIT`` and name who must approve the request."""
    limit = min(banker["approval_limit"], rule["amount"])
    within = amount <= limit
    if open_referral:
        approver = "No one, while the fraud referral on it is open"
    elif within:
        approver = f"{banker['name']}, the relationship manager"
    else:
        approver = "The credit committee"
    return rule | {
        "applies": True,
        "approval_limit": limit,
        "passed": within and not open_referral,
        "approver": approver,
    }


def _shares_identifiers(
    identifiers: list[dict[str, Any]], directors: list[dict[str, Any]]
) -> bool:
    """Say whether two or more applicants share an identifier or a director."""
    if any(len(identifier["applicants"]) >= 2 for identifier in identifiers):
        return True
    applicants_by_director: dict[str, set[str]] = {}
    for link in directors:
        if link["business_has_open_application"]:
            applicants_by_director.setdefault(link["director"], set()).add(
                link["business"]
            )
    return any(len(names) >= 2 for names in applicants_by_director.values())


def _summarize_loops(
    loops: list[dict[str, Any]], total_deposits: float, days: int, percent: float
) -> dict[str, Any]:
    """Total the loop deposits and the revenue that is left without them.

    Two loops can start with the same transfer out, so each transfer out is
    counted once in ``sent_into_loops``.
    """
    circular = round(sum(loop["returned_amount"] for loop in loops), 2)
    sent = {loop["sent_transaction_id"]: loop["sent_amount"] for loop in loops}
    outside = round(total_deposits - circular, 2)
    revenue = _annualize(outside, days)
    share = round(100 * circular / total_deposits, 1) if total_deposits else 0.0
    return {
        "total_deposits": total_deposits,
        "circular_deposits": circular,
        "circular_share_percent": share,
        "deposits_outside_loops": outside,
        "sent_into_loops": round(sum(sent.values()), 2),
        "annual_revenue_without_loops": revenue,
        "max_line_without_loops": round(revenue * percent / 100, 2),
    }


def _rules(context: StaffContext, *codes: str) -> dict[str, dict[str, Any]]:
    """Fetch rules by code, in the order given, with their policy text."""
    records = _run(context, _RULES, codes=list(codes))
    found = {
        row["rule"]["rule_code"]: {
            k: v
            for k, v in row["rule"].items()
            if v is not None or k not in _RULE_SETTINGS
        }
        for row in records
    }
    missing = [code for code in codes if code not in found]
    if missing:
        raise LookupError(f"Rules missing from the graph: {', '.join(missing)}")
    return {code: found[code] for code in codes}


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Dates must be YYYY-MM-DD, got {value!r}") from error


def _run(context: StaffContext, query: str, **params: Any) -> list[dict[str, Any]]:
    context.executed.append(query.strip())
    records, _, _ = context.driver.execute_query(
        query,
        banker_id=context.banker_id,
        database_=context.database,
        routing_=neo4j.RoutingControl.READ,
        **params,
    )
    return [_plain(record.data()) for record in records]


def _plain(value: Any) -> Any:
    """Convert Neo4j values to JSON-serializable ones. Temporals become ISO strings."""
    match value:
        case dict():
            return {key: _plain(item) for key, item in value.items()}
        case list():
            return [_plain(item) for item in value]
        case Date() | DateTime():
            return value.iso_format()
        case _:
            return value


def _format_money(value: Any) -> Any:
    """Write dollar fields as "$5,000.00" anywhere in a tool result."""
    match value:
        case dict():
            return {
                key: f"${item:,.2f}"
                if key in _MONEY_FIELDS and isinstance(item, int | float)
                else _format_money(item)
                for key, item in value.items()
            }
        case list():
            return [_format_money(item) for item in value]
        case _:
            return value


def _kind(var: str) -> str:
    """Cypher for the party type of node ``var``."""
    return (
        f"CASE WHEN {var}:Business THEN 'BUSINESS' "
        f"WHEN {var}:Person THEN 'PERSON' ELSE 'CUSTOMER' END"
    )


_SHARED_FIELDS = frozenset({"kind", "value", "address_kind", "used_by", "applicants"})
_EXCLUDED_FIELDS = frozenset(
    {
        "kind",
        "value",
        "address_kind",
        "used_by_count",
        "used_by_members",
        "used_by_my_clients",
    }
)

# Every detail query starts with this match, so a business outside the
# banker's book returns no rows.
_MY_BUSINESS = """
MATCH (:Banker {banker_id: $banker_id})-[:MANAGES]->
      (b:Business {business_id: $business_id})
"""

_CHECK_MY_BUSINESS = _MY_BUSINESS + "RETURN b.business_id AS business_id"

_MY_APPLICATION = """
MATCH (banker:Banker {banker_id: $banker_id})-[:MANAGES]->(b:Business)
      -[:APPLIED_FOR]->(app:LoanApplication {application_id: $application_id})
"""

_RULES = """
MATCH (rule)
WHERE (rule:FraudRule OR rule:LendingRule) AND rule.rule_code IN $codes
RETURN rule {
  .rule_code, .name, .condition, .percent, .years, .lookback_days, .amount,
  .min_red_flags,
  policy: [(policy:Policy)-[:DEFINES]->(rule) | policy.name][0],
  policy_text: [(rule)-[:FROM_CHUNK]->(chunk:Chunk) | chunk.text]
} AS rule
"""

# A business outside the book shows only its name, its banker, and the
# banker's own clients it shares a connected group with.
_FIND_MY_CLIENT = """
MATCH (b:Business)
WHERE toLower(b.name) CONTAINS toLower($name)
WITH b, exists { (:Banker {banker_id: $banker_id})-[:MANAGES]->(b) } AS in_my_book
ORDER BY in_my_book DESC, b.name
LIMIT $limit
RETURN in_my_book,
CASE WHEN in_my_book THEN b {
  .business_id, .name, .industry, .registered_on,
  applications: COLLECT {
    MATCH (b)-[:APPLIED_FOR]->(app:LoanApplication)
    RETURN app {.application_id, .type, .status, .submitted_at} AS app
    ORDER BY app.submitted_at DESC
  }
} ELSE b {
  .name,
  banker: [(banker:Banker)-[:MANAGES]->(b) | banker.name][0],
  connected_to_my_clients: COLLECT {
    MATCH (b)-[:IN_GROUP]->(g:ConnectedGroup)<-[:IN_GROUP]-(client:Business)
          <-[:MANAGES]-(:Banker {banker_id: $banker_id})
    RETURN client {.business_id, .name, group_id: g.group_id} AS client
    ORDER BY client.name
  }
} END AS business
"""

_GET_APPLICATION = (
    _MY_APPLICATION
    + """
RETURN app.application_id AS application_id, app.type AS type,
       app.amount AS amount, app.stated_annual_revenue AS stated_annual_revenue,
       app.submitted_at AS submitted_at, app.status AS status,
       b {.business_id, .name, .industry, .registered_on} AS business
"""
)

# Posted deposits to the business's accounts between $date_from and $date_to:
# credits on its own accounts, plus transfers in from accounts it does not hold.
_DEPOSITS = """
CALL (b) {
  CALL (b) {
    MATCH (b)-[:HOLDS]->(:Account)-[:HAS_TRANSACTION]->(t:Transaction)
    WHERE t.type IN $credit_types
    RETURN t
    UNION
    MATCH (b)-[:HOLDS]->(:Account)<-[:TO_ACCOUNT]-(t:Transaction)
          <-[:HAS_TRANSACTION]-(source:Account)
    WHERE NOT (b)-[:HOLDS]->(source)
    RETURN t
  }
  WITH t
  WHERE t.status = 'POSTED' AND $date_from <= date(t.initiated_at) <= $date_to
  RETURN coalesce(sum(t.amount), 0.0) AS total_deposits
}
"""

_CHECK_LENDING_RULES = (
    _MY_APPLICATION
    + _DEPOSITS
    + """
RETURN app {
  .application_id, .type, .amount, .stated_annual_revenue, .submitted_at, .status
} AS application,
b {.business_id, .name} AS business,
banker {.banker_id, .name, .role, .approval_limit} AS banker,
total_deposits,
exists {
  MATCH (referral)-[:FOR_APPLICATION]->(app)
  WHERE referral:FraudReferral AND referral.status = 'OPEN'
} AS open_fraud_referral
"""
)

# Each chain is a path of OWNS links of any length up to the business. A
# written-off loan counts when the owner borrowed or owns the borrower, at any
# depth.
_BENEFICIAL_OWNERS = (
    _MY_BUSINESS
    + """
CALL (b) {
  OPTIONAL MATCH path = (owner)-[owns:OWNS]->+(b)
  WITH owner, collect({
    path: [n IN nodes(path) | n.name], percents: [r IN owns | r.percent]
  }) AS chains
  WHERE owner IS NOT NULL
  RETURN collect({
    owner_id: coalesce(owner.person_id, owner.business_id, owner.customer_id),
    name: owner.name,
    kind: """
    + _kind("owner")
    + """,
    in_my_book: exists { (:Banker {banker_id: $banker_id})-[:MANAGES]->(owner) },
    chains: chains,
    written_off_loans: COLLECT {
      MATCH (owner)-[:OWNS]->*(borrower)-[:BORROWER_ON]->
            (loan:Loan {status: 'WRITTEN_OFF'})
      RETURN DISTINCT loan {
        .loan_id, .type, .principal, .status, .opened_date, .closed_date,
        borrower: borrower.name,
        within_lookback: loan.closed_date >= $loss_since
      } AS loan
      ORDER BY loan.closed_date DESC
    }
  }) AS owners
}
RETURN b {.business_id, .name} AS business, owners
"""
)

# Members are the group's members, or the business alone when it is in no
# group. An identifier is listed when two or more parties use it. A device is
# used by the businesses whose applications were submitted from it.
_CONNECTED_GROUP = (
    _MY_BUSINESS
    + """
OPTIONAL MATCH (b)-[:IN_GROUP]->(g:ConnectedGroup)
WITH b, g,
     CASE WHEN g IS NULL THEN [b]
          ELSE COLLECT { MATCH (m)-[:IN_GROUP]->(g) RETURN m } END AS members
CALL (b, g, members) {
  UNWIND members AS m
  RETURN collect({
    id: coalesce(m.business_id, m.person_id, m.customer_id),
    name: m.name,
    kind: """
    + _kind("m")
    + """,
    centrality: CASE WHEN g IS NULL THEN null
                     ELSE COLLECT {
                       MATCH (m)-[r:IN_GROUP]->(g) RETURN round(r.centrality, 2)
                     }[0] END,
    in_my_book: exists { (:Banker {banker_id: $banker_id})-[:MANAGES]->(m) },
    banker: [(banker:Banker)-[:MANAGES]->(m) | banker.name][0],
    // An outside member's application date is theirs, so it stays hidden.
    applied_on: CASE WHEN exists {
                       (:Banker {banker_id: $banker_id})-[:MANAGES]->(m)
                     } THEN COLLECT {
      MATCH (m)-[:APPLIED_FOR]->(app:LoanApplication)
      WHERE app.status IN $open_statuses
      RETURN date(app.submitted_at) AS day ORDER BY day DESC LIMIT 1
    }[0] END
  }) AS member_rows
}
CALL (members) {
  UNWIND members AS m
  CALL (m) {
    MATCH (m)-[:HAS_PHONE|HAS_EMAIL|HAS_ADDRESS]->(id)
    RETURN id
    UNION
    MATCH (m)-[:APPLIED_FOR]->(:LoanApplication)-[:SUBMITTED_FROM]->(id:Device)
    RETURN id
  }
  WITH DISTINCT id, members
  WITH id, members,
       CASE WHEN id:Device THEN COLLECT {
         MATCH (u:Business)-[:APPLIED_FOR]->(:LoanApplication)
               -[:SUBMITTED_FROM]->(id)
         RETURN DISTINCT u
       } ELSE COLLECT {
         MATCH (u)-[:HAS_PHONE|HAS_EMAIL|HAS_ADDRESS]->(id)
         WHERE u:Customer OR u:Person OR u:Business
         RETURN DISTINCT u
       } END AS users
  WHERE size(users) >= 2
  WITH id, members, users,
       id:Address AND id.kind IN $excluded_kinds AS excluded
  ORDER BY excluded, id.number, id.address, id.device_id, id.address_id
  RETURN collect({
    kind: CASE WHEN id:Phone THEN 'PHONE' WHEN id:Email THEN 'EMAIL'
               WHEN id:Device THEN 'DEVICE' ELSE 'ADDRESS' END,
    // A home address is never shown, only who shares it.
    value: CASE WHEN id:Address AND id.kind = 'HOME' THEN null ELSE coalesce(
      id.number, id.device_id, id.line1 + ', ' + id.city + ', ' + id.state,
      id.address
    ) END,
    address_kind: id.kind,
    excluded: excluded,
    used_by: apoc.coll.sort([u IN users | u.name]),
    applicants: apoc.coll.sort([u IN users WHERE exists {
      MATCH (u)-[:APPLIED_FOR]->(app:LoanApplication)
      WHERE app.status IN $open_statuses
    } | u.name]),
    used_by_count: size(users),
    used_by_members: apoc.coll.sort([u IN users WHERE u IN members | u.name]),
    used_by_my_clients: apoc.coll.sort([u IN users WHERE exists {
      (:Banker {banker_id: $banker_id})-[:MANAGES]->(u)
    } | u.name])
  }) AS identifiers
}
CALL (members) {
  UNWIND members AS owner
  MATCH (owner)-[r:OWNS]->(owned)
  WHERE owned IN members
  WITH owner, owned, r ORDER BY owner.name, owned.name
  RETURN collect({
    owner: owner.name, business: owned.name, percent: r.percent
  }) AS ownership
}
CALL (members) {
  UNWIND members AS director
  MATCH (director)-[:DIRECTOR_OF]->(directed)
  WHERE directed IN members
  WITH director, directed ORDER BY director.name, directed.name
  RETURN collect({
    director: director.name, business: directed.name,
    business_has_open_application: exists {
      MATCH (directed)-[:APPLIED_FOR]->(app:LoanApplication)
      WHERE app.status IN $open_statuses
    }
  }) AS directors
}
RETURN b {.business_id, .name} AS business,
       g {.group_id, .size, .method} AS group,
       member_rows AS members, identifiers, ownership, directors
"""
)

# A loop is a transfer back into the business whose sender the business
# reached earlier through a chain of transfers, each after the one before. The
# chain that left latest is kept, so ``days_to_return`` is the shortest loop.
# Only the first transfer of a chain is the business's own, so the hops in
# between are shown as names on the route, with no amounts.
_CIRCULAR_FLOWS = (
    _MY_BUSINESS
    + _DEPOSITS
    + """
CALL (b) {
  MATCH (b)-[:HOLDS]->(mine:Account)<-[:TO_ACCOUNT]-(back:Transaction)
        <-[:HAS_TRANSACTION]-(source:Account)
  WHERE NOT (b)-[:HOLDS]->(source)
    AND back.status = 'POSTED'
    AND $date_from <= date(back.initiated_at) <= $date_to
  CALL (mine, source, back) {
    MATCH path = (mine)(()-[:HAS_TRANSACTION]->(hop:Transaction)
                 -[:TO_ACCOUNT]->()){1,"""
    + str(_MAX_LOOP_HOPS)
    + """}(source)
    WHERE date(hop[0].initiated_at) >= $date_from
      AND last(hop).initiated_at < back.initiated_at
      AND all(i IN range(0, size(hop) - 2)
              WHERE hop[i].initiated_at < hop[i + 1].initiated_at)
    RETURN path, hop
    ORDER BY hop[0].initiated_at DESC, size(hop)
    LIMIT 1
  }
  WITH b, back, hop,
       [n IN nodes(path) WHERE n:Account |
         [(holder)-[:HOLDS]->(n) WHERE holder:Business OR holder:Customer |
           holder][0]] AS holders
  WITH b, back, hop, holders, last(holders) AS sender
  RETURN collect({
    returned_transaction_id: back.transaction_id,
    returned_amount: back.amount,
    returned_on: date(back.initiated_at),
    from_business: sender.name,
    from_in_my_book: exists {
      (:Banker {banker_id: $banker_id})-[:MANAGES]->(sender)
    },
    sender_in_same_group: exists {
      (b)-[:IN_GROUP]->(:ConnectedGroup)<-[:IN_GROUP]-(sender)
    },
    sent_transaction_id: hop[0].transaction_id,
    sent_amount: hop[0].amount,
    sent_on: date(hop[0].initiated_at),
    days_to_return: duration.inDays(
      date(hop[0].initiated_at), date(back.initiated_at)
    ).days,
    route: [holder IN holders | holder.name] + [b.name]
  }) AS loops
}
RETURN b {.business_id, .name} AS business, total_deposits, loops
"""
)
