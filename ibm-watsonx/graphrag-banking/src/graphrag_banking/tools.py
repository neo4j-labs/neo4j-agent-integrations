"""Customer-scoped retrieval tools for the support agent (PRD section 7.3).

Portability rule: this module imports only the ``neo4j`` driver and
``embeddings.embed``, so the tools move into watsonx Orchestrate unchanged.

Each tool takes a ``ToolContext`` first, then the arguments the model sees. The
context carries the customer ID and connection settings, so the model never
supplies a customer ID. Every customer-scoped query starts from
``(:Customer {customer_id: $customer_id})-[:HOLDS]->(:Account)``.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import neo4j
from neo4j.time import Date, DateTime

from graphrag_banking.embeddings import embed

VECTOR_INDEX_NAME = "chunk_embedding"
COUNTERPARTY_INDEX_NAME = "counterparty_name"

TRANSACTION_TYPES = frozenset(
    {
        "WIRE_OUT",
        "WIRE_IN",
        "ACH_OUT",
        "ACH_IN",
        "CHECK_DEPOSIT",
        "CARD",
        "FEE",
        "TRANSFER",
    }
)
_CREDIT_TYPES = ["CHECK_DEPOSIT", "ACH_IN", "WIRE_IN"]
_POLICY_RESULTS = 5
_TRANSACTION_LIMIT = 25
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
# Dollar fields the model quotes to the customer. Formatted last, so the
# coverage math in _project_balances still runs on numbers.
_MONEY_FIELDS = frozenset(
    {
        "amount",
        "ledger_balance",
        "available_balance",
        "available_before_payment",
        "threshold",
    }
)


@dataclass(frozen=True)
class ToolContext:
    """Settings the tools need that the model must not supply.

    Attributes:
        driver: Open Neo4j driver.
        database: Neo4j database name.
        customer_id: The signed-in customer. Every scoped query starts here.
        embedding_config: Passed to ``embeddings.embed``.
        as_of: Today's date for the demo.
        executed: Cypher run by the tools, in order. Used for the trace.
    """

    driver: neo4j.Driver
    database: str
    customer_id: str
    embedding_config: dict[str, str]
    as_of: date
    executed: list[str] = field(default_factory=list)


def search_policies(context: ToolContext, question: str) -> dict[str, Any]:
    """Search the bank's policy documents for fees, holds, and compliance rules.

    Use this for any question about what a policy says, such as fee amounts,
    waivers, hold periods, or why a transaction is reviewed. Results include the
    structured rules each passage defines and the products they apply to.

    Args:
        question: The policy question in plain language.

    Returns:
        The best matching policy passages and the passages next to them, each
        with its policy name and rules. Neighboring passages have no score.
    """
    records = _run(
        context,
        _SEARCH_POLICIES,
        index=VECTOR_INDEX_NAME,
        k=_POLICY_RESULTS,
        embedding=embed(question, context.embedding_config),
    )
    return _format_money({"passages": records})


def get_my_accounts(context: ToolContext) -> dict[str, Any]:
    """List the customer's accounts with product, balances, and co-holders.

    Use this to find which account the customer means, such as "our joint
    account", and which product terms apply to it.

    Returns:
        The customer's accounts.
    """
    records = _run(context, _GET_MY_ACCOUNTS)
    return _format_money({"accounts": records})


def find_my_transactions(
    context: ToolContext,
    payee: str | None = None,
    type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    """Find transactions on the customer's accounts, newest first.

    All filters are optional. Resolve relative dates such as "yesterday" to
    YYYY-MM-DD before calling.

    Args:
        payee: Payee or payer name. Partial names match, such as "Acme".
        type: One of WIRE_OUT, WIRE_IN, ACH_OUT, ACH_IN, CHECK_DEPOSIT, CARD,
            FEE, or TRANSFER.
        date_from: Earliest initiation date, YYYY-MM-DD, inclusive.
        date_to: Latest initiation date, YYYY-MM-DD, inclusive.

    Returns:
        Matching transactions, at most 25.
    """
    if type is not None and type not in TRANSACTION_TYPES:
        raise ValueError(f"Unknown transaction type {type!r}")
    params = {
        "type": type,
        "date_from": _parse_date(date_from),
        "date_to": _parse_date(date_to),
        "limit": _TRANSACTION_LIMIT,
    }
    if payee:
        records = _run(
            context,
            _FIND_TRANSACTIONS_BY_PAYEE,
            index=COUNTERPARTY_INDEX_NAME,
            payee=_LUCENE_SPECIAL.sub(r"\\\1", payee),
            **params,
        )
    else:
        records = _run(context, _FIND_TRANSACTIONS, **params)
    return _format_money({"transactions": records})


def explain_transaction(context: ToolContext, transaction_id: str) -> dict[str, Any]:
    """Explain one transaction: its status, alerts, fees, and the rules behind them.

    Returns the compliance alerts it raised, any fees charged for it, and the
    fee and hold rules for this account's product that match its type. Each rule
    shows whether this product waives it and the policy text that defines it.

    Args:
        transaction_id: A transaction ID from find_my_transactions.

    Returns:
        The transaction with its alerts, fees, and rules, or an error if the
        customer has no such transaction.
    """
    records = _run(context, _EXPLAIN_TRANSACTION, transaction_id=transaction_id)
    if not records:
        return {"error": f"No transaction {transaction_id} on your accounts."}
    return _format_money(records[0])


def get_my_household(context: ToolContext) -> dict[str, Any]:
    """List the customer's household members and the accounts they share.

    Only shared accounts are returned. Accounts a household member holds alone
    are private to them and cannot be shown.

    Returns:
        Related customers, each with the relationship and shared accounts.
    """
    records = _run(context, _GET_MY_HOUSEHOLD)
    return {"household": records}


def get_scheduled_payments(context: ToolContext, account_id: str) -> dict[str, Any]:
    """List upcoming scheduled payments on one of the customer's accounts.

    For each payment, ``available_before_payment`` is today's available balance
    plus pending deposits available by the payment date, minus earlier scheduled
    payments. ``covered`` says whether that amount covers the payment. Each
    pending deposit lists the hold rules for its type and the policy behind them.

    Args:
        account_id: An account ID from get_my_accounts.

    Returns:
        The account's available balance, pending deposits, and upcoming
        payments, or an error if the customer does not hold the account.
    """
    records = _run(
        context,
        _GET_SCHEDULED_PAYMENTS,
        account_id=account_id,
        as_of=context.as_of,
        credit_types=_CREDIT_TYPES,
    )
    if not records:
        return {"error": f"No account {account_id} among your accounts."}
    result = records[0]
    _project_balances(result)
    return _format_money(result)


def _project_balances(result: dict[str, Any]) -> None:
    """Add ``available_before_payment`` and ``covered`` to each payment."""
    balance = result["available_balance"]
    paid = 0.0
    for payment in result["payments"]:
        run_date = payment["next_run_date"]
        deposits = sum(
            deposit["amount"]
            for deposit in result["pending_deposits"]
            if deposit["available_on"] is not None
            and deposit["available_on"] <= run_date
        )
        available = round(balance + deposits - paid, 2)
        payment["available_before_payment"] = available
        payment["covered"] = available >= payment["amount"]
        paid += payment["amount"]


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Dates must be YYYY-MM-DD, got {value!r}") from error


def _run(context: ToolContext, query: str, **params: Any) -> list[dict[str, Any]]:
    context.executed.append(query.strip())
    records, _, _ = context.driver.execute_query(
        query,
        customer_id=context.customer_id,
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


# Each match brings the sections before and after it in the same document, so a
# related section the vector search ranked lower still reaches the model.
# Neighbors have a null score and sort with the match that brought them in.
_SEARCH_POLICIES = """
CALL db.index.vector.queryNodes($index, $k, $embedding) YIELD node AS hit, score
UNWIND [hit] + [(hit)-[:NEXT_CHUNK]-(neighbor:Chunk) | neighbor] AS chunk
WITH chunk, max(CASE WHEN chunk = hit THEN score END) AS score,
     max(score) AS rank
