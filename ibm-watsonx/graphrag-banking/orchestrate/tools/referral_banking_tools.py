"""watsonx Orchestrate wrappers for the fraud referral tools.

Each wrapper reads the ``banker_creds`` connection, opens a Neo4j driver, and
calls the matching function in ``referral_tools.py``. The connection supplies
the banker ID, so the model never chooses who submitted a referral.

Each wrapper takes its description from the matching function in
``referral_tools.py``, so the tools carry the same descriptions in Orchestrate
as they do locally.

The ``fraud_referral`` flow calls these tools. No agent lists them directly.

``build_referral_tools.sh`` copies this file next to ``referral_queries.py``
and imports the folder as one package. ``referral_queries.py`` is a copy of
``referral_tools.py``.
"""

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import neo4j
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.run import connections

# Orchestrate runs this file as a top-level module, not as part of a package,
# so relative imports fail. Put this file's folder on the import path instead.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import referral_queries as referral

APP_ID = "banker_creds"
CREDENTIALS = [{"app_id": APP_ID, "type": "key_value_creds"}]


def _described_by(
    source: Callable[..., Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Copy the docstring of a function in referral_tools.py onto its wrapper."""

    def apply(wrapper: Callable[..., Any]) -> Callable[..., Any]:
        wrapper.__doc__ = source.__doc__
        return wrapper

    return apply


@contextmanager
def _context() -> Iterator[referral.ReferralContext]:
    """Build a ReferralContext from the connection and close the driver afterwards."""
    creds = connections.key_value(APP_ID)
    driver = neo4j.GraphDatabase.driver(
        creds["NEO4J_URI"],
        auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]),
    )
    try:
        yield referral.ReferralContext(
            driver=driver,
            database=creds["NEO4J_DATABASE"],
            banker_id=creds["DEMO_BANKER_ID"],
            as_of=date.fromisoformat(creds["DEMO_AS_OF"]),
        )
    finally:
        driver.close()


@tool(expected_credentials=CREDENTIALS)
@_described_by(referral.create_fraud_referral)
def create_fraud_referral(
    application_id: str, red_flags: list[str], summary: str
) -> dict[str, Any]:
    with _context() as context:
        return referral.create_fraud_referral(
            context, application_id, red_flags, summary
        )


@tool(expected_credentials=CREDENTIALS)
@_described_by(referral.resolve_fraud_referral)
def resolve_fraud_referral(referral_id: str, status: str) -> dict[str, Any]:
    with _context() as context:
        return referral.resolve_fraud_referral(context, referral_id, status)
