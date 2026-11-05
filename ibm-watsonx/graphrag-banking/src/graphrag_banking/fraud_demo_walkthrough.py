"""Run the staff and fraud demo from docs/fraud-demo-walkthrough.md in a terminal.

Each step prints a header with its number and title, where it runs and the exact
command. The command's output follows, then a "Captured" line for each value a
later step uses. A step runs on its own with ``--steps``. The runner only reads,
chats and scores: it never creates, imports or deploys an Orchestrate object and
never starts an Aura Graph Analytics session.

Steps:
   1  Environment and tenant check
   2  Connection loaded: banker_creds
   3  Staff tools loaded
   4  Agents and knowledge base loaded
   5  What Aura holds: the connected groups Graph Data Science found
   6  Set the scene: the application facts, queried from Aura
   7  The failure: credit_analyst alone
   8  The fix: bank_supervisor in a new chat
   9  The follow-up: the same chat as step 8
  10  How GraphRAG changed the answer: score credit_analyst against bank_supervisor
  11  The proof: run orchestrate/fraud_proof_query.cypher against Aura

It needs the orchestrate CLI with an active environment, which ``make wxo-env``
sets up, and the ADK installed with ``uv tool install``. Commands run from the
project root. Each answer and the scoring files go to ``--out-dir``.

Usage:
  uv run fraud-demo-walkthrough
  uv run fraud-demo-walkthrough --steps 7-9
  uv run fraud-demo-walkthrough --steps 9 --thread-id <bank_supervisor thread ID>
  uv run fraud-demo-walkthrough --skip-scoring
"""

import argparse
import json
import logging
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from neo4j import RoutingControl

from graphrag_banking.config import PROJECT_ROOT, get_driver, load_settings
from graphrag_banking.demo_walkthrough import (
    _SAVED_REPORT,
    _THREAD_ID,
    EVAL_SCRIPTS,
    MAX_WIDTH,
    Captured,
    Console,
    Step,
    StepError,
    Walkthrough,
    Where,
    _capture,
    _native_agent,
    _orchestrate_json,
    _parse_one,
    _relative,
    _shell,
    _table,
    find_target,
)
from graphrag_banking.eval_local import Check, load_scenarios, routing_checks
from graphrag_banking.staff_tools import (
    _CREDIT_TYPES,
    _DAYS_PER_YEAR,
    _DEPOSITS,
    _MY_APPLICATION,
    _REVENUE_DAYS,
    StaffContext,
    get_connected_group,
)

logger = logging.getLogger(__name__)

SUPERVISOR = "bank_supervisor"
CREDIT_ANALYST = "credit_analyst"
FRAUD_INVESTIGATOR = "fraud_investigator"
POLICY_AGENT = "banking_policy"
STAFF_AGENTS = (SUPERVISOR, CREDIT_ANALYST, FRAUD_INVESTIGATOR, POLICY_AGENT)
CONNECTION_NAME = "banker_creds"
KNOWLEDGE_BASE_NAME = "banking_policies"
STAFF_TOOLS = (
    "find_my_client",
    "get_application",
    "check_lending_rules",
    "get_beneficial_owners",
    "get_connected_group",
    "find_circular_flows",
    "screen_business",
)
# The model bank_supervisor.yaml names, so step 1 can show the tenant offers it.
SUPERVISOR_MODEL = "virtual-model/openai/gpt-6-luna"
COLLABORATOR_PREFIX = "chat_with_collaborator_"
CONNECTION_SCRIPT = PROJECT_ROOT / "orchestrate" / "create_staff_connection.sh"
PROOF_QUERY_PATH = PROJECT_ROOT / "orchestrate" / "fraud_proof_query.cypher"
# Dana Whitfield, the banker the connection fixes and every question comes from.
BANKER_ID = "RM-07"
APPLICATION_ID = "APP-1001"
APPLICANT_ID = "B-1002"
APPLICANT = "Ortega Builders"
# The fraud tools whose result holds the applicant's connected group.
GROUP_TOOLS = ("get_connected_group", "screen_business")
FAILURE_SCENARIO = "E"
FOLLOW_UP_SCENARIO = "H"
SCORED_SCENARIO = "E"

# The groups build-groups wrote, with each group's most central member and
# whether the applicant is in it.
GROUPS_CYPHER = """
MATCH (g:ConnectedGroup)
RETURN g.group_id AS group_id, g.size AS size,
       COLLECT {
         MATCH (m)-[r:IN_GROUP]->(g)
         WITH m.name AS name, r.centrality AS score
         ORDER BY score DESC, name
         LIMIT 1
         RETURN {name: name, score: score}
       }[0] AS most_central,
       exists {
         (:Business {business_id: $business_id})-[:IN_GROUP]->(g)
       } AS has_applicant
ORDER BY group_id
"""

# The doc's Step 1 numbers. Step 6 compares the graph with them.
DOC_FACTS = {
    "amount": 400_000,
    "stated_revenue": 2_440_000,
    "deposits": 610_000,
    "verified_revenue": 2_440_000,
    "max_line": 610_000,
    "approval_limit": 500_000,
}

# The staff_tools queries run as they are, so the numbers match what the agents
# see. Only the final RETURN is new.
SCENE_CYPHER = (
    _MY_APPLICATION
    + _DEPOSITS
    + """
MATCH (rule:LendingRule {rule_code: 'LEND-BUSLINE-REV'})
RETURN app.application_id AS application_id, app.type AS type,
       app.amount AS amount, app.stated_annual_revenue AS stated_revenue,
       total_deposits AS deposits, rule.percent AS line_percent,
       banker.name AS banker, banker.approval_limit AS approval_limit
"""
)

_ROUTING_PASSED = "✔"
_ROUTING_FAILED = "✖"
_CALLED_TOOL = re.compile(r"Called tool '([^']+)'")
_TOOL_AGENT = re.compile(r"Agent:\s*(\S+)")
_KEYS_ARRAY = re.compile(r"^KEYS=\(([^)]*)\)", re.MULTILINE)
_NODE_NAME_KEYS = (
    "name",
    "number",
    "device_id",
    "application_id",
    "account_id",
    "transaction_id",
    "loan_id",
    "group_id",
    "rule_code",
)


