"""List the banking demo's objects saved in watsonx Orchestrate.

Each `orchestrate ... list` command prints every object in the tenant. This script
keeps only the objects the two demos use and prints them as tables: the
connections, tools, knowledge base, and agents that `make wxo-setup` and
`make wxo-staff-setup` create, plus the optional fraud referral tools and flow.

Usage: uv run python orchestrate/list_demo.py
"""

from typing import Any

from build_agent import TOOLS
from check_setup import (
    AGENTS,
    CONNECTION,
    KNOWLEDGE_BASE,
    _orchestrate,
    _orchestrate_json,
)

STAFF_CONNECTION = "banker_creds"
STAFF_TOOLS = [
    "find_my_client",
    "get_application",
    "check_lending_rules",
    "get_beneficial_owners",
    "get_connected_group",
    "find_circular_flows",
    "screen_business",
]
# Imported by build_referral_tools.sh, which is optional.
REFERRAL_TOOLS = ["create_fraud_referral", "resolve_fraud_referral", "fraud_referral"]
STAFF_AGENTS = [
    "banking_policy",
    "credit_analyst",
    "fraud_investigator",
    "bank_supervisor",
]


def _table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a bordered table. A cell may hold several lines split by newlines."""
    widths = [
        max(len(line) for cell in column for line in cell.split("\n"))
        for column in zip(headers, *rows)
    ]

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w + 2) for w in widths) + right

    def line(cells: list[str]) -> None:
        split = [cell.split("\n") for cell in cells]
        height = max(len(parts) for parts in split)
        padded = [parts + [""] * (height - len(parts)) for parts in split]
        for parts in zip(*padded):
            row = " │ ".join(p.ljust(w) for p, w in zip(parts, widths))
            print(f"│ {row} │")

    print(border("┌", "┬", "┐"))
    line(headers)
    print(border("├", "┼", "┤"))
    for i, row in enumerate(rows):
        if i:
            print(border("├", "┼", "┤"))
        line(row)
    print(border("└", "┴", "┘"))


def _section(title: str) -> None:
    print(f"\n{title}")


def _active_environment() -> str:
    return next(
        (
            line.split()[0]
            for line in _orchestrate("env", "list").splitlines()
            if "(active)" in line
        ),
        "none",
    )


def list_connections() -> None:
    _section("Connections")
    saved = _orchestrate_json("connections", "list")
    rows = []
    for app_id in (CONNECTION, STAFF_CONNECTION):
        found = [c for c in saved if c["app_id"] == app_id]
        entered = {c["environment"] for c in found if c["credentials_entered"]}
        rows.append(
            [app_id]
            + [
                ("set" if env in entered else "missing") if found else "not found"
                for env in ("draft", "live")
            ]
        )
    _table(["Connection", "Draft credentials", "Live credentials"], rows)


def list_tools() -> dict[str, str]:
    _section("Tools")
    names_by_id = {t["id"]: t["name"] for t in _orchestrate_json("tools", "list")}
    saved = set(names_by_id.values())
    rows = [
        [name, demo, "saved" if name in saved else missing]
        for demo, expected, missing in (
            ("Demo Two, customer", TOOLS, "missing"),
            ("Demo One, staff", STAFF_TOOLS, "missing"),
            ("Optional, referral", REFERRAL_TOOLS, "not imported"),
        )
        for name in expected
    ]
    _table(["Tool", "Used by", "Status"], rows)
    return names_by_id


def list_knowledge_base() -> dict[str, str]:
    _section("Knowledge base")
    kb_id = next(
        (
            kb["id"]
            for kb in _orchestrate_json("knowledge-bases", "list")
            if kb["name"] == KNOWLEDGE_BASE
        ),
        None,
    )
    if kb_id is None:
        _table(["Knowledge base", "Index status"], [[KNOWLEDGE_BASE, "not found"]])
        return {}
    status = _orchestrate_json("knowledge-bases", "status", "-n", KNOWLEDGE_BASE)
    _table(
        ["Knowledge base", "Index status"],
        [[KNOWLEDGE_BASE, str(status.get("built_in_index_status"))]],
    )
    return {kb_id: KNOWLEDGE_BASE}


def list_agents(tool_names: dict[str, str], kb_names: dict[str, str]) -> None:
    _section("Agents")
    agents: list[dict[str, Any]] = _orchestrate_json("agents", "list")["native"]
    names_by_id = {a["id"]: a["name"] for a in agents}
    by_name = {a["name"]: a for a in agents}
    rows = []
    for name in [*AGENTS, *STAFF_AGENTS]:
        agent = by_name.get(name)
        if agent is None:
            rows.append([name, "not found", "", "", ""])
            continue
        rows.append(
            [name, agent["llm"]]
            + [
                "\n".join(lookup.get(i, i) for i in agent[key])
                for key, lookup in (
                    ("tools", tool_names),
                    ("collaborators", names_by_id),
                    ("knowledge_base", kb_names),
                )
            ]
        )
    _table(["Agent", "Model", "Tools", "Collaborators", "Knowledge base"], rows)


def main() -> None:
    print(f"Environment: {_active_environment()}")
    list_connections()
    tool_names = list_tools()
    kb_names = list_knowledge_base()
    list_agents(tool_names, kb_names)


if __name__ == "__main__":
    main()
