"""A Neo4j-backed Custom service knowledge source for watsonx Orchestrate.

Orchestrate sends ``POST <server_url>`` with ``{"query", "filter", "metadata"}``
and expects ``{"search_results": [{"title", "body", ...}]}`` back. This service
answers with a fraud screen when the ``filter`` names a business in the banker's
book, followed by policy passages from the graph. It reuses the retrieval
functions in ``tools.py`` and ``staff_tools.py`` and adds no Cypher of its own.

Orchestrate keeps only the first 5 snippets of ``search_results``. The fraud
screen therefore comes first and always survives, and the policy passages fill
the remaining slots up to ``_MAX_RESULTS``.

Every request needs the shared key in ``KNOWLEDGE_SERVICE_API_KEY``.
"""

import base64
import binascii
import hmac
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from graphrag_banking import staff_tools, tools
from graphrag_banking.config import Settings, get_driver, load_settings

API_KEY_VARIABLE = "KNOWLEDGE_SERVICE_API_KEY"
# Orchestrate rejects a response over 100 KB. Stay well under it.
_MAX_BODY_CHARS = 8000
# Orchestrate keeps only the first 5 snippets of search_results.
_MAX_RESULTS = 5


class SearchRequest(BaseModel):
    """The request body Orchestrate sends. Unknown fields are ignored."""

    query: str
    filter: str | None = None
    metadata: dict[str, Any] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Read settings, fail fast on a missing key, and own one Neo4j driver."""
    if not os.environ.get(API_KEY_VARIABLE):
        raise RuntimeError(f"{API_KEY_VARIABLE} is not set.")
    settings = load_settings()
    app.state.settings = settings
    app.state.banker_id = os.environ.get("DEMO_BANKER_ID", "")
    with get_driver(settings) as driver:
        app.state.driver = driver
        yield


app = FastAPI(title="Neo4j custom knowledge service", lifespan=lifespan)


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    """Accept the shared key as ``X-API-Key``, a bearer token, or a Basic password.

    Orchestrate documents API key and Basic auth for a Custom service but not the
    header name, so each form it might send is checked.
    """
    expected = os.environ[API_KEY_VARIABLE]
    if not any(
        hmac.compare_digest(candidate, expected)
        for candidate in _presented_keys(x_api_key, authorization)
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _presented_keys(x_api_key: str | None, authorization: str | None) -> list[str]:
    keys = [x_api_key] if x_api_key else []
    scheme, _, credential = (authorization or "").partition(" ")
    match scheme.lower():
        case "bearer" | "apikey":
            keys.append(credential)
        case "basic":
            try:
                decoded = base64.b64decode(credential).decode()
            except (binascii.Error, UnicodeDecodeError):
                return keys
            keys.append(decoded.partition(":")[2])
    return keys


@app.post("/", dependencies=[Depends(require_api_key)])
@app.post("/query", dependencies=[Depends(require_api_key)])
def search(body: SearchRequest, request: Request) -> dict[str, Any]:
    """Return the passages that answer the query, in Orchestrate's schema.

    Orchestrate keeps only the first 5 snippets, so the order decides what the
    agent sees. The fraud screen results and any "Outside your book" results
    come first and are always kept, even when they exceed 5. The policy passages
    follow in score order and fill the remaining slots. Without a filter the
    response holds the top 5 policy passages.
    """
    state = request.app.state
    results = []
    if body.filter and body.filter.strip():
        results = _fraud_results(state, body.filter.strip())
    remaining = max(0, _MAX_RESULTS - len(results))
    if remaining:
        results += _policy_results(state, body.query)[:remaining]
    return {"search_results": results}


def _policy_results(state: Any, question: str) -> list[dict[str, Any]]:
    settings: Settings = state.settings
    context = tools.ToolContext(
        driver=state.driver,
        database=settings.neo4j_database,
        customer_id=settings.demo_customer_id,
        embedding_config=settings.embedding_config,
        as_of=settings.demo_as_of,
    )
    return [
        _result(
            title=passage["policy"],
            body=passage["text"],
            score=passage["score"],
            rule_codes=[rule["rule_code"] for rule in passage["rules"]],
        )
        for passage in tools.search_policies(context, question)["passages"]
    ]


def _fraud_results(state: Any, name: str) -> list[dict[str, Any]]:
    """Screen the businesses in the banker's book that match ``name``."""
    context = staff_tools.StaffContext(
        driver=state.driver,
        database=state.settings.neo4j_database,
        banker_id=state.banker_id,
        as_of=state.settings.demo_as_of,
    )
    found = staff_tools.find_my_client(context, name)
    results = []
    for client in found["clients"]:
        screen = staff_tools.screen_business(context, client["business_id"])
        for check, detail in screen.items():
            flags = detail.get("red_flags", [])
            facts = {key: value for key, value in detail.items() if key != "rules"}
            results.append(
                _result(
                    title=f"Fraud screen, {check}: {client['name']}",
                    body=f"Red flags: {', '.join(flags) or 'none'}.\n"
                    + json.dumps(facts, default=str),
                    rule_codes=flags,
                )
            )
    results += [
        _result(
            title=f"Outside your book: {business['name']}",
            body=f"Managed by {business['banker']}. Details cannot be shown.",
        )
        for business in found["outside_my_book"]
    ]
    return results


def _result(
    title: str,
    body: str,
    score: float | None = None,
    rule_codes: list[str] | None = None,
) -> dict[str, Any]:
    result_metadata: dict[str, Any] = {"rule_codes": rule_codes or []}
    if score is not None:
        result_metadata["score"] = score
    return {
        "title": title,
        "body": body[:_MAX_BODY_CHARS],
        "result_metadata": result_metadata,
    }