@dataclass
class FraudWalkthrough(Walkthrough):
    """The shared walkthrough state, plus what the staff steps look up once."""

    tool_names: dict[str, str] = field(default_factory=dict)
    agent_names: dict[str, str] = field(default_factory=dict)
    supervisor_passed: bool | None = None


# ---- Pure helpers ---------------------------------------------------------------


def parse_steps(value: str, valid: Iterable[int]) -> list[int]:
    """Parse "1,3-5" into [1, 3, 4, 5]. Every number must be in ``valid``."""
    allowed = set(valid)
    numbers: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start, end = (int(p) for p in part.split("-", 1))
                numbers.update(range(start, end + 1))
            else:
                numbers.add(int(part))
        except ValueError as e:
            raise argparse.ArgumentTypeError(f"Bad step range: {part}") from e
    if not numbers or not numbers <= allowed:
        raise argparse.ArgumentTypeError(
            f"Steps must be between {min(allowed)} and {max(allowed)}, got {value}"
        )
    return sorted(numbers)


def connection_keys(script: str) -> list[str]:
    """The key names create_staff_connection.sh sets. Never the values."""
    if (match := _KEYS_ARRAY.search(script)) is None:
        return []
    return match[1].split()


def pick_connections(connections: list[dict[str, Any]], app_id: str) -> list[dict]:
    return [c for c in connections if c.get("app_id") == app_id]


def pick_tools(tools: list[dict[str, Any]], names: Iterable[str]) -> list[dict]:
    """The named tools, in the order of ``names``."""
    by_name = {t.get("name"): t for t in tools}
    return [by_name[name] for name in names if name in by_name]


def tool_connections(tool: dict[str, Any]) -> list[str]:
    binding = (tool.get("binding") or {}).get("python") or {}
    return sorted(binding.get("connections") or {})


def tool_packages(tool: dict[str, Any]) -> list[str]:
    binding = (tool.get("binding") or {}).get("python") or {}
    return list(binding.get("requirements") or [])


def names_for(ids: Iterable[str], lookup: dict[str, str]) -> list[str]:
    """Replace Orchestrate IDs with names, keeping an unknown ID as it is."""
    return sorted(lookup.get(i, i) for i in ids)


def trace_calls(output: str) -> list[tuple[str, str]]:
    """The (agent, tool) pairs in a chat's Reasoning Trace, in call order."""
    calls: list[tuple[str, str]] = []
    tool: str | None = None
    for line in output.splitlines():
        if match := _CALLED_TOOL.search(line):
            tool = match[1]
        elif tool is not None and (match := _TOOL_AGENT.search(line)):
            calls.append((match[1], tool))
            tool = None
    return calls


def call_kind(tool: str) -> str:
    """What a traced tool call is: a collaborator, a graph tool, or the KB."""
    if tool.startswith(COLLABORATOR_PREFIX):
        return "collaborator call"
    if tool in STAFF_TOOLS:
        return "graph tool"
    if tool == KNOWLEDGE_BASE_NAME:
        return "knowledge base"
    return "other"


def collaborators_called(calls: list[tuple[str, str]], asked: str) -> list[str]:
    """Collaborators the asked agent sent the question to, or that ran a tool."""
    names = {
        tool.removeprefix(COLLABORATOR_PREFIX)
        for _, tool in calls
        if tool.startswith(COLLABORATOR_PREFIX)
    }
    names |= {agent for agent, _ in calls if agent != asked}
    return sorted(names)


def rule_codes(value: Any) -> list[str]:
    """Every rule_code anywhere in a tool result, sorted without repeats."""
    found: set[str] = set()
    match value:
        case dict():
            if isinstance(value.get("rule_code"), str):
                found.add(value["rule_code"])
            for item in value.values():
                found.update(rule_codes(item))
        case list():
            for item in value:
                found.update(rule_codes(item))
    return sorted(found)


def money(value: float) -> str:
    return f"${value:,.0f}"


