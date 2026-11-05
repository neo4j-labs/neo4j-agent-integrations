"""Tools that write fraud referrals for the referral workflow in the loan fraud demo.

Portability rule: at module level this file imports only the ``neo4j`` driver
and the standard library, so the tools move into watsonx Orchestrate unchanged.
It repeats the small helpers it needs from ``staff_tools.py`` instead of
importing them. Only ``main``, the local cleanup command, imports the project
config, and it does so inside the function.

Each tool takes a ``ReferralContext`` first, then the arguments the model sees.
The context carries the signed-in banker, so the model never supplies one.
``create_fraud_referral`` checks the application against the banker's book
through ``(:Banker {banker_id: $banker_id})-[:MANAGES]->(:Business)``.

``check_lending_rules`` in ``staff_tools.py`` reads an open referral through
``(:FraudReferral)-[:FOR_APPLICATION]->(:LoanApplication)``. The create query
uses those exact names.
"""

import argparse
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import neo4j
from neo4j.time import Date, DateTime

logger = logging.getLogger(__name__)

# The red flag rules a referral can cite. The other fraud rules, such as
# AML-NO-TIPOFF, are guidance and are never cited.
_RED_FLAG_CODES = frozenset(
    {"KYC-UBO-25", "FRAUD-PRIOR-LOSS", "FRAUD-SHARED-ID", "FRAUD-CIRCULAR-FLOW"}
)
# Sam Price reviews every referral in the demo.
_REVIEWER_ID = "FR-02"
_RESOLVED_STATUSES = frozenset({"ACCEPTED", "CLOSED"})


@dataclass(frozen=True)
class ReferralContext:
    """Settings the referral tools need that the model must not supply.

    Attributes:
        driver: Open Neo4j driver.
        database: Neo4j database name.
        banker_id: The signed-in banker. The create query checks MANAGES.
        as_of: Today's date for the demo.
        executed: Cypher run by the tools, in order. Used for the trace.
    """

    driver: neo4j.Driver
    database: str
    banker_id: str
    as_of: date
    executed: list[str] = field(default_factory=list)


def create_fraud_referral(
    context: ReferralContext,
    application_id: str,
    red_flags: list[str],
    summary: str,
) -> dict[str, Any]:
    """Refer a loan application to the fraud team, with status OPEN.

    The referral links to the application, the business's connected group,
    each red flag rule, and the fraud reviewer Sam Price. Only one open
    referral can exist for an application.

    Args:
        application_id: An application ID from a client in your book.
        red_flags: The red flag rule codes from the fraud check, such as
            "FRAUD-SHARED-ID". Each must be KYC-UBO-25, FRAUD-PRIOR-LOSS,
            FRAUD-SHARED-ID, or FRAUD-CIRCULAR-FLOW.
        summary: A short summary of why the application is referred.

    Returns:
        The new referral with its links, or an error if the application is not
        from a client in your book or already has an open referral.
    """
    if not summary.strip():
        raise ValueError("Give a summary of why the application is referred")
    codes = list(dict.fromkeys(red_flags))
    if not codes:
        raise ValueError("Give at least one red flag rule code")
    if unknown := [code for code in codes if code not in _RED_FLAG_CODES]:
        raise ValueError(
            f"Not red flag rule codes: {', '.join(unknown)}. "
            f"Use {', '.join(sorted(_RED_FLAG_CODES))}."
        )

    created_at = datetime.combine(context.as_of, datetime.now(UTC).time(), tzinfo=UTC)
    records = _write(
        context,
        _CREATE_FRAUD_REFERRAL,
        application_id=application_id,
        reviewer_id=_REVIEWER_ID,
        red_flags=codes,
        summary=summary.strip(),
        created_at=created_at,
    )
    if records:
        return records[0]["referral"]

    [why] = _run(
        context,
        _WHY_NOT_CREATED,
        application_id=application_id,
    )
    if not why["in_my_book"]:
        return {"error": f"No application {application_id} from a client in your book."}
    if why["open_referral"]:
        return {
            "error": f"Application {application_id} already has an open referral, "
            f"{why['open_referral']}."
        }
    return {"error": f"No fraud reviewer {_REVIEWER_ID} in the graph."}


def resolve_fraud_referral(
    context: ReferralContext, referral_id: str, status: str
) -> dict[str, Any]:
    """Set an open fraud referral's status to ACCEPTED or CLOSED.

    Args:
        referral_id: The referral ID from create_fraud_referral, such as
            "REF-0001".
        status: ACCEPTED or CLOSED.

    Returns:
        The referral with its new status, or an error if no open referral has
        that ID.
    """
    if status not in _RESOLVED_STATUSES:
        raise ValueError(f"Status must be ACCEPTED or CLOSED, not {status!r}")
    records = _write(
        context, _RESOLVE_FRAUD_REFERRAL, referral_id=referral_id, status=status
    )
    if not records:
        return {
            "error": f"No open referral {referral_id}. "
            "It does not exist or is already resolved."
        }
    return records[0]["referral"]


