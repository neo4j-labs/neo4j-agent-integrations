#!/usr/bin/env python3
import argparse, os, sys
from google import genai
from dotenv import load_dotenv
load_dotenv() 
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-gcp-project-id")
LOCATION = os.environ.get("GCP_LOCATION", "global")
AGENT_NAME = os.environ.get("AGENT_NAME", "neo4j-managed-agent")
AGENT_ID = f"projects/{PROJECT_ID}/locations/{LOCATION}/agents/{AGENT_NAME}"



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="How many nodes are in the database?")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    print(f"→ {AGENT_ID}\n")

    stream = client.interactions.create(
        agent=AGENT_ID, input=args.query,
        stream=True, background=True, store=True,
    )
    for event in stream:
        if args.verbose:
            print(event); continue
        if getattr(event, "event_type", None) == "step.delta":
            delta = getattr(event, "delta", None) or {}
            if (getattr(delta, "type", None) or delta.get("type")) == "text":
                print(getattr(delta, "text", "") or delta.get("text", ""), end="", flush=True)
    print()



if __name__ == "__main__":
    main()