#!/usr/bin/env python3
import argparse
import os
import sys
from google import genai

# Pull platform routing variables directly from the active runtime environment
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "gcp-neo4j-agent-integr-14f4")
LOCATION = os.environ.get("GCP_LOCATION", "global")
AGENT_ID = f"projects/{PROJECT_ID}/locations/{LOCATION}/agents/neo4j-managed-agent"

def parse_args():
    parser = argparse.ArgumentParser(description="Interactive test client for the Neo4j Managed Agent Platform.")
    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        default="How many nodes are currently in our database?",
        help="The natural language prompt to send to the graph agent."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print full server-sent event (SSE) stream objects, including internal tool execution logs."
    )
    return parser.parse_args()

def main():
    args = parse_args()

    print("======================================================================")
    print(f"Initializing Gemini Enterprise Client [Project: {PROJECT_ID}]")
    print("======================================================================")

    try:
        client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION,
        )

        print(f"Sending interaction request to: {AGENT_ID}\n")
        if not args.verbose:
            print("--- Assistant Response ---")

        stream = client.interactions.create(
            agent=AGENT_ID,
            input=args.query,
            stream=True,
            background=True,
            store=True,
        )

        for event in stream:
            if args.verbose:
                print(event)
            else:
                event_type = getattr(event, "event_type", None) or event.get("event_type")

                if event_type == "step.delta":
                    delta = getattr(event, "delta", None) or event.get("delta", {})
                    delta_type = getattr(delta, "type", None) or delta.get("type")

                    if delta_type == "text":
                        text_chunk = getattr(delta, "text", "") or delta.get("text", "")
                        print(text_chunk, end="", flush=True)

        print("\n--------------------------")
        print("\nInteraction stream finalized successfully.")

    except Exception as e:
        print(f"\n[ERROR] Failed to execute interaction loop: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()