def delete_demo_referrals(driver: neo4j.Driver, database: str) -> int:
    """Delete every FraudReferral and its links. Returns the number deleted."""
    _, summary, _ = driver.execute_query(
        _DELETE_REFERRALS, database_=database, routing_=neo4j.RoutingControl.WRITE
    )
    return summary.counters.nodes_deleted


def _run(context: ReferralContext, query: str, **params: Any) -> list[dict[str, Any]]:
    return _execute(context, query, neo4j.RoutingControl.READ, params)


def _write(context: ReferralContext, query: str, **params: Any) -> list[dict[str, Any]]:
    return _execute(context, query, neo4j.RoutingControl.WRITE, params)


def _execute(
    context: ReferralContext,
    query: str,
    routing: neo4j.RoutingControl,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    context.executed.append(query.strip())
    records, _, _ = context.driver.execute_query(
        query,
        banker_id=context.banker_id,
        database_=context.database,
        routing_=routing,
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


# Creates nothing unless the application is in the banker's book, the reviewer
# exists, and the application has no open referral. The ID is the next
# REF-0001 style number.
_CREATE_FRAUD_REFERRAL = """
MATCH (banker:Banker {banker_id: $banker_id})-[:MANAGES]->(b:Business)
      -[:APPLIED_FOR]->(app:LoanApplication {application_id: $application_id})
MATCH (reviewer:FraudReviewer {reviewer_id: $reviewer_id})
WHERE NOT exists {
  MATCH (:FraudReferral {status: 'OPEN'})-[:FOR_APPLICATION]->(app)
}
CALL () {
  OPTIONAL MATCH (existing:FraudReferral)
  RETURN coalesce(max(toInteger(substring(existing.referral_id, 4))), 0) + 1 AS next
}
CREATE (referral:FraudReferral {
  referral_id: 'REF-' + right('000' + toString(next), 4),
  status: 'OPEN', created_at: $created_at, summary: $summary
})
CREATE (banker)-[:SUBMITTED]->(referral)
CREATE (referral)-[:FOR_APPLICATION]->(app)
CREATE (referral)-[:ASSIGNED_TO]->(reviewer)
WITH banker, b, app, reviewer, referral
CALL (b, referral) {
  OPTIONAL MATCH (b)-[:IN_GROUP]->(g:ConnectedGroup)
  WITH referral, collect(g) AS groups
  FOREACH (g IN groups | CREATE (referral)-[:ABOUT_GROUP]->(g))
  RETURN [g IN groups | g.group_id][0] AS group_id
}
CALL (referral) {
  MATCH (rule:FraudRule)
  WHERE rule.rule_code IN $red_flags
  CREATE (referral)-[:CITES]->(rule)
  RETURN collect(rule.rule_code) AS cites
}
RETURN referral {
  .referral_id, .status, .created_at, .summary,
  application: app.application_id,
  business: b {.business_id, .name},
  group_id: group_id,
  cites: cites,
  assigned_to: reviewer {.reviewer_id, .name},
  submitted_by: banker {.banker_id, .name}
} AS referral
"""

_WHY_NOT_CREATED = """
OPTIONAL MATCH (:Banker {banker_id: $banker_id})-[:MANAGES]->(:Business)
      -[:APPLIED_FOR]->(app:LoanApplication {application_id: $application_id})
RETURN app IS NOT NULL AS in_my_book,
       [(r:FraudReferral {status: 'OPEN'})-[:FOR_APPLICATION]->(app)
        | r.referral_id][0] AS open_referral
"""

_RESOLVE_FRAUD_REFERRAL = """
MATCH (referral:FraudReferral {referral_id: $referral_id, status: 'OPEN'})
SET referral.status = $status
RETURN referral {.referral_id, .status, .created_at, .summary} AS referral
"""

_DELETE_REFERRALS = "MATCH (referral:FraudReferral) DETACH DELETE referral"


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete every demo fraud referral.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        required=True,
        help="delete every FraudReferral node and its links",
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from graphrag_banking.config import get_driver, load_settings

    settings = load_settings()
    with get_driver(settings) as driver:
        deleted = delete_demo_referrals(driver, settings.neo4j_database)
    logger.info("Deleted %d fraud referrals", deleted)


if __name__ == "__main__":
    main()