MATCH (chunk)-[:FROM_DOCUMENT]->(doc:Document)
OPTIONAL MATCH (rule)-[:FROM_CHUNK]->(chunk)
WITH chunk, score, rank, doc, rule
ORDER BY rule.rule_code
WITH chunk, score, rank, doc, collect(rule {
  .rule_code, .name, .amount, .hold_days, .threshold, .condition,
  .transaction_types,
  kind: head(labels(rule)),
  applies_to: [(rule)-[:APPLIES_TO]->(p:AccountProduct) | p.name],
  waived_for: [(rule)-[:WAIVED_FOR]->(p:AccountProduct) | p.name]
}) AS rules
RETURN doc.title AS policy, doc.policy_id AS policy_id, chunk.text AS text,
       round(score, 4) AS score, rules
ORDER BY rank DESC, chunk.index
"""

_GET_MY_ACCOUNTS = """
MATCH (c:Customer {customer_id: $customer_id})-[holds:HOLDS]->(a:Account)
OPTIONAL MATCH (a)-[:IS_PRODUCT]->(p:AccountProduct)
RETURN a.account_id AS account_id, a.nickname AS nickname, holds.role AS role,
       p.name AS product, p.product_code AS product_code,
       a.ledger_balance AS ledger_balance,
       a.available_balance AS available_balance,
       a.currency AS currency, a.status AS status,
       [(other:Customer)-[:HOLDS]->(a) WHERE other <> c | other.name]
         AS other_holders
