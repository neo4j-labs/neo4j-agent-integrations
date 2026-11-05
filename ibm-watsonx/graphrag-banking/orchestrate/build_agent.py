"""Write the banking_support agent YAML for watsonx Orchestrate.

The instructions come from prompts/agent_instructions.md, the same file the
local agent uses, with the demo date filled in. Orchestrate has no template
variables, so the date is written into the YAML literally.

Usage: uv run python orchestrate/build_agent.py
Then:  orchestrate agents import -f orchestrate/build/banking_support.yaml
"""

import os
from pathlib import Path

import yaml

from graphrag_banking.agent import load_instructions
from graphrag_banking.config import load_settings

OUTPUT = Path(__file__).parent / "build" / "banking_support.yaml"
DEFAULT_MODEL = "bedrock/openai.gpt-oss-120b-1:0"
TOOLS = [
    "search_policies",
    "get_my_accounts",
    "find_my_transactions",
    "explain_transaction",
    "get_my_household",
    "get_scheduled_payments",
]


class _Literal(str):
    """A string written as a YAML block, so the instructions stay readable."""


yaml.add_representer(
    _Literal, lambda dumper, data: dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
)


def main() -> None:
    settings = load_settings()
    agent = {
        "spec_version": "v1",
        "kind": "native",
        "name": "banking_support",
        "description": (
            "Answers a signed-in bank customer's questions about their own accounts, "
            "transactions, and the bank's fee, hold, and compliance policies, using a "
            "Neo4j knowledge graph."
        ),
        "llm": os.environ.get("ORCHESTRATE_MODEL", DEFAULT_MODEL),
        "style": "default",
        "instructions": _Literal(load_instructions(settings.demo_as_of)),
        "tools": TOOLS,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(yaml.dump(agent, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()