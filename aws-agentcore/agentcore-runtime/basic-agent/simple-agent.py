#!/usr/bin/env python3
"""
Simple Neo4j MCP Agent

A simplified ReAct agent that connects to the Neo4j MCP server via AgentCore Gateway.
Uses .mcp-credentials.json for authentication (no automatic token refresh).

Usage:
    python simple-agent.py                    # Run demo queries
    python simple-agent.py "your question"    # Ask a specific question
"""

import asyncio
import json
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient


CREDENTIALS_FILE = ".mcp-credentials.json"
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

SYSTEM_PROMPT = """You are a helpful Neo4j database assistant with access to tools that let you query a Neo4j graph database.

Your capabilities include:
- Retrieve the database schema to understand node labels, relationship types, and properties
- Execute read-only Cypher queries to answer questions about the data
- Do not execute any write Cypher queries

When answering questions about the database:
1. First retrieve the schema to understand the database structure
2. Formulate appropriate Cypher queries based on the actual schema
3. If a query returns no results, explain what you looked for and suggest alternatives
4. Format results in a clear, human-readable way
5. Cite the actual data returned in your response

Important Cypher notes:
- Use MATCH patterns that align with the actual schema
- For counting, use MATCH (n:Label) RETURN count(n)
- For listing items, add LIMIT to avoid overwhelming results
- Handle potential NULL values gracefully

Be concise but thorough in your responses."""

DEMO_QUESTIONS = [
    ("Database Schema Overview", "What is the database schema? Give me a brief summary."),
    ("Count of Aircraft", "How many Aircraft are in the database?"),
    ("List Airports", "List 5 airports with their city and country."),
    ("Recent Maintenance Events", "Show me 3 recent maintenance events with their severity."),
    ("Flight Statistics", "How many flights are in the database and what operators fly them?"),
]


def load_credentials() -> dict:
    """Load credentials from .mcp-credentials.json."""
    if not Path(CREDENTIALS_FILE).exists():
        print("ERROR: Credentials file not found: .mcp-credentials.json")
        print()
        print("Run './deploy.sh credentials' to generate it")
        sys.exit(1)

    with open(CREDENTIALS_FILE) as f:
        return json.load(f)


def get_llm(region: str = "us-west-2"):
    """Get the LLM to use for the agent (AWS Bedrock Claude via Converse API)."""
    return init_chat_model(
        MODEL_ID,
        model_provider="bedrock_converse",
        region_name=region,
        temperature=0,
    )


async def run_agent(question: str):
    """Run the LangGraph agent with the given question."""
    print("=" * 70)
    print("Neo4j MCP Agent (Simple)")
    print("=" * 70)
    print()

    # Load credentials
    credentials = load_credentials()
    gateway_url = credentials["gateway_url"]
    access_token = credentials["access_token"]
    region = credentials.get("region", "us-west-2")

    print(f"Gateway: {gateway_url}")
    print()

    # Initialize LLM
    print(f"Initializing LLM (Bedrock, region: {region})...")
    llm = get_llm(region)
    print(f"Using: {MODEL_ID}")
    print()

    # Connect to MCP server
    print("Connecting to MCP server...")

    client = MultiServerMCPClient(
        {
            "neo4j": {
                "transport": "streamable_http",
                "url": gateway_url,
                "headers": {
                    "Authorization": f"Bearer {access_token}",
                },
            }
        }
    )

    # Get available tools
    tools = await client.get_tools()
    print(f"Loaded {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool.name}")
    print()

    # Create the ReAct agent
    print("Creating agent...")
    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

    # Run the agent
    print("=" * 70)
    print(f"Question: {question}")
    print("=" * 70)
    print()

    result = await agent.ainvoke({"messages": [("human", question)]})

    # Extract and print the final response
    messages = result.get("messages", [])
    if messages:
        final_message = messages[-1]
        if hasattr(final_message, "content"):
            print("Answer:")
            print("-" * 70)
            print(final_message.content)
            print("-" * 70)
        else:
            print("Answer:", final_message)
    else:
        print("No response from agent")


async def run_demo():
    """Run demo queries to showcase the agent capabilities."""
    print()
    print("#" * 76)
    print("#" + "NEO4J MCP AGENT DEMO (Simple)".center(74) + "#")
    print("#" * 76)
    print()

    for i, (title, question) in enumerate(DEMO_QUESTIONS, 1):
        print()
        print("=" * 76)
        print(f"  QUERY {i}: {title}")
        print("=" * 76)
        print()
        await run_agent(question)
        print()

    print()
    print("#" * 76)
    print("#" + "DEMO COMPLETE".center(74) + "#")
    print("#" * 76)


def main():
    if len(sys.argv) < 2:
        asyncio.run(run_demo())
    else:
        question = " ".join(sys.argv[1:])
        asyncio.run(run_agent(question))


if __name__ == "__main__":
    main()