ORDER BY account_id
"""

_TRANSACTION_FILTERS = """
WHERE ($type IS NULL OR t.type = $type)
  AND ($date_from IS NULL OR date(t.initiated_at) >= $date_from)
  AND ($date_to IS NULL OR date(t.initiated_at) <= $date_to)
"""

_TRANSACTION_FIELDS = """
RETURN t.transaction_id AS transaction_id, a.account_id AS account_id,
       a.nickname AS account_nickname, t.type AS type, t.amount AS amount,
       t.currency AS currency, t.status AS status,
       t.initiated_at AS initiated_at, t.posted_at AS posted_at,
       t.available_on AS available_on, t.channel AS channel,
       t.description AS description, cp.name AS counterparty,
       [(who:Customer)-[:INITIATED]->(t) |
         who {.customer_id, .name}][0] AS initiated_by
ORDER BY t.initiated_at DESC
LIMIT $limit
"""

_FIND_TRANSACTIONS = (
    """
MATCH (:Customer {customer_id: $customer_id})-[:HOLDS]->(a:Account)
      -[:HAS_TRANSACTION]->(t:Transaction)
"""
    + _TRANSACTION_FILTERS
    + """
OPTIONAL MATCH (t)-[:PAID_TO|RECEIVED_FROM]->(cp:Counterparty)
"""
    + _TRANSACTION_FIELDS
)

_FIND_TRANSACTIONS_BY_PAYEE = (
    """
CALL db.index.fulltext.queryNodes($index, $payee) YIELD node AS cp
MATCH (:Customer {customer_id: $customer_id})-[:HOLDS]->(a:Account)
      -[:HAS_TRANSACTION]->(t:Transaction)-[:PAID_TO|RECEIVED_FROM]->(cp)
"""
    + _TRANSACTION_FILTERS
    + _TRANSACTION_FIELDS
)

# Hold rules that match a transaction ``t`` by type, with the policy behind each.
_HOLD_RULES = """
COLLECT {
  MATCH (rule:HoldRule)
  WHERE t.type IN rule.transaction_types
  RETURN rule {
    .rule_code, .name, .hold_days, .threshold, .condition,
    policy: [(policy:Policy)-[:DEFINES]->(rule) | policy.name][0],
    policy_text: [(rule)-[:FROM_CHUNK]->(chunk:Chunk) | chunk.text]
  }
  ORDER BY rule.rule_code
}"""

_EXPLAIN_TRANSACTION = (
    """