def scene_rows(row: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """The application facts from the graph next to the doc's Step 1 numbers."""
    deposits = row["deposits"]
    verified = deposits * _DAYS_PER_YEAR / _REVENUE_DAYS
    max_line = verified * row["line_percent"] / 100
    facts = [
        ("Amount", row["amount"], DOC_FACTS["amount"]),
        ("Stated annual revenue", row["stated_revenue"], DOC_FACTS["stated_revenue"]),
        (f"Deposits, last {_REVENUE_DAYS} days", deposits, DOC_FACTS["deposits"]),
        (
            f"Verified annual revenue ({_REVENUE_DAYS}-day deposits annualized)",
            verified,
            DOC_FACTS["verified_revenue"],
        ),
        (
            f"Largest line, {row['line_percent']} percent of verified revenue",
            max_line,
            DOC_FACTS["max_line"],
        ),
        (
            f"{row['banker']}'s approval limit",
            row["approval_limit"],
            DOC_FACTS["approval_limit"],
        ),
    ]
    return [
        (name, money(actual), money(doc), "yes" if actual == doc else "NO")
        for name, actual, doc in facts
    ]


def group_rows(groups: list[dict[str, Any]]) -> list[tuple[str, str, str, str, str]]:
    """One row per connected group: size, most central member, and the applicant."""
    return [
        (
            g["group_id"],
            str(g["size"]),
            g["most_central"]["name"],
            f"{g['most_central']['score']:.2f}",
            "yes" if g["has_applicant"] else "-",
        )
        for g in groups
    ]


def group_readers(calls: list[tuple[str, str]]) -> list[str]:
    """The fraud tools that read the connected group in a chat, in call order."""
    return list(
        dict.fromkeys(
            tool
            for agent, tool in calls
            if agent == FRAUD_INVESTIGATOR and tool in GROUP_TOOLS
        )
    )


def member_rows(result: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """The members of a get_connected_group result, most central first."""
    return [
        (
            m["name"],
            m["kind"].lower(),
            "-" if m["centrality"] is None else f"{m['centrality']:.2f}",
            m["banker"] or "-",
        )
        for m in result["members"]
    ]


def identifier_rows(result: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """The shared identifiers of a get_connected_group result.

    A home address has no value, so only who shares it is shown.
    """
    return [
        (
            i["kind"].lower(),
            i["value"] or "home address",
            str(len(i["used_by"])),
            str(len(i["applicants"])),
        )
        for i in result["shared_identifiers"]
    ]


def answer_fact_rows(
    runs: list[dict[str, Any]], agents: list[str]
) -> list[tuple[str, ...]]:
    """One row per answer fact with PASS or FAIL for each agent, from a report."""
    by_agent = {
        agent: {
            c["fact"]: c["passed"]
            for run in runs
            if run["agent"] == agent
            for c in run["checks"]
            if c["kind"] == "answer"
        }
        for agent in agents
    }
    facts = list(dict.fromkeys(f for found in by_agent.values() for f in found))
    return [
        (
            fact,
            *(
                "PASS"
                if by_agent[a].get(fact)
                else "FAIL"
                if fact in by_agent[a]
                else "-"
                for a in agents
            ),
        )
        for fact in facts
    ]


def graph_tools(run: dict[str, Any]) -> str:
    """The distinct graph tools a run called, in call order."""
    names = (c["name"] for c in run["tool_calls"])
    return ", ".join(dict.fromkeys(n for n in names if n in STAFF_TOOLS))


def trace_found(run: dict[str, Any]) -> str:
    """How many of a run's trace facts its tool results contained."""
    trace = [c for c in run["checks"] if c["kind"] == "trace"]
    return f"{sum(c['passed'] for c in trace)} of {len(trace)}"


def markdown_table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]
    return "\n".join(lines) + "\n"


def node_label(node: Any) -> str:
    """A short name for a graph node, with the one detail worth reading."""
    props = dict(node)
    labels = set(node.labels)
    if "Chunk" in labels:
        return f"policy chunk {props.get('index')}"
    name = next((str(props[k]) for k in _NODE_NAME_KEYS if k in props), "?")
    if "Transaction" in labels and "amount" in props:
        return f"{name} ({money(props['amount'])})"
    if "Loan" in labels:
        return f"{name} ({props.get('status')}, balance {money(props['balance'])})"
    if "ConnectedGroup" in labels:
        return f"{name} ({props.get('size')} members)"
    return name


def rel_label(rel: Any) -> str:
    props = dict(rel)
    if "percent" in props:
        return f"{rel.type} {props['percent']:g}%"
    if "centrality" in props:
        return f"{rel.type} centrality {props['centrality']:.1f}"
    return str(rel.type)


def path_line(path: Any) -> str:
    """Write a path as ``A -[REL]-> B -[REL]-> C``."""
    parts = [node_label(path.nodes[0])]
    for rel, node in zip(path.relationships, path.nodes[1:], strict=True):
        parts += [f"-[{rel_label(rel)}]->", node_label(node)]
    return " ".join(parts)


def loop_total(paths: list[Any]) -> float:
    """The sum of the transactions on loop paths."""
    return sum(
        dict(node).get("amount", 0.0)
        for path in paths
        for node in path.nodes
        if "Transaction" in set(node.labels)
    )


# ---- Output helpers -------------------------------------------------------------


def _save(wt: FraudWalkthrough, name: str, text: str) -> Path:
    path = wt.out_dir / name
    path.write_text(text, encoding="utf-8")
    return path


def _print_checks(wt: FraudWalkthrough, checks: list[Check]) -> None:
    for check in checks:
        mark = _ROUTING_PASSED if check.passed else _ROUTING_FAILED
        style = "green" if check.passed else "red"
        wt.console.output(f"{wt.console.paint(mark, 'bold', style)} {check.fact}")


def _scenario(scenario_id: str) -> dict[str, Any]:
    return next(s for s in load_scenarios() if s["id"] == scenario_id)


def _chat(
    wt: FraudWalkthrough,
    agent: str,
    prompt: str,
    *,
    what: str,
    thread_id: str | None = None,
    save_as: str,
) -> tuple[str, str]:
    """Send one prompt with `orchestrate chat ask`. Returns the thread ID and the
    cleaned output, and saves the output under the output folder. ``what`` is the
    story this chat tells, printed on the step's What line."""
    cmd = ["orchestrate", "chat", "ask", "-n", agent]
    if thread_id is not None:
        cmd += ["--thread-id", thread_id]
    cmd += ["-r", prompt]
    where = (
        "The local CLI continues the chat that step 8 started, so the agent sees "
        "the earlier answer. "
        if thread_id
        else ""
    )
    wt.console.where_and_command(
        wt.target,
        Where.CLOUD,
        what,
        f"{where}The {agent} agent runs in Orchestrate with its model, tools and "
        "collaborators. The local CLI sends the prompt and prints the reasoning "
        "trace and answer. `echo q` ends the chat after the first answer.",
        ["echo", "q", "|", *_shell(cmd)],
    )
    _, output = wt.run(cmd, stdin="q\n")
    new_thread = _parse_one(_THREAD_ID, output, "thread ID", "orchestrate chat ask")
    saved = _save(wt, save_as, output + "\n")
    wt.console.captured(f"{agent} thread ID", new_thread)
    wt.console.captured("answer file", _relative(saved))
    return new_thread, output


def _print_calls(wt: FraudWalkthrough, calls: list[tuple[str, str]]) -> None:
    if not calls:
        wt.console.output("No tool calls in the reasoning trace.")
        return
    _table(
        wt,
        ("#", "Agent", "Tool", "What it is"),
        [
            (str(n), agent, tool, call_kind(tool))
            for n, (agent, tool) in enumerate(calls, start=1)
        ],
    )


def _staff_tool_list(wt: FraudWalkthrough) -> list[dict[str, Any]]:
    cmd = ["orchestrate", "tools", "list", "--verbose"]
    tools = _orchestrate_json(wt, cmd)
    wt.tool_names = {t["id"]: t["name"] for t in tools if "id" in t}
    return tools


# ---- Steps ----------------------------------------------------------------------


def step_environment(wt: FraudWalkthrough) -> None:
    env_cmd = ["orchestrate", "env", "list"]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "The demo runs on a live watsonx Orchestrate tenant. Every agent, tool and "
        "chat in the next steps lives there. Every fact they reason over comes from "
        "Neo4j Aura.",
        "The local CLI lists the Orchestrate environments it knows. The active one "
        "is the tenant every later step talks to.",
        _shell(env_cmd),
    )
    wt.run(env_cmd)
    wt.console.output("")
    wt.console.sub_header("1.1", "The models the demo uses")
    models_cmd = ["orchestrate", "models", "list"]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "Orchestrate hosts the models. The specialists run on gpt-oss-120b, and the "
        "supervisor runs on gpt-6-luna. How good an answer is depends on the graph "
        "context the tools hand the model.",
        "The local CLI asks the tenant which models it offers. bank_supervisor "
        f"names {SUPERVISOR_MODEL} in its agent file.",
        _shell(models_cmd),
    )
    status, output = wt.run_captured(models_cmd)
    if status != 0:
        raise StepError("`orchestrate models list` failed. Run `make wxo-env`.")
    offered = SUPERVISOR_MODEL in output
    _table(
        wt,
        ("Model", "Offered by the tenant"),
        [(SUPERVISOR_MODEL, "yes" if offered else "NO")],
    )
    where = "cloud" if wt.target.is_cloud else "local developer edition"
    _capture(wt, "environment", f"{wt.target.env_name} · {where} · {wt.target.host}")
    wt.console.output("")
    wt.console.note(
        "Nothing in this walkthrough creates, imports or deploys an Orchestrate "
        "object. It only reads, chats and scores."
    )


