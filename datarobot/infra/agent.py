from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import urllib.request
import urllib.error
import urllib.parse

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:  # type: ignore[misc]
        return False

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
DIST_DIR = ROOT / "dist"
PACKAGE_PATH = DIST_DIR / "neo4j_datarobot_agent.zip"

# Files packaged into the DataRobot custom model ZIP
AGENT_FILES = [
    "__init__.py",
    "agent.py",
    "custom.py",
    "helpers.py",
    "memory.py",
    "mcp_client.py",
    "model-metadata.yaml",
    "requirements.txt",
]

# DataRobot Python 3 drop-in environment name (agentic workflows use this)
DR_PYTHON3_ENV_NAME = "Python 3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_environment() -> None:
    load_dotenv(ROOT / ".env")


def _dr_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _dr_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
    timeout: int = 60,
) -> dict:
    """Make a JSON DataRobot API request and return the parsed response."""
    data = json.dumps(body).encode() if body else None
    headers = _dr_headers(token)
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body_text}") from exc


def _dr_upload_files(
    url: str,
    token: str,
    files: list[tuple[str, bytes, str]],
    timeout: int = 120,
) -> dict:
    """
    Multipart/form-data file upload to DataRobot.
    files: list of (field_name, file_bytes, filename)
    """
    boundary = "----DataRobotBoundary" + str(int(time.time()))
    parts = []
    for field_name, file_bytes, filename in files:
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n'.encode()
            + file_bytes
            + b'\r\n'
        )
    body = b"".join(parts) + f'--{boundary}--\r\n'.encode()
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {body_text}") from exc


