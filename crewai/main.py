#!/usr/bin/env python3
"""
CLI entry point for CrewAI + Neo4j Agent Integrations.

Runs the multi-agent crew to perform graph research, network analysis,
and executive synthesis for a given company.
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from agent.crew import build_company_intelligence_crew


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run CrewAI Multi-Agent Intelligence Crew against Neo4j Knowledge Graph."
    )
    parser.add_argument(
        "--company",
        type=str,
        default="Google",
        help="Company name to research (default: Google)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional file path to save the generated markdown briefing report.",
    )
    parser.add_argument(
        "--crew-id",
        type=str,
        default=None,
        help="Optional unique session/crew ID for NAMS memory tracking.",
    )

    args = parser.parse_args()

    print(f"============================================================")
    print(f"🚀 Initializing CrewAI Multi-Agent Team for: '{args.company}'")
    print(f"   Neo4j URI: {os.environ.get('NEO4J_URI', 'demo.neo4jlabs.com')}")
    print(f"   Memory (NAMS): {'Enabled' if os.environ.get('MEMORY_API_KEY') else 'Disabled/Local'}")
    print(f"   MCP Server: {os.environ.get('MCP_SERVER_URL', 'None')}")
    print(f"============================================================\n")

    crew = build_company_intelligence_crew(
        company_name=args.company,
        output_file=args.output,
        crew_id=args.crew_id,
    )

    print("🤖 Executing multi-agent workflow...")
    result = crew.kickoff()

    print("\n============================================================")
    print("✨ Executive Intelligence Briefing Completed!")
    print("============================================================\n")
    print(result)

    if args.output:
        print(f"\n📄 Report saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
