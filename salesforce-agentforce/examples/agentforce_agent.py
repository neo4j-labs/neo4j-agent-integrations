"""
agentforce_agent.py — Industry Research Agent via Salesforce AgentForce API

PURPOSE
-------
Demonstrates how to drive an AgentForce agent from Python using the Agent API.
Implements the Industry Research Agent reference pattern for:
  - Company profile lookup (from Neo4j via AgentForce actions)
  - Industry exploration
  - News and relationship research
  - Multi-turn research conversations

PREREQUISITES
-------------
1. Salesforce org with AgentForce enabled
2. Connected App configured for OAuth 2.0 Client Credentials flow
3. AgentForce agent deployed with Neo4j actions (via External Service or MCP)
4. Python SDK: pip install salesforce-agentforce

OR use raw REST (no SDK dependency):
  pip install requests sseclient-py

ENVIRONMENT VARIABLES
---------------------
  SF_INSTANCE_URL     https://your-org.my.salesforce.com
  SF_CLIENT_ID        Connected App consumer key
  SF_CLIENT_SECRET    Connected App consumer secret
  SF_AGENT_ID         AgentForce agent ID (0Xxxx... or API name)

AGENT API ENDPOINT
------------------
  POST /einstein/ai-agent/v1/sessions          ← create session
  POST /einstein/ai-agent/v1/sessions/{id}/messages  ← send message
  DELETE /einstein/ai-agent/v1/sessions/{id}   ← end session

Note: Newer docs reference /services/data/v62.0/einstein/ai-agent/v1/
      Check your org's API version. Both paths may work.
"""

import os
import uuid
import json
import time
from typing import Optional

import requests

try:
    # Official Python SDK (pip install salesforce-agentforce)
    from agentforce.agents import Agentforce as AgentforceSDK
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SF_INSTANCE_URL = os.environ.get("SF_INSTANCE_URL", "https://your-org.my.salesforce.com")
SF_CLIENT_ID = os.environ.get("SF_CLIENT_ID", "")
SF_CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET", "")
SF_AGENT_ID = os.environ.get("SF_AGENT_ID", "")