MATCH (:Customer {customer_id: $customer_id})-[:HOLDS]->(a:Account)
      -[:HAS_TRANSACTION]->(t:Transaction {transaction_id: $transaction_id})
OPTIONAL MATCH (a)-[:IS_PRODUCT]->(p:AccountProduct)
OPTIONAL MATCH (t)-[:PAID_TO|RECEIVED_FROM]->(cp:Counterparty)
RETURN t {
  .transaction_id, .type, .amount, .currency, .status, .initiated_at,
  .posted_at, .available_on, .channel, .description
} AS transaction,
a {.account_id, .nickname} AS account,
p.name AS product,
cp.name AS counterparty,
[(who:Customer)-[:INITIATED]->(t) | who {.customer_id, .name}][0]
  AS initiated_by,
[(t)-[:RAISED]->(alert:ComplianceAlert) | alert {
  .alert_id, .rule_code, .status, .opened_at, .reason,
  rule: [(alert)-[:UNDER_RULE]->(rule:ComplianceRule) | rule {
    .rule_code, .name, .threshold, .condition,
    policy: [(policy:Policy)-[:DEFINES]->(rule) | policy.name][0],
    policy_text: [(rule)-[:FROM_CHUNK]->(chunk:Chunk) | chunk.text]
  }][0]
}] AS alerts,
[(fee:Transaction)-[:FEE_FOR]->(t) | fee {
  .transaction_id, .amount, .status, .description
}] AS fees_charged,
COLLECT {
  MATCH (rule:FeeRule)
  WHERE t.type IN rule.transaction_types
    AND exists { (rule)-[:APPLIES_TO|WAIVED_FOR]->(p) }
  RETURN rule {
    .rule_code, .name, .amount, .threshold, .condition,
    waived_for_this_product: exists { (rule)-[:WAIVED_FOR]->(p) },
    policy: [(policy:Policy)-[:DEFINES]->(rule) | policy.name][0],
    policy_text: [(rule)-[:FROM_CHUNK]->(chunk:Chunk) | chunk.text]
  }
  ORDER BY rule.rule_code
} AS fee_rules,
"""
    + _HOLD_RULES
    + """ AS hold_rules
"""
)

_GET_MY_HOUSEHOLD = """
MATCH (c:Customer {customer_id: $customer_id})-[rel:RELATED_TO]-(other:Customer)
RETURN other.customer_id AS customer_id, other.name AS name,
       rel.type AS relationship,
       [(c)-[:HOLDS]->(a:Account)<-[holds:HOLDS]-(other) |
         a {.account_id, .nickname, their_role: holds.role}] AS shared_accounts
ORDER BY name
"""

_GET_SCHEDULED_PAYMENTS = (
    """
MATCH (:Customer {customer_id: $customer_id})-[:HOLDS]->
      (a:Account {account_id: $account_id})
CALL (a) {
  OPTIONAL MATCH (a)-[:HAS_SCHEDULED_PAYMENT]->(sp:ScheduledPayment)
  WHERE sp.next_run_date >= $as_of
  OPTIONAL MATCH (sp)-[:PAYS]->(cp:Counterparty)
  WITH sp, cp ORDER BY sp.next_run_date
  RETURN collect(sp {
    .payment_id, .amount, .frequency, .next_run_date, .status,
    payee: cp.name
  }) AS payments
}
CALL (a) {
  OPTIONAL MATCH (a)-[:HAS_TRANSACTION]->(t:Transaction {status: 'PENDING'})
  WHERE t.type IN $credit_types
  WITH t ORDER BY t.available_on
  RETURN collect(t {
    .transaction_id, .type, .amount, .available_on,
    initiated_by: [(who:Customer)-[:INITIATED]->(t) | who.name][0],
    hold_rules: """
    + _HOLD_RULES
    + """
  }) AS pending_deposits
}
RETURN a.account_id AS account_id, a.nickname AS nickname,
       a.available_balance AS available_balance, $as_of AS as_of,
       pending_deposits, payments
"""
)
