#!/usr/bin/env python3
"""
Vertex AI Memory Bank client — runs inside the managed-agent sandbox via code_execution.
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

PROJECT_ID = "__PROJECT_ID__"
LOCATION = "__MEMORY_BANK_LOCATION__"
MEMORY_BANK_ID = "__MEMORY_BANK_ID__"

METADATA_TOKEN_URL = (
    "http://169.254.169.254/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)



def _metadata_token():
    """Fetch the sandbox identity's OAuth token via the metadata server IP."""
    req = urllib.request.Request(
        METADATA_TOKEN_URL,
        headers={"Metadata-Flavor": "Google"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())["access_token"]



class MemoryBankClient:
    def __init__(self, project_id, location, memory_bank_id):
        if not memory_bank_id or memory_bank_id.startswith("__"):
            raise ValueError("memory_bank_id is not configured (deploy templating failed)")
        self.base_url = (
            f"https://aiplatform.googleapis.com/v1beta1/"
            f"projects/{project_id}/locations/{location}"
            f"/reasoningEngines/{memory_bank_id}"
        )

    def add_memory(self, user_id, fact):
        res = self._send(f"{self.base_url}/memories",
                         {"fact": fact, "scope": {"user_id": user_id}})
        if res.get("status") == "success":
            res["operation"] = res["data"].get("name")
        return res

    def get_memories(self, user_id, query=None, top_k=5):
        payload = {"scope": {"user_id": user_id}}
        if query:
            payload["similaritySearchParams"] = {"searchQuery": query, "topK": top_k}
        else:
            payload["simpleRetrievalParams"] = {"pageSize": top_k}
        res = self._send(f"{self.base_url}/memories:retrieve", payload)
        if res.get("status") == "success":
            facts = [m.get("memory", {}).get("fact")
                     for m in res["data"].get("retrievedMemories", [])]
            res["facts"] = [f for f in facts if f]
        return res

    def _send(self, url, payload):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_metadata_token()}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as r:
                return {"status": "success", "http": r.status,
                        "data": json.loads(r.read().decode("utf-8"))}
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode("utf-8"))
            except Exception:
                detail = str(e)
            return {"status": "error", "http": e.code, "message": detail}
        except Exception as e:
            return {"status": "error", "message": str(e)}



if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--action", choices=["add_memory", "get_memories"], required=True)
    p.add_argument("--user_id", required=True)
    p.add_argument("--fact")
    p.add_argument("--query")
    args = p.parse_args()

    client = MemoryBankClient(PROJECT_ID, LOCATION, MEMORY_BANK_ID)

    if args.action == "add_memory":
        if not args.fact:
            sys.exit(json.dumps({"status": "error", "message": "--fact is required"}))
        out = client.add_memory(args.user_id, args.fact)
    else:
        out = client.get_memories(args.user_id, args.query)

    print(json.dumps(out))