def step_connection(wt: FraudWalkthrough) -> None:
    cmd = ["orchestrate", "connections", "list", "--verbose"]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "Orchestrate keeps the Neo4j Aura credentials in a managed connection, "
        f"{CONNECTION_NAME}. Every staff tool reads it, so no password sits in a "
        "prompt or a file. The connection also fixes the banker to Dana, so every "
        "chat runs as Dana.",
        "The local CLI asks Orchestrate which connections it holds. The tenant has "
        f"many built-in ones, so this shows only {CONNECTION_NAME}, the connection "
        "that holds the Aura credentials and fixes the banker to Dana. The API "
        "never returns credential values, only whether they were entered.",
        _shell(cmd),
    )
    connections = pick_connections(_orchestrate_json(wt, cmd), CONNECTION_NAME)
    if not connections:
        raise StepError(
            f"Connection {CONNECTION_NAME} is not loaded in Orchestrate. Run "
            "`./orchestrate/create_staff_connection.sh`."
        )
    _table(
        wt,
        ("Connection", "Environment", "Type", "Scope", "Credentials entered"),
        [
            (
                c["name"],
                c["environment"],
                c["security_scheme"],
                c.get("preference") or "-",
                "yes" if c.get("credentials_entered") else "NO",
            )
            for c in connections
        ],
    )
    keys = connection_keys(CONNECTION_SCRIPT.read_text(encoding="utf-8"))
    wt.console.output("")
    wt.console.output(
        f"Keys set by {_relative(CONNECTION_SCRIPT)}, names only: {', '.join(keys)}"
    )
    wt.console.note(
        "Orchestrate stores these values. The tools read them when they run, so the "
        "credentials are not in the tool code or the agent instructions. The "
        "connection also fixes the signed-in banker, so no prompt can change whose "
        "book the tools read."
    )
    environments = ", ".join(c["environment"] for c in connections)
    _capture(wt, "connection", f"{CONNECTION_NAME} · {environments}")


def step_tools(wt: FraudWalkthrough) -> None:
    cmd = ["orchestrate", "tools", "list", "--verbose"]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "These seven Python tools are how the agents reach the graph. Each one runs "
        "a Cypher query in Neo4j Aura from inside Orchestrate. Three answer credit "
        "questions about one application. Four follow links across the graph: "
        "owners behind owners, shared phones and devices, and money that moves in "
        "a loop.",
        "The local CLI asks Orchestrate for its tools. The tenant holds many, so "
        "this shows the seven staff tools, with the connection and packages each "
        "one runs with.",
        _shell(cmd),
    )
    tools = _staff_tool_list(wt)
    staff = pick_tools(tools, STAFF_TOOLS)
    if len(staff) < len(STAFF_TOOLS):
        missing = ", ".join(set(STAFF_TOOLS) - {t["name"] for t in staff})
        raise StepError(
            f"Staff tools missing from Orchestrate: {missing}. Run `make wxo-staff-tools`."
        )
    _table(
        wt,
        ("Tool", "Connection", "Permission", "Packages"),
        [
            (
                t["name"],
                ", ".join(tool_connections(t)) or "-",
                t.get("permission") or "-",
                ", ".join(tool_packages(t)) or "-",
            )
            for t in staff
        ],
    )
    wt.console.note(
        "Each tool is a Python function that Orchestrate runs in its own runtime. "
        "It reads banker_creds, opens a Neo4j driver against Aura and runs Cypher "
        "there. Nothing runs on this laptop."
    )
    bound = {c for t in staff for c in tool_connections(t)}
    _capture(
        wt,
        "staff tools",
        f"{len(staff)} of {len(STAFF_TOOLS)} loaded · connection {', '.join(sorted(bound))}",
    )