AGENT_API_BASE = f"{SF_INSTANCE_URL}/einstein/ai-agent/v1"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_access_token() -> tuple[str, str]:
    """
    Get Salesforce access token via OAuth 2.0 Client Credentials flow.

    Returns:
        (access_token, instance_url)
    """
    response = requests.post(
        f"{SF_INSTANCE_URL}/services/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": SF_CLIENT_ID,
            "client_secret": SF_CLIENT_SECRET,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["access_token"], data.get("instance_url", SF_INSTANCE_URL)


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------

class AgentForceSession:
    """
    Manages an AgentForce session lifecycle.

    Usage:
        with AgentForceSession(token, instance_url, agent_id) as session:
            response = session.send_message("Research Apple Inc")
            print(response)
    """

    def __init__(self, token: str, instance_url: str, agent_id: str,
                 variables: Optional[list] = None):
        self.token = token
        self.instance_url = instance_url
        self.agent_id = agent_id
        self.variables = variables or []
        self.session_id = None
        self.sequence_id = 0
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.base_url = f"{instance_url}/einstein/ai-agent/v1"

    def __enter__(self):
        self._create_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._end_session()

    def _create_session(self):
        """Start an AgentForce session."""
        payload = {
            "externalSessionKey": str(uuid.uuid4()),
            "instanceConfig": {"endpoint": self.instance_url},
        }
        if self.variables:
            payload["variables"] = self.variables

        response = requests.post(
            f"{self.base_url}/sessions",
            headers=self.headers,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        self.session_id = data["sessionId"]
        print(f"Session created: {self.session_id}")

    def _end_session(self):
        """End the AgentForce session."""
        if not self.session_id:
            return
        try:
            requests.delete(
                f"{self.base_url}/sessions/{self.session_id}",
                headers=self.headers,
                timeout=10,
            )
            print(f"Session ended: {self.session_id}")
        except Exception as e:
            print(f"Warning: Failed to end session: {e}")

    def send_message(self, text: str, timeout: int = 120) -> dict:
        """
        Send a message to the agent and return the response.

        Args:
            text: User message text
            timeout: Request timeout in seconds

        Returns:
            {
                'text': str,           # Agent's text response
                'actions_taken': list, # Actions the agent executed
                'raw': dict            # Full response payload
            }
        """
        self.sequence_id += 1
        payload = {
            "message": {
                "sequenceId": self.sequence_id,
                "type": "Text",
                "text": text,
            }
        }

        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/messages",
            headers=self.headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        # Parse response messages
        text_response = ""
        actions_taken = []

        for msg in data.get("messages", []):
            msg_type = msg.get("type", "")
            if msg_type == "Text":
                text_response = msg.get("message", msg.get("text", ""))
            elif msg_type == "AgentAction" or msg_type == "Inform":
                action_name = msg.get("actionName", msg.get("message", ""))
                if action_name:
                    actions_taken.append({
                        "action": action_name,
                        "inputs": msg.get("inputs", {}),
                        "outputs": msg.get("outputs", {}),
                    })

        return {
            "text": text_response,
            "actions_taken": actions_taken,
            "session_state": data.get("sessionState", "UNKNOWN"),
            "raw": data,
        }

    def send_message_streaming(self, text: str):
        """
        Send a message with Server-Sent Events streaming.
        Yields text chunks as they arrive.

        Requires: pip install sseclient-py
        """
        try:
            import sseclient
        except ImportError:
            raise ImportError("pip install sseclient-py required for streaming")

        self.sequence_id += 1
        payload = {
            "message": {
                "sequenceId": self.sequence_id,
                "type": "Text",
                "text": text,
            }
        }

        response = requests.post(
            f"{self.base_url}/sessions/{self.session_id}/messages/stream",
            headers={**self.headers, "Accept": "text/event-stream"},
            json=payload,
            stream=True,
            timeout=180,
        )
        response.raise_for_status()

        for event in sseclient.SSEClient(response):
            if event.data and event.data != "[DONE]":
                try:
                    chunk = json.loads(event.data)
                    if chunk.get("type") == "chunk":
                        yield chunk.get("text", "")
                except json.JSONDecodeError:
                    pass


# ---------------------------------------------------------------------------
# SDK-based Client (if salesforce-agentforce is installed)
# ---------------------------------------------------------------------------

class AgentForceSDKClient:
    """
    Uses the official salesforce-agentforce Python SDK.
    pip install salesforce-agentforce
    """

    def __init__(self):
        if not SDK_AVAILABLE:
            raise ImportError("pip install salesforce-agentforce")
        self.client = AgentforceSDK()
        self.client.authenticate(
            salesforce_org=SF_INSTANCE_URL,
            client_id=SF_CLIENT_ID,
            client_secret=SF_CLIENT_SECRET,
        )
        self.session = None

    def start_session(self, agent_id: str):
        self.session = self.client.start_session(agent_id=agent_id)
        return self.session.sessionId

    def chat(self, message: str) -> str:
        self.client.add_message_text(message)
        response = self.client.send_message(session_id=self.session.sessionId)
        return response

    def end_session(self):
        if self.session:
            self.client.end_session(session_id=self.session.sessionId)


# ---------------------------------------------------------------------------
# Industry Research Agent — Reference Implementation
# ---------------------------------------------------------------------------

def run_industry_research_agent(company_name: str, verbose: bool = True) -> dict:
    """
    Run the Industry Research Agent for a specific company.

    This demonstrates the full research workflow using AgentForce:
    1. Research company profile (neo4j tool via agent action)
    2. Search for recent news
    3. Analyze industry position
    4. Generate research report

    Args:
        company_name: Company to research (e.g., "Apple", "Tesla")
        verbose: Print conversation to stdout

    Returns:
        {
            'company': str,
            'research_steps': list,
            'final_report': str,
            'actions_executed': list
        }
    """
    token, instance_url = get_access_token()

    research_steps = []
    all_actions = []

    with AgentForceSession(token, instance_url, SF_AGENT_ID) as session:

        # Step 1: Company profile
        step1_prompt = (
            f"Research {company_name}: get the company profile including "
            f"industry, location, leadership, and company ID from the knowledge graph."
        )
        if verbose:
            print(f"\n[STEP 1] {step1_prompt}\n")

        response1 = session.send_message(step1_prompt)
        research_steps.append({
            "step": "company_profile",
            "prompt": step1_prompt,
            "response": response1["text"],
            "actions": response1["actions_taken"],
        })
        all_actions.extend(response1["actions_taken"])

        if verbose:
            print(f"Agent: {response1['text']}\n")
            for action in response1["actions_taken"]:
                print(f"  [ACTION] {action['action']}")

        # Step 2: Recent news
        step2_prompt = (
            f"Search for recent news about {company_name} — "
            f"focus on strategic developments, partnerships, and market moves."
        )
        if verbose:
            print(f"\n[STEP 2] {step2_prompt}\n")

        response2 = session.send_message(step2_prompt)
        research_steps.append({
            "step": "news_research",
            "prompt": step2_prompt,
            "response": response2["text"],
            "actions": response2["actions_taken"],
        })
        all_actions.extend(response2["actions_taken"])

        if verbose:
            print(f"Agent: {response2['text']}\n")

        # Step 3: Industry and relationships
        step3_prompt = (
            f"Analyze {company_name}'s industry position and organizational "
            f"relationships. Who are they connected to in the knowledge graph?"
        )
        if verbose:
            print(f"\n[STEP 3] {step3_prompt}\n")

        response3 = session.send_message(step3_prompt)
        research_steps.append({
            "step": "industry_analysis",
            "prompt": step3_prompt,
            "response": response3["text"],
            "actions": response3["actions_taken"],
        })
        all_actions.extend(response3["actions_taken"])

        if verbose:
            print(f"Agent: {response3['text']}\n")

        # Step 4: Synthesis
        step4_prompt = (
            f"Based on everything you've found, generate a concise investment "
            f"research report for {company_name}. Include: executive summary, "
            f"industry position, recent developments, key relationships, and outlook."
        )
        if verbose:
            print(f"\n[STEP 4] Synthesizing report...\n")

        response4 = session.send_message(step4_prompt)
        research_steps.append({
            "step": "synthesis",
            "prompt": step4_prompt,
            "response": response4["text"],
            "actions": response4["actions_taken"],
        })

        if verbose:
            print(f"\n{'='*60}")
            print(f"RESEARCH REPORT: {company_name}")
            print('='*60)
            print(response4["text"])
            print('='*60)

    return {
        "company": company_name,
        "research_steps": research_steps,
        "final_report": response4["text"],
        "actions_executed": all_actions,
        "total_actions": len(all_actions),
    }


# ---------------------------------------------------------------------------
# Interactive Research Chat
# ---------------------------------------------------------------------------

def interactive_research_chat():
    """
    Start an interactive multi-turn research conversation with the agent.
    Type 'exit' to end the session.
    """
    token, instance_url = get_access_token()

    print("\nSalesforce AgentForce — Industry Research Agent")
    print("Powered by Neo4j Company News Knowledge Graph")
    print("Type 'exit' to end the session\n")

    with AgentForceSession(token, instance_url, SF_AGENT_ID) as session:
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Agent: Goodbye! Session ending.")
                break
            if not user_input:
                continue

            print("Agent: ", end="", flush=True)
            response = session.send_message(user_input)
            print(response["text"])

            if response["actions_taken"]:
                print(f"\n  [Actions executed: {len(response['actions_taken'])}]", end="")
                for action in response["actions_taken"]:
                    print(f"\n    → {action['action']}", end="")
            print("\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        company = " ".join(sys.argv[1:])
        print(f"\nResearching: {company}")
        result = run_industry_research_agent(company, verbose=True)
        print(f"\nTotal AgentForce actions executed: {result['total_actions']}")
    else:
        # Interactive mode
        interactive_research_chat()
