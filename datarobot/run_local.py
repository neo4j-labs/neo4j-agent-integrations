from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from agent.custom import chat


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DataRobot Neo4j agent locally.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Give me a competitive snapshot of Google including recent news and relationships.",
        help="User prompt to send to the agent.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full OpenAI-compatible response envelope instead of assistant text only.",
    )
    args = parser.parse_args()

    request = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": args.prompt,
            }
        ],
    }
    response = chat(request, model=request["model"])
    if args.json:
        print(json.dumps(response, indent=2))
    else:
        print(response["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