def step_agents(wt: FraudWalkthrough) -> None:
    wt.console.sub_header("4.1", "The agents")
    cmd = ["orchestrate", "agents", "list", "--kind", "native", "--verbose"]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        f"Orchestrate routes the work between specialists. {CREDIT_ANALYST} sees "
        f"one application. {FRAUD_INVESTIGATOR} sees the network around it. "
        f"{SUPERVISOR} has no tools. It asks both and writes one answer.",
        "The local CLI asks Orchestrate for its native agents. The tenant holds "
        "other agents too, so this shows only the four staff agents. Orchestrate "
        "lists tools and collaborators by ID, so this step also looks the IDs up "
        "with `orchestrate tools list --verbose`.",
        _shell(cmd),
    )
    listed = _orchestrate_json(wt, cmd)
    agents = listed["native"] if isinstance(listed, dict) else listed
    chosen = [_native_agent(wt, agents, name) for name in STAFF_AGENTS]
    wt.agent_names = {a["id"]: a["name"] for a in agents if "id" in a}
    _staff_tool_list(wt)
    _table(
        wt,
        ("Agent", "Model", "Tools", "Collaborators", "Knowledge bases"),
        [
            (
                a["name"],
                a.get("llm") or "-",
                ", ".join(names_for(a.get("tools") or [], wt.tool_names)) or "-",
                ", ".join(names_for(a.get("collaborators") or [], wt.agent_names))
                or "-",
                ", ".join(a.get("knowledge_base") or []) or "-",
            )
            for a in chosen
        ],
    )
    supervisor = chosen[0]
    wt.console.note(
        f"{SUPERVISOR} has {len(supervisor.get('collaborators') or [])} "
        "collaborators and no tools of its own. It routes each question to the "
        "right specialists and writes one answer. That is Orchestrate "
        "multi-agent routing."
    )

    wt.console.sub_header("4.2", f"The {KNOWLEDGE_BASE_NAME} knowledge base")
    kb_cmd = [
        "orchestrate",
        "knowledge-bases",
        "status",
        "-n",
        KNOWLEDGE_BASE_NAME,
        "--verbose",
    ]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        f"The {KNOWLEDGE_BASE_NAME} knowledge base holds the policy documents for "
        "plain vector search. The graph holds the same policies as rules. Each rule "
        "links to its policy text and to the facts it applies to, which is what "
        "lets an answer cite a rule code.",
        f"The local CLI asks Orchestrate about the {KNOWLEDGE_BASE_NAME} knowledge "
        f"base that {POLICY_AGENT} reads. Orchestrate chunks and indexes the policy "
        "documents itself.",
        _shell(kb_cmd),
    )
    kb = _orchestrate_json(wt, kb_cmd)
    documents = kb.get("documents") or []
    policy = chosen[3]
    uses_it = kb.get("id") in (policy.get("knowledge_base") or [])
    _table(
        wt,
        (
            "Knowledge base",
            "Ready",
            "Index status",
            "Documents",
            f"Used by {POLICY_AGENT}",
        ),
        [
            (
                kb["name"],
                "yes" if kb.get("ready") else "NO",
                kb.get("built_in_index_status") or "-",
                str(len(documents)),
                "yes" if uses_it else "NO",
            )
        ],
    )
    wt.console.note(
        "The graph holds the same policies as rules, so the other agents can link a "
        "rule to the facts it applies to."
    )
    _capture(
        wt,
        "agents",
        f"{', '.join(STAFF_AGENTS)} · knowledge base {kb['name']} with "
        f"{len(documents)} documents",
    )


def step_groups(wt: FraudWalkthrough) -> None:
    settings = load_settings()
    params = {"business_id": APPLICANT_ID}
    host = urlparse(settings.neo4j_uri).hostname or settings.neo4j_uri
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "Before any agent asks a question, Neo4j Graph Data Science scans the whole "
        "bank. It joins people and businesses that share a phone, an email, a "
        "device or an address, and writes each cluster back to Aura as a group. It "
        "also scores who sits at the center of each group. The agents do not have "
        "to find the ring. They read it from the graph.",
        f"This script runs the Cypher below against Neo4j Aura at {host} with the "
        "neo4j driver, in a read transaction. `uv run build-groups` wrote the groups "
        "during the rebuild. This step only reads them, so it starts no Aura Graph "
        "Analytics session. Orchestrate is not involved.",
        ["neo4j driver: execute_query(<Cypher below>, routing_=READ)"],
    )
    for line in GROUPS_CYPHER.strip().splitlines():
        wt.console.output(wt.console.paint(line, "yellow"))
    wt.console.output(
        wt.console.paint(
            "Parameters: " + json.dumps(params, separators=(", ", ": ")), "dim"
        )
    )
    wt.console.rule("result")
    with get_driver(settings) as driver:
        records, _, _ = driver.execute_query(
            GROUPS_CYPHER,
            params,
            database_=settings.neo4j_database,
            routing_=RoutingControl.READ,
        )
    if not records:
        raise StepError(
            "The graph has no connected groups. Run `uv run build-groups`, which "
            "starts a billed Aura Graph Analytics session."
        )
    groups = [record.data() for record in records]
    _table(
        wt,
        ("Group", "Members", "Most central member", "Centrality", f"Holds {APPLICANT}"),
        group_rows(groups),
    )
    found = next((g for g in groups if g["has_applicant"]), None)
    if found is None:
        wt.console.note(f"{APPLICANT} is in no connected group.")
        _capture(wt, "connected groups", f"{len(groups)} groups · {APPLICANT} in none")
        return
    central = found["most_central"]["name"]
    wt.console.note(
        f"Graph Data Science found {len(groups)} groups across every banker's book. "
        f"{APPLICANT} is in {found['group_id']}, with {found['size']} members, and "
        f"{central} sits at its center. Step 8 shows the fraud tools reading this "
        "group."
    )
    _capture(
        wt,
        "connected groups",
        f"{len(groups)} groups · {APPLICANT} in {found['group_id']} · "
        f"{found['size']} members · most central {central}",
    )


