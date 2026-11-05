"""watsonx Orchestrate wrappers for the banker-scoped staff tools.

Each wrapper reads the ``banker_creds`` connection, opens a Neo4j driver, and
calls the matching function in ``staff_tools.py``. The connection supplies the
banker ID, so the model never chooses whose book it reads.

Each wrapper takes its description from the matching function in
``staff_tools.py``, so the agent sees the same tool descriptions in Orchestrate
as it does locally.

``build_staff_tools.sh`` copies this file next to ``staff_queries.py`` and
imports the folder as one package. ``staff_queries.py`` is a copy of
``staff_tools.py``.
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

import staff_queries as staff

APP_ID = "banker_creds"
CREDENTIALS = [{"app_id": APP_ID, "type": "key_value_creds"}]


def _described_by(
    source: Callable[..., Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Copy the docstring of a function in staff_tools.py onto its wrapper."""

    def apply(wrapper: Callable[..., Any]) -> Callable[..., Any]:
        wrapper.__doc__ = source.__doc__
        return wrapper

    return apply


@contextmanager
def _context() -> Iterator[staff.StaffContext]:
    """Build a StaffContext from the connection and close the driver afterwards."""
    creds = connections.key_value(APP_ID)
    driver = neo4j.GraphDatabase.driver(
        creds["NEO4J_URI"],
        auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]),
    )
    try:
        yield staff.StaffContext(
            driver=driver,
            database=creds["NEO4J_DATABASE"],
            banker_id=creds["DEMO_BANKER_ID"],
            as_of=date.fromisoformat(creds["DEMO_AS_OF"]),
        )
    finally:
        driver.close()


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.find_my_client)
def find_my_client(name: str) -> dict[str, Any]:
    with _context() as context:
        return staff.find_my_client(context, name)


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.get_application)
def get_application(application_id: str) -> dict[str, Any]:
    with _context() as context:
        return staff.get_application(context, application_id)


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.check_lending_rules)
def check_lending_rules(application_id: str) -> dict[str, Any]:
    with _context() as context:
        return staff.check_lending_rules(context, application_id)


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.get_beneficial_owners)
def get_beneficial_owners(business_id: str) -> dict[str, Any]:
    with _context() as context:
        return staff.get_beneficial_owners(context, business_id)


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.get_connected_group)
def get_connected_group(business_id: str) -> dict[str, Any]:
    with _context() as context:
        return staff.get_connected_group(context, business_id)


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.find_circular_flows)
def find_circular_flows(
    business_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    with _context() as context:
        return staff.find_circular_flows(
            context, business_id, date_from=date_from, date_to=date_to
        )


@tool(expected_credentials=CREDENTIALS)
@_described_by(staff.screen_business)
def screen_business(business_id: str) -> dict[str, Any]:
    with _context() as context:
        return staff.screen_business(context, business_id)
