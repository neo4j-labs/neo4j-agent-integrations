"""watsonx Orchestrate wrappers for the customer-scoped retrieval tools.

Each wrapper reads the ``banking_creds`` connection, opens a Neo4j driver, and
calls the matching function in ``tools.py``. The connection supplies the
customer ID, so the model never chooses which customer's data it reads.

Each wrapper takes its description from the matching function in ``tools.py``,
so the agent sees the same tool descriptions in Orchestrate as it does locally.

``build_tools.sh`` copies this file next to ``banking_queries.py`` (a copy of
``tools.py``) and ``embeddings.py``, and imports the folder as one package.
"""

import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any, Optional, Union

import neo4j
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.run import connections

# Orchestrate runs this file as a top-level module, not as part of a package,
# so relative imports fail. Put this file's folder on the import path instead.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import banking_queries as banking

APP_ID = "banking_creds"
CREDENTIALS = [{"app_id": APP_ID, "type": "key_value_creds"}]


def _described_by(source: Callable[..., Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Copy the docstring of a function in tools.py onto its wrapper."""

    def apply(wrapper: Callable[..., Any]) -> Callable[..., Any]:
        wrapper.__doc__ = source.__doc__
        return wrapper

    return apply


@contextmanager
def _context() -> Iterator[banking.ToolContext]:
    """Build a ToolContext from the connection and close the driver afterwards."""
    creds = connections.key_value(APP_ID)
    driver = neo4j.GraphDatabase.driver(
        creds["NEO4J_URI"],
        auth=(creds["NEO4J_USERNAME"], creds["NEO4J_PASSWORD"]),
    )
    try:
        yield banking.ToolContext(
            driver=driver,
            database=creds["NEO4J_DATABASE"],
            customer_id=creds["DEMO_CUSTOMER_ID"],
            embedding_config={
                "provider": "openai",
                "model": creds["OPENAI_EMBEDDING_MODEL"],
                "api_key": creds["OPENAI_API_KEY"],
            },
            as_of=date.fromisoformat(creds["DEMO_AS_OF"]),
        )
    finally:
        driver.close()


@tool(expected_credentials=CREDENTIALS)
@_described_by(banking.search_policies)
def search_policies(question: str) -> dict[str, Any]:
    with _context() as context:
        return banking.search_policies(context, question)


@tool(expected_credentials=CREDENTIALS)
@_described_by(banking.get_my_accounts)
def get_my_accounts() -> dict[str, Any]:
    with _context() as context:
        return banking.get_my_accounts(context)


@tool(expected_credentials=CREDENTIALS)
@_described_by(banking.find_my_transactions)
def find_my_transactions(
    payee: Optional[str] = None,
    type: Optional[Union[str, list[str]]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    with _context() as context:
        return banking.find_my_transactions(
            context, payee=payee, type=type, date_from=date_from, date_to=date_to
        )


@tool(expected_credentials=CREDENTIALS)
@_described_by(banking.explain_transaction)
def explain_transaction(transaction_id: str) -> dict[str, Any]:
    with _context() as context:
        return banking.explain_transaction(context, transaction_id)


@tool(expected_credentials=CREDENTIALS)
@_described_by(banking.get_my_household)
def get_my_household() -> dict[str, Any]:
    with _context() as context:
        return banking.get_my_household(context)


@tool(expected_credentials=CREDENTIALS)
@_described_by(banking.get_scheduled_payments)
def get_scheduled_payments(account_id: str) -> dict[str, Any]:
    with _context() as context:
        return banking.get_scheduled_payments(context, account_id)