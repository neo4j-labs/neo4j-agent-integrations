"""Run the finance LangGraph agent on this machine, outside Orchestrate.

Usage:
    uv run --with langchain-mcp-adapters python mcp-setup/run_local.py "question"

It builds the same credentials dict that Orchestrate injects, from
.mcp-credentials.finance.json and the OPENAI_API_KEY in .env.
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "finance-agent"))

from agent import LLM_KEY, TOKEN_KEY, TOKEN_TYPE_KEY, URL_KEY, create_agent


def fetch_token(creds: dict) -> str:
    """Get a Cognito access token, as Orchestrate does for the connection."""
    basic = base64.b64encode(f"{creds['client_id']}:{creds['client_secret']}".encode())
    form = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": creds["scope"]}
    ).encode()
    request = urllib.request.Request(
        creds["token_url"],
        data=form,
        headers={"Authorization": f"Basic {basic.decode()}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)["access_token"]


def build_config() -> dict:
    load_dotenv(ROOT / ".env")
    creds = json.loads((ROOT / ".mcp-credentials.finance.json").read_text())
    return {
        "configurable": {
            "credentials": {
                LLM_KEY: os.environ["OPENAI_API_KEY"],
                TOKEN_KEY: fetch_token(creds),
                TOKEN_TYPE_KEY: "Bearer",
                URL_KEY: creds["gateway_url"],
            }
        }
    }


async def main(question: str) -> None:
    config = build_config()
    graph = create_agent(config).compile()
    result = await graph.ainvoke({"messages": [HumanMessage(content=question)]}, config)
    print(result["messages"][-1].content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    asyncio.run(main(parser.parse_args().question))