def step_scene(wt: FraudWalkthrough) -> None:
    settings = load_settings()
    as_of = settings.demo_as_of
    params = {
        "banker_id": BANKER_ID,
        "application_id": APPLICATION_ID,
        "date_from": as_of - timedelta(days=_REVENUE_DAYS),
        "date_to": as_of,
        "credit_types": _CREDIT_TYPES,
    }
    host = urlparse(settings.neo4j_uri).hostname or settings.neo4j_uri
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "This is one loan application, as Neo4j Aura stores it. Ortega Builders "
        "asks for $400,000, revenue supports it, and it is under Dana's limit. "
        "Every fact here is true, and none of them looks suspicious. The risk is in "
        "the links around this application.",
        f"This script runs the Cypher below against Neo4j Aura at {host} with the "
        "neo4j driver, in a read transaction. It is the query the credit tools run, "
        "with a new RETURN. Orchestrate is not involved.",
        ["neo4j driver: execute_query(<Cypher below>, routing_=READ)"],
    )
    for line in SCENE_CYPHER.strip().splitlines():
        wt.console.output(wt.console.paint(line, "yellow"))
    wt.console.output(
        wt.console.paint(
            "Parameters: "
            + json.dumps(
                {k: str(v) for k, v in params.items()}, separators=(", ", ": ")
            ),
            "dim",
        )
    )
    wt.console.rule("result")
    with get_driver(settings) as driver:
        records, _, _ = driver.execute_query(
            SCENE_CYPHER,
            params,
            database_=settings.neo4j_database,
            routing_=RoutingControl.READ,
        )
    if not records:
        raise StepError(
            f"The graph has no application {APPLICATION_ID} in {BANKER_ID}'s book. "
            "Run `make rebuild`."
        )
    row = records[0].data()
    rows = scene_rows(row)
    _table(
        wt,
        (
            f"{row['application_id']}, {row['type']}",
            "From the graph",
            "Doc Step 1",
            "Match",
        ),
        rows,
    )
    matches = all(r[3] == "yes" for r in rows)
    wt.console.note(
        "The request is under the largest line and under the approval limit, so on "
        "paper the banker can approve it. Step 7 shows what an AI assistant says."
    )
    _capture(
        wt,
        "scene",
        f"{row['application_id']} · {money(row['amount'])} · "
        f"{'matches the doc' if matches else 'DOES NOT match the doc'}",
    )


def step_failure(wt: FraudWalkthrough) -> None:
    scenario = _scenario(FAILURE_SCENARIO)
    thread_id, output = _chat(
        wt,
        CREDIT_ANALYST,
        scenario["prompt"],
        what=f"{CREDIT_ANALYST} reads the graph, but only the application and the "
        "lending rules. Its context stops at one node, so it sees strong deposits "
        "and a request under the limit. Watch it recommend approval.",
        save_as=f"step7-{CREDIT_ANALYST}.txt",
    )
    calls = trace_calls(output)
    wt.console.output("")
    _print_calls(wt, calls)
    wt.console.note(
        f"{CREDIT_ANALYST} checks one application against the lending and approval "
        "rules. It cannot see who owns the business, who else applied or where the "
        "deposits came from."
    )
    wt.captured.baseline_thread_id = thread_id


def step_fix(wt: FraudWalkthrough) -> None:
    scenario = _scenario(FAILURE_SCENARIO)
    thread_id, output = _chat(
        wt,
        SUPERVISOR,
        scenario["prompt"],
        what=f"{SUPERVISOR} sends the same question to {CREDIT_ANALYST} and "
        f"{FRAUD_INVESTIGATOR}. The fraud tools follow multi-hop paths in the "
        "graph: an owner hidden behind a holding company, a shared phone and "
        "device, and money that loops back. The model now reasons over connected "
        "facts, and each red flag names the rule it comes from.",
        save_as=f"step8-{SUPERVISOR}.txt",
    )
    wt.captured.thread_id = thread_id
    calls = trace_calls(output)
    wt.console.output("")
    _print_calls(wt, calls)
    wt.console.output("")
    wt.console.output(
        wt.console.paint("Routing checks from eval/scenarios.yaml", "bold")
    )
    _print_checks(wt, routing_checks(scenario, collaborators_called(calls, SUPERVISOR)))
    wt.console.note(
        f"{SUPERVISOR} sent the question to {CREDIT_ANALYST} and "
        f"{FRAUD_INVESTIGATOR}. Their graph tools found the owner, the ring and the "
        "money loop. Step 9 continues in this chat."
    )
    _print_group(wt, group_readers(calls))


def _print_group(wt: FraudWalkthrough, readers: list[str]) -> None:
    """Print the connected group the fraud tools read, from the same function."""
    wt.console.sub_header("8.1", "The connected group the fraud tools read")
    settings = load_settings()
    host = urlparse(settings.neo4j_uri).hostname or settings.neo4j_uri
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "Graph Data Science found this group before the chat began, so "
        f"{FRAUD_INVESTIGATOR} reads it in one tool call. The group reaches into "
        "other bankers' books, so Dana's own book never shows it. The highest "
        "centrality marks the center of the ring.",
        "This script calls get_connected_group from staff_tools, the same function "
        f"the Orchestrate tool runs, for {APPLICANT_ID} as {BANKER_ID}. It runs "
        f"against Neo4j Aura at {host} in a read transaction, so the result prints "
        "as tables. Orchestrate is not involved.",
        [f"staff_tools.get_connected_group(<{BANKER_ID} context>, '{APPLICANT_ID}')"],
    )
    with get_driver(settings) as driver:
        context = StaffContext(
            driver, settings.neo4j_database, BANKER_ID, settings.demo_as_of
        )
        result = get_connected_group(context, APPLICANT_ID)
    if "error" in result:
        raise StepError(result["error"])
    if result["group"] is None:
        wt.console.output(f"{APPLICANT} is in no connected group.")
        return
    _table(wt, ("Member", "Kind", "Centrality", "Banker"), member_rows(result))
    wt.console.output("")
    _table(
        wt,
        ("Shared identifier", "Value", "Parties", "Applicants"),
        identifier_rows(result),
    )
    read_by = (
        f"In this chat, {FRAUD_INVESTIGATOR} read this group through "
        f"{', '.join(readers)}."
        if readers
        else f"In this chat, {FRAUD_INVESTIGATOR} called no tool that reads the group."
    )
    wt.console.note(
        f"{result['most_central']} is the most central member of "
        f"{result['group']['group_id']}. {read_by}"
    )


