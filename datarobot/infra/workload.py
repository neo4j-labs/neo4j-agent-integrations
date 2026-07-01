"""Deploy the Neo4j research agent as a DataRobot Workload API service (Path C).

This is the deployment mechanism DataRobot recommends going forward — Custom
Model / DRUM (Path A, ``infra/agent.py``) remains supported but is being
phased out. The Workload API is plain REST (no Python SDK support yet); this
script calls it directly via ``httpx``, following the pattern documented in
DataRobot's ``datarobot-workload-api`` skill and
https://docs.datarobot.com/en/docs/api/dev-learning/workload-api/overview.html

Prerequisites:
  * DATAROBOT_ENDPOINT (must end in /api/v2) and DATAROBOT_API_TOKEN set.
  * A container image built for linux/amd64 and pushed to a registry
    DataRobot can pull from (see ../Dockerfile). Pass its URI via
    --image or the WORKLOAD_IMAGE_URI env var.
  * Runtime secrets (OPENAI_API_KEY, NEO4J_PASSWORD, MEMORY_API_KEY, ...)
    should be injected as DataRobot credentials (see --credential) rather
    than plaintext env vars where possible; plaintext env vars are used
    as a fallback for local/demo convenience.

Usage:
    python infra/workload.py create --image ghcr.io/org/neo4j-datarobot-agent:latest
    python infra/workload.py status <workload_id>
    python infra/workload.py logs <workload_id>
    python infra/workload.py delete <workload_id>
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:  # type: ignore[misc]
        return False

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_NAME = os.environ.get("DR_WORKLOAD_NAME", "neo4j-datarobot-agent")

# Env vars forwarded verbatim into the workload's container as plaintext.
# Prefer DataRobot credentials (--credential NAME=CRED_ID:KEY) for secrets;
# these are only a fallback for quick local/demo deployments.
PLAINTEXT_ENV_VARS = (
    "OPENAI_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_DATABASE",
    "AGENT_MAX_TOOL_STEPS",
    "MEMORY_WORKSPACE_ID",
    "MCP_SERVER_URL",
)
# Secrets: forwarded as plaintext ONLY if no --credential mapping is given
# for them. Strongly prefer wiring these through DataRobot credentials.
SECRET_ENV_VARS = (
    "OPENAI_API_KEY",
    "NEO4J_PASSWORD",
    "MEMORY_API_KEY",
    "MCP_AUTH_TOKEN",
)


def _client() -> "httpx.Client":
    if httpx is None:
        print("ERROR: httpx is required. Install with: pip install httpx", file=sys.stderr)
        sys.exit(1)
    endpoint = os.environ.get("DATAROBOT_ENDPOINT", "").rstrip("/")
    token = os.environ.get("DATAROBOT_API_TOKEN", "")
    if not endpoint or not token:
        print("ERROR: DATAROBOT_ENDPOINT and DATAROBOT_API_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)
    return httpx.Client(
        base_url=endpoint,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )


def _build_spec(image_uri: str, credentials: dict[str, str]) -> dict[str, Any]:
    """Build the Workload API create-workload request body.

    ``credentials`` maps env var name -> "drCredentialId:key" (see --credential).
    Any secret without a credential mapping falls back to a plaintext env var
    read from the local environment (demo convenience, not for production).
    """
    env_vars: list[dict[str, Any]] = []
    for name in PLAINTEXT_ENV_VARS:
        value = os.environ.get(name)
        if value:
            env_vars.append({"name": name, "value": value})

    for name in SECRET_ENV_VARS:
        if name in credentials:
            cred_id, key = credentials[name].split(":", 1)
            env_vars.append({
                "source": "dr-credential",
                "name": name,
                "drCredentialId": cred_id,
                "key": key,
            })
        else:
            value = os.environ.get(name)
            if value:
                print(f"  WARNING: {name} injected as plaintext (no --credential given)")
                env_vars.append({"name": name, "value": value})

    return {
        "name": WORKLOAD_NAME,
        "importance": "low",
        "artifact": {
            "name": f"{WORKLOAD_NAME}-artifact",
            "spec": {
                "type": "service",
                "containerGroups": [
                    {
                        "name": "default",
                        "containers": [
                            {
                                "name": "main",
                                "imageUri": image_uri,
                                "port": 8080,
                                "primary": True,
                                "readinessProbe": {
                                    "path": "/readyz", "port": 8080, "initialDelaySeconds": 10,
                                },
                                "livenessProbe": {
                                    "path": "/healthz", "port": 8080, "initialDelaySeconds": 30,
                                },
                                "environmentVars": env_vars,
                            }
                        ],
                    }
                ],
            },
        },
        "runtime": {
            "containerGroups": [
                {
                    "name": "default",
                    "replicaCount": 1,
                    "containers": [
                        {"name": "main", "resourceAllocation": {"cpu": 1, "memory": "512MB"}}
                    ],
                }
            ]
        },
    }


def create_workload(image_uri: str, credentials: dict[str, str], wait: bool = True) -> str:
    spec = _build_spec(image_uri, credentials)
    with _client() as client:
        resp = client.post("/api/v2/workloads/", json=spec)
        resp.raise_for_status()
        workload_id = resp.json()["id"]
        print(f"Created workload: {workload_id}")

        if wait:
            wait_for_running(workload_id)

        endpoint_resp = client.get(f"/api/v2/workloads/{workload_id}/")
        endpoint_resp.raise_for_status()
        data = endpoint_resp.json()
        print("\n" + "=" * 60)
        print("Workload deployed!")
        print(f"  Workload ID: {workload_id}")
        print(f"  Status:      {data.get('status')}")
        print(f"  Console:     https://app.datarobot.com/console-nextgen/workloads/{workload_id}/overview")
        print("=" * 60)
        return workload_id


def wait_for_running(workload_id: str, interval: int = 5, max_wait: int = 600) -> dict[str, Any]:
    waited = 0
    with _client() as client:
        while waited < max_wait:
            resp = client.get(f"/api/v2/workloads/{workload_id}/")
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "").lower()
            if status == "running":
                return data
            if status in {"errored", "failed", "terminated"}:
                raise RuntimeError(f"Workload {workload_id} entered terminal state '{status}': {data}")
            print(f"  ... status={status}, waiting {interval}s")
            time.sleep(interval)
            waited += interval
    raise TimeoutError(f"Timed out waiting for workload {workload_id} to reach 'running'")


def workload_status(workload_id: str) -> None:
    with _client() as client:
        resp = client.get(f"/api/v2/workloads/{workload_id}/")
        resp.raise_for_status()
        print(resp.json())


def workload_logs(workload_id: str, limit: int = 100) -> None:
    with _client() as client:
        resp = client.get(
            f"/api/v2/otel/workload/{workload_id}/logs/",
            params={"limit": limit},
        )
        resp.raise_for_status()
        for entry in resp.json().get("data", []):
            print(f"{entry.get('timestamp')} | {entry.get('level')} | {entry.get('message')}")


def delete_workload(workload_id: str) -> None:
    with _client() as client:
        resp = client.delete(f"/api/v2/workloads/{workload_id}/")
        resp.raise_for_status()
        print(f"Deleted workload: {workload_id}")


def _parse_credential(value: str) -> tuple[str, str]:
    """Parse '--credential NAME=CRED_ID:KEY' into (NAME, 'CRED_ID:KEY')."""
    name, mapping = value.split("=", 1)
    return name, mapping


def main() -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Deploy via DataRobot Workload API (Path C).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create and wait for the workload to run")
    p_create.add_argument("--image", required=True, help="linux/amd64 image URI (see ../Dockerfile)")
    p_create.add_argument(
        "--credential", action="append", default=[],
        metavar="NAME=CRED_ID:KEY",
        help="Inject a DataRobot credential as an env var, e.g. "
             "OPENAI_API_KEY=abc123:apiToken. Repeatable.",
    )
    p_create.add_argument("--no-wait", action="store_true", help="Don't block until running")

    p_status = sub.add_parser("status", help="Get workload status")
    p_status.add_argument("workload_id")

    p_logs = sub.add_parser("logs", help="Print recent logs")
    p_logs.add_argument("workload_id")

    p_delete = sub.add_parser("delete", help="Delete the workload")
    p_delete.add_argument("workload_id")

    args = parser.parse_args()

    try:
        if args.command == "create":
            credentials = dict(_parse_credential(c) for c in args.credential)
            create_workload(args.image, credentials, wait=not args.no_wait)
        elif args.command == "status":
            workload_status(args.workload_id)
        elif args.command == "logs":
            workload_logs(args.workload_id)
        elif args.command == "delete":
            delete_workload(args.workload_id)
        return 0
    except (RuntimeError, TimeoutError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