def _poll(
    url: str,
    token: str,
    done_states: set[str],
    failed_states: set[str],
    status_key: str = "status",
    interval: int = 5,
    max_wait: int = 600,
) -> dict:
    """Poll a DataRobot async resource until it reaches a terminal state."""
    waited = 0
    while waited < max_wait:
        payload = _dr_request("GET", url, token)
        status = payload.get(status_key, "").lower()
        if status in done_states:
            return payload
        if status in failed_states:
            raise RuntimeError(f"DataRobot task failed (status={status}): {payload}")
        print(f"  ... {status_key}={status}, waiting {interval}s")
        time.sleep(interval)
        waited += interval
    raise TimeoutError(f"Timed out waiting for {url} after {max_wait}s")


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def package_agent() -> Path:
    """Build the ZIP archive for DataRobot upload."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with ZipFile(PACKAGE_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for name in AGENT_FILES:
            path = AGENT_DIR / name
            if path.exists():
                archive.write(path, arcname=name)
            else:
                print(f"  WARNING: {name} not found, skipping")
    print(f"Package created: {PACKAGE_PATH}")
    return PACKAGE_PATH


def _normalize_dr_endpoint(endpoint: str) -> str:
    """
    Return the DataRobot app base URL with no trailing slash and no
    trailing /api/v2, regardless of which form DATAROBOT_ENDPOINT was set
    to. DataRobot's own docs/SDKs are inconsistent about whether this env
    var should already include /api/v2 (e.g. https://app.datarobot.com vs.
    https://app.datarobot.com/api/v2), so callers that append /api/v2
    themselves (validate_datarobot_access, deploy_to_datarobot) would
    otherwise silently build a broken .../api/v2/api/v2/... URL if a user
    supplied the /api/v2 form.
    """
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/api/v2"):
        normalized = normalized[: -len("/api/v2")]
    return normalized


def validate_datarobot_access(timeout: int = 20) -> tuple[bool, str]:
    """Verify DATAROBOT_ENDPOINT + DATAROBOT_API_TOKEN work."""
    endpoint = os.environ.get("DATAROBOT_ENDPOINT")
    token = os.environ.get("DATAROBOT_API_TOKEN")
    if not endpoint or not token:
        return False, "DATAROBOT_ENDPOINT or DATAROBOT_API_TOKEN is missing."
    url = f"{_normalize_dr_endpoint(endpoint)}/api/v2/account/info/"
    try:
        payload = _dr_request("GET", url, token, timeout=timeout)
        username = payload.get("username") or payload.get("uid") or "unknown"
        return True, f"Authenticated as {username}."
    except RuntimeError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        return False, f"Connection error: {exc}"


def _find_execution_environment(base_url: str, token: str, name_fragment: str = "Python 3") -> str:
    """Return the ID of the first execution environment whose name contains name_fragment."""
    url = f"{base_url}/api/v2/executionEnvironments/?offset=0&limit=100"
    payload = _dr_request("GET", url, token)
    for env in payload.get("data", []):
        if name_fragment.lower() in env.get("name", "").lower():
            return env["id"]
    raise RuntimeError(
        f"Could not find an execution environment matching '{name_fragment}'. "
        "Check your DataRobot instance has a Python 3 drop-in environment."
    )


def deploy_to_datarobot(dry_run: bool = False) -> None:
    """
    Fully automated DataRobot deployment:

    1. Package agent files into ZIP
    2. Validate DR access
    3. Create custom model (target type: agenticworkflow)
    4. Create a custom model version and upload all agent files
    5. Wait for the version build to complete
    6. Register the model in the Model Registry
    7. Create a deployment from the registered model
    8. Print the deployment prediction URL
    """
    endpoint = os.environ.get("DATAROBOT_ENDPOINT", "")
    token = os.environ.get("DATAROBOT_API_TOKEN", "")
    model_name = os.environ.get("DR_MODEL_NAME", "Neo4j DataRobot Agent")

    if not endpoint or not token:
        print("ERROR: DATAROBOT_ENDPOINT and DATAROBOT_API_TOKEN must be set.")
        sys.exit(1)

    base = f"{_normalize_dr_endpoint(endpoint)}/api/v2"

    # ── 1. Package ────────────────────────────────────────────────────────
    print("\n[1/7] Packaging agent files...")
    zip_path = package_agent()

    # ── 2. Validate access ────────────────────────────────────────────────
    print("\n[2/7] Validating DataRobot access...")
    ok, msg = validate_datarobot_access()
    print(f"  {msg}")
    if not ok:
        sys.exit(1)

    if dry_run:
        print("\nDry-run mode: stopping before API calls that mutate state.")
        return

    # ── 3. Create custom model ────────────────────────────────────────────
    print(f"\n[3/7] Creating custom model: '{model_name}'...")
    cm = _dr_request(
        "POST",
        f"{base}/customModels/",
        token,
        body={
            "name": model_name,
            "targetType": "agenticWorkflow",
            "description": "Neo4j Research Agent with NAMS memory and MCP tool support.",
            "language": "Python",
        },
    )
    custom_model_id = cm["id"]
    print(f"  custom_model_id = {custom_model_id}")

    # ── 4. Create version and upload files ────────────────────────────────
    print("\n[4/7] Finding Python 3 execution environment...")
    env_id = _find_execution_environment(_normalize_dr_endpoint(endpoint), token)
    print(f"  execution_environment_id = {env_id}")

    print("  Creating custom model version and uploading files...")
    # DataRobot expects multipart upload for version creation with files
    # We upload each agent file individually via the version files endpoint

    # First create the version
    version_resp = _dr_request(
        "POST",
        f"{base}/customModels/{custom_model_id}/versions/",
        token,
        body={
            "baseEnvironmentId": env_id,
            "label": "v1.0.0",
            "isMajorUpdate": True,
        },
    )
    version_id = version_resp["id"]
    print(f"  custom_model_version_id = {version_id}")

    # Upload each file to the version
    print("  Uploading agent files...")
    for filename in AGENT_FILES:
        filepath = AGENT_DIR / filename
        if not filepath.exists():
            print(f"  SKIP (missing): {filename}")
            continue
        file_bytes = filepath.read_bytes()
        upload_url = f"{base}/customModels/{custom_model_id}/versions/{version_id}/files/"
        _dr_upload_files(upload_url, token, [("file", file_bytes, filename)])
        print(f"  Uploaded: {filename}")

    # ── 5. Wait for build ─────────────────────────────────────────────────
    print("\n[5/7] Waiting for custom model version build...")
    build_url = f"{base}/customModels/{custom_model_id}/versions/{version_id}/"
    result = _poll(
        build_url, token,
        done_states={"succeeded", "passed"},
        failed_states={"failed", "error"},
        status_key="buildStatus",
        interval=10,
        max_wait=300,
    )
    print(f"  Build status: {result.get('buildStatus')}")

    # ── 6. Register model ─────────────────────────────────────────────────
    print("\n[6/7] Registering model in Model Registry...")
    reg = _dr_request(
        "POST",
        f"{base}/registeredModels/",
        token,
        body={
            "customModelVersionId": version_id,
            "name": model_name,
        },
    )
    registered_model_id = reg.get("id") or reg.get("registeredModelId")
    registered_version_id = (
        reg.get("registeredModelVersionId")
        or (reg.get("registeredModelVersion") or {}).get("id")
    )
    print(f"  registered_model_id = {registered_model_id}")
    print(f"  registered_model_version_id = {registered_version_id}")

    # ── 7. Create deployment ──────────────────────────────────────────────
    print("\n[7/7] Creating deployment...")
    dep = _dr_request(
        "POST",
        f"{base}/deployments/fromRegisteredModel/",
        token,
        body={
            "registeredModelVersionId": registered_version_id,
            "label": model_name,
            "description": "Neo4j Research Agent deployment",
            "importance": "LOW",
        },
    )
    deployment_id = dep.get("id") or dep.get("deploymentId")
    print(f"  deployment_id = {deployment_id}")

    # ── Done ──────────────────────────────────────────────────────────────
    prediction_url = (
        f"{_normalize_dr_endpoint(endpoint)}/api/v2/deployments/{deployment_id}/chatCompletions/"
    )
    print("\n" + "=" * 60)
    print("Deployment complete!")
    print(f"  Model name:     {model_name}")
    print(f"  Model ID:       {custom_model_id}")
    print(f"  Version ID:     {version_id}")
    print(f"  Deployment ID:  {deployment_id}")
    print(f"\nChat endpoint:  {prediction_url}")
    print("\nNext steps:")
    print("  1. In DataRobot UI, open the deployment and set Runtime Parameters")
    print("     (OPENAI_API_KEY, NEO4J_PASSWORD, MEMORY_API_KEY, etc.)")
    print("  2. Test via the Playground tab or call the Chat endpoint directly:")
    print(f'     curl -X POST "{prediction_url}" \\')
    print(f'       -H "Authorization: Token $DATAROBOT_API_TOKEN" \\')
    print(f'       -H "Content-Type: application/json" \\')
    print(f"       -d '{{\"messages\": [{{\"role\": \"user\", \"content\": \"Tell me about Neo4j\"}}]}}'")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Manual upload guide (fallback when no API token available)
# ---------------------------------------------------------------------------

def print_manual_upload_steps(package_path: Path) -> None:
    print("Package created:", package_path)
    print("")
    print("Manual DataRobot upload steps:")
    print("1. In DataRobot, click 'Registry' in the top nav, then 'Workshop' in the LEFT sidebar.")
    print("   (Workshop is a sidebar item — not the same as the 'Data' or 'Models' sections)")
    print("2. Click the 'Agentic workflows' tab, then '+ Add a workflow'.")
    print("3. Enter a model name, confirm Target type = Agentic Workflow, click 'Add model'.")
    print("4. On the Assemble tab > Files section, upload all files from the ZIP package above.")
    print("5. On the Assemble tab > Runtime parameters, add all keys from agent/model-metadata.yaml.")
    print("6. (Optional) Click 'Test workflow' to verify the agent responds.")
    print("7. Click 'Register a workflow' > name it > 'Register a workflow'.")
    print("8. Go to Registry > Models > find your workflow > Deploy.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    load_environment()

    parser = argparse.ArgumentParser(
        description="Package, validate, and deploy the DataRobot Neo4j agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
commands:
  package               Build the ZIP archive and print manual upload steps
  validate              Verify DATAROBOT_ENDPOINT + DATAROBOT_API_TOKEN
  package-and-validate  Package + validate (no deployment)
  deploy                Full automated deployment via DataRobot API
  deploy --dry-run      Package + validate only, do not create any DR resources
""",
    )
    parser.add_argument(
        "command",
        choices=("package", "validate", "package-and-validate", "deploy"),
        help="Action to run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="For 'deploy': package and validate only, skip API mutations.",
    )
    args = parser.parse_args()

    if args.command == "package":
        print_manual_upload_steps(package_agent())
        return 0

    if args.command == "validate":
        ok, message = validate_datarobot_access()
        print(message)
        return 0 if ok else 1

    if args.command == "package-and-validate":
        print_manual_upload_steps(package_agent())
        ok, message = validate_datarobot_access()
        print(message)
        return 0 if ok else 1

    if args.command == "deploy":
        try:
            deploy_to_datarobot(dry_run=args.dry_run)
            return 0
        except (RuntimeError, TimeoutError) as exc:
            print(f"\nERROR: {exc}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
