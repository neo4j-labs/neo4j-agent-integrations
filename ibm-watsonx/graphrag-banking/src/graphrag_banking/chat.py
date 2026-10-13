"""Interactive chat with the support agent, as the demo customer.

After each answer it prints a trace: the tools called, the Cypher they ran, and
the policy chunks retrieved. This is the proof beat for Phases 1 to 3.
"""

import json
import textwrap

from graphrag_banking.agent import SupportAgent, ToolCall
from graphrag_banking.config import get_driver, load_settings

_RESULT_PREVIEW_CHARS = 600


def _indent(text: str, prefix: str = "      ") -> str:
    return textwrap.indent(text, prefix)


def _format_chunks(result: dict) -> str:
    lines = []
    for passage in result.get("passages", []):
        heading = passage["text"].splitlines()[0]
        codes = ", ".join(rule["rule_code"] for rule in passage["rules"]) or "none"
        lines.append(
            f"{passage['score']:.4f}  {passage['policy']}: {heading}  [rules: {codes}]"
        )
    return "\n".join(lines) or "(no chunks)"


def _format_call(number: int, call: ToolCall) -> str:
    args = ", ".join(f"{name}={value!r}" for name, value in call["args"].items())
    parts = [f"  {number}. {call['name']}({args})"]
    for query in call["cypher"]:
        parts.append("     Cypher:")
        parts.append(_indent(query))
    if call["name"] == "search_policies" and "passages" in call["result"]:
        parts.append("     Chunks:")
        parts.append(_indent(_format_chunks(call["result"])))
    else:
        preview = json.dumps(call["result"], ensure_ascii=False)
        if len(preview) > _RESULT_PREVIEW_CHARS:
            preview = preview[:_RESULT_PREVIEW_CHARS] + " ..."
        parts.append("     Result:")
        parts.append(_indent(preview))
    return "\n".join(parts)


def main() -> None:
    settings = load_settings()
    print(f"Signed in as {settings.demo_customer_id}. Today is {settings.demo_as_of}.")
    print("Type a question, or press Ctrl-D to quit.\n")
    with get_driver(settings) as driver:
        agent = SupportAgent(settings, driver)
        while True:
            try:
                prompt = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not prompt:
                continue
            result = agent.ask(prompt)
            print(f"\nagent> {result['answer']}\n")
            print(f"Trace: {len(result['tool_calls'])} tool calls")
            for number, call in enumerate(result["tool_calls"], start=1):
                print(_format_call(number, call))
            print()