def step_follow_up(wt: FraudWalkthrough) -> None:
    scenario = _scenario(FOLLOW_UP_SCENARIO)
    thread_id = wt.captured.thread_id
    assert thread_id is not None
    _, output = _chat(
        wt,
        SUPERVISOR,
        scenario["prompt"],
        what="The same chat continues. The supervisor remembers the fraud referral "
        f"from step 8, so it sends this question to {POLICY_AGENT} alone. The graph "
        "findings shape the next answer, and Dana gets words that do not tip off "
        "the client.",
        thread_id=thread_id,
        save_as=f"step9-{SUPERVISOR}.txt",
    )
    calls = trace_calls(output)
    wt.console.output("")
    _print_calls(wt, calls)
    wt.console.output("")
    wt.console.output(
        wt.console.paint("Routing checks from eval/scenarios.yaml", "bold")
    )
    _print_checks(wt, routing_checks(scenario, collaborators_called(calls, SUPERVISOR)))
    wt.console.note(
        f"This is a policy question, so {SUPERVISOR} sent it to {POLICY_AGENT} alone. "
        "The chat history tells it the question is about Ortega Builders' application."
    )


def step_score(wt: FraudWalkthrough) -> None:
    runs_dir = wt.out_dir / "runs"
    agents = [CREDIT_ANALYST, SUPERVISOR]
    wt.console.sub_header("10.1", f"Send scenario {SCORED_SCENARIO} to both agents")
    run_cmd = [
        str(wt.adk_python),
        "-I",
        f"{EVAL_SCRIPTS}/run_agent.py",
        str(runs_dir),
        "--agents",
        ",".join(agents),
        "--scenarios",
        SCORED_SCENARIO,
        "--persona",
        "staff",
    ]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL_TO_CLOUD,
        "Now the difference gets measured. The same Scenario "
        f"{SCORED_SCENARIO} prompt goes to {CREDIT_ANALYST} and to {SUPERVISOR}. "
        "Each answer is saved with the graph results behind it.",
        "run_agent.py runs locally with the ADK's Python. It sends the scenario's "
        "prompt to each agent through the Orchestrate API, and saves each answer "
        "and tool response as JSON.",
        _shell(run_cmd),
    )
    wt.run(run_cmd)
    if not sorted(runs_dir.glob("*.json")):
        raise StepError(f"run_agent.py saved no runs in {runs_dir}.")

    wt.console.sub_header("10.2", "Score the saved answers")
    score_cmd = ["uv", "run", "python", f"{EVAL_SCRIPTS}/score.py", str(runs_dir)]
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "Each answer is scored fact by fact. The table shows which facts each agent "
        "found and the graph pattern that found each one. Only the agent with "
        "multi-hop graph context finds the hidden owner, the ring and the money "
        "loop.",
        "score.py runs locally with the project's Python. It applies the scenario's "
        f"checks to each answer. {CREDIT_ANALYST} is expected to fail, so the exit "
        "status is not the verdict. The table below is.",
        _shell(score_cmd),
    )
    _, output = wt.run(score_cmd, check=False)
    _save(wt, "score.txt", output + "\n")
    report_match = _SAVED_REPORT.search(output)
    if report_match is None:
        raise StepError("score.py saved no report.")
    report = json.loads((PROJECT_ROOT / report_match[1]).read_text(encoding="utf-8"))
    runs = report["runs"]

    wt.console.sub_header("10.3", "Fact by fact")
    header = ("Fact", f"{CREDIT_ANALYST} alone", SUPERVISOR)
    rows = answer_fact_rows(runs, agents)
    _table(wt, header, rows)
    _save(wt, "fact-table.md", markdown_table(header, rows))
    wt.console.output("")
    wt.console.output(wt.console.paint("What the tools returned", "bold"))
    _table(
        wt,
        (
            "Agent",
            "Graph tools called",
            "Rule codes in the tool results",
            "Trace facts found",
        ),
        [
            (
                run["agent"],
                graph_tools(run) or "-",
                ", ".join(rule_codes([c["result"] for c in run["tool_calls"]])) or "-",
                trace_found(run),
            )
            for agent in agents
            for run in runs
            if run["agent"] == agent
        ],
    )
    wt.console.note(
        f"{CREDIT_ANALYST} saw one application and passed it. {SUPERVISOR} also asked "
        f"{FRAUD_INVESTIGATOR}, whose graph tools returned the ownership chain, the "
        "shared identifiers, the loop and the rules behind each red flag. "
        f"The Markdown table is in {_relative(wt.out_dir / 'fact-table.md')}."
    )
    supervisor_run = next(r for r in runs if r["agent"] == SUPERVISOR)
    wt.supervisor_passed = bool(supervisor_run["passed"])
    verdict = "all checks passed" if wt.supervisor_passed else "some checks failed"
    _capture(wt, "score report", f"{report_match[1]} · {SUPERVISOR}: {verdict}")


def step_proof(wt: FraudWalkthrough) -> None:
    settings = load_settings()
    query = PROOF_QUERY_PATH.read_text(encoding="utf-8")
    host = urlparse(settings.neo4j_uri).hostname or settings.neo4j_uri
    wt.console.where_and_command(
        wt.target,
        Where.LOCAL,
        "Every fact in the supervisor's answer is a node or a link in Neo4j Aura. "
        "This query draws them all: Hale's ownership chain, the written-off loan, "
        "the shared phone and device, the money loop, and each rule with its "
        "policy text. Anyone can check the answer against the graph.",
        f"This script runs {_relative(PROOF_QUERY_PATH)} against Neo4j Aura at "
        f"{host} with the neo4j driver, in a read transaction. Orchestrate is not "
        "involved.",
        [
            f"neo4j driver: execute_query(<{_relative(PROOF_QUERY_PATH)}>, routing_=READ)"
        ],
    )
    for line in query.strip().splitlines():
        wt.console.output(wt.console.paint(line, "yellow"))
    wt.console.rule("result")
    with get_driver(settings) as driver:
        records, _, _ = driver.execute_query(
            query, database_=settings.neo4j_database, routing_=RoutingControl.READ
        )
    if not records:
        raise StepError("The proof query returned no row. Run `make rebuild`.")
    row = records[0]
    collections = list(row.keys())
    _table(
        wt,
        ("Collection", "Paths"),
        [(key, str(len(row[key]))) for key in collections],
    )
    for key in collections:
        wt.console.output("")
        wt.console.output(wt.console.paint(key, "bold"))
        for path in row[key]:
            wt.console.output(f"  {path_line(path)}")
    total = loop_total(row["loop_in"])
    wt.console.output("")
    wt.console.output(
        f"Loop transfers into A-3001: {len(row['loop_in'])} totalling {money(total)}"
    )
    wt.console.note(
        "To see the graph, paste the query from "
        f"{_relative(PROOF_QUERY_PATH)} into the Aura Query tool and switch to the "
        "graph view. Each fact above is a node or a link there."
    )
    counts = ", ".join(f"{key} {len(row[key])}" for key in collections)
    _capture(wt, "proof query", counts)


STEPS = [
    Step(1, "Environment and tenant check", step_environment),
    Step(2, f"Connection loaded: {CONNECTION_NAME}", step_connection),
    Step(3, "Staff tools loaded", step_tools),
    Step(4, "Agents and knowledge base loaded", step_agents),
    Step(5, "What Aura holds: the connected groups", step_groups),
    Step(6, "Set the scene: the application facts from Aura", step_scene),
    Step(7, f"The failure: {CREDIT_ANALYST} alone", step_failure),
    Step(8, f"The fix: {SUPERVISOR} in a new chat", step_fix),
    Step(9, "The follow-up: the same chat as step 8", step_follow_up),
    Step(
        10, f"How GraphRAG changed the answer: scenario {SCORED_SCENARIO}", step_score
    ),
    Step(11, "The proof: the graph behind the answer", step_proof),
]
SCORING_STEP = 10
THREAD_STEPS = (8, 9)


# ---- Setup ----------------------------------------------------------------------


def check_inputs(selected: list[int], thread_id: str | None) -> None:
    """Fail before any cloud call when a step's input will be missing."""
    chosen = set(selected)
    if 9 in chosen and 8 not in chosen and thread_id is None:
        raise StepError(
            f"Step 9 needs the {SUPERVISOR} thread ID from step 8. Include step 8 or "
            "pass --thread-id."
        )


def print_summary(wt: FraudWalkthrough, elapsed: float) -> None:
    rows = list(wt.captured.loaded.items())
    if wt.captured.thread_id:
        rows.append((f"{SUPERVISOR} thread ID", wt.captured.thread_id))
    if wt.captured.baseline_thread_id:
        rows.append((f"{CREDIT_ANALYST} thread ID", wt.captured.baseline_thread_id))
    if wt.supervisor_passed is not None:
        verdict = (
            wt.console.paint("PASS", "bold", "green")
            if wt.supervisor_passed
            else wt.console.paint("FAIL, see step 10", "bold", "red")
        )
        rows.append((f"{SUPERVISOR} score", verdict))
    rows += [("Output folder", _relative(wt.out_dir)), ("Elapsed", f"{elapsed:.0f}s")]
    wt.console.banner("Walkthrough complete: captured values", rows)


def main() -> None:
    numbers = [s.number for s in STEPS]
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--steps",
        type=lambda v: parse_steps(v, numbers),
        default=numbers,
        help='Steps to run, such as "1-4" or "7,8,9". Default: all.',
    )
    parser.add_argument(
        "--thread-id",
        help=f"{SUPERVISOR} thread ID for step 9 without step 8.",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help=f"Skip step {SCORING_STEP}, which sends scenario {SCORED_SCENARIO} to "
        "both agents again.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Where to write each answer and the scoring files. Default: a new "
        "temporary folder.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    width = min(shutil.get_terminal_size((MAX_WIDTH, 24)).columns, MAX_WIDTH)
    console = Console(color=sys.stdout.isatty(), width=width)
    selected = [n for n in args.steps if not (args.skip_scoring and n == SCORING_STEP)]

    started = time.monotonic()
    try:
        check_inputs(selected, args.thread_id)
        target = find_target()
        if args.out_dir is None:
            out_dir = Path(tempfile.mkdtemp(prefix="fraud-demo-walkthrough-"))
        else:
            out_dir = args.out_dir.resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
        wt = FraudWalkthrough(
            console=console,
            target=target,
            out_dir=out_dir,
            agent=SUPERVISOR,
            baseline_agent=CREDIT_ANALYST,
            prompts={s["id"]: s["prompt"] for s in load_scenarios()},
            captured=Captured(thread_id=args.thread_id),
            total_steps=len(STEPS),
        )
        where = "cloud" if target.is_cloud else "local developer edition"
        console.banner(
            "Staff and fraud demo walkthrough",
            [
                ("Environment", f"{target.env_name} · {where} · {target.host}"),
                ("Agents", ", ".join(STAFF_AGENTS)),
                ("Steps", ", ".join(str(n) for n in selected)),
                ("Output folder", _relative(out_dir)),
            ],
        )
        for step in STEPS:
            if step.number not in selected:
                continue
            console.step_header(step.number, wt.total_steps, step.title)
            step.run(wt)
    except StepError as e:
        print(f"\n  {console.paint('✖ Failed', 'bold', 'red')}  {e}", file=sys.stdout)
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n  {console.paint('Interrupted', 'bold', 'yellow')}")
        sys.exit(130)
    print_summary(wt, time.monotonic() - started)
    if wt.supervisor_passed is False:
        sys.exit(1)


if __name__ == "__main__":
    main()
