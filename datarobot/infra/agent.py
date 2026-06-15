from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import urllib.request
import urllib.error

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:  # type: ignore[misc]
        return False

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"
DIST_DIR = ROOT / "dist"
PACKAGE_PATH = DIST_DIR / "neo4j_datarobot_agent.zip"


def load_environment() -> None:
    load_dotenv(ROOT / ".env")


def package_agent() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    files_to_package = [
        "__init__.py",
        "agent.py",
        "custom.py",
        "helpers.py",
        "memory.py",
        "mcp_client.py",
        "model-metadata.yaml",
        "requirements.txt",
    ]
    with ZipFile(PACKAGE_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for name in files_to_package:
            path = AGENT_DIR / name
            archive.write(path, arcname=name)
    return PACKAGE_PATH


def validate_datarobot_access(timeout: int = 20) -> tuple[bool, str]:
    endpoint = os.environ.get("DATAROBOT_ENDPOINT")
    token = os.environ.get("DATAROBOT_API_TOKEN")
    if not endpoint or not token:
        return False, "DATAROBOT_ENDPOINT or DATAROBOT_API_TOKEN is missing."

    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}/account/info/",
        headers={
            "Authorization": f"Token {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json as _json
            payload = _json.loads(resp.read().decode())
            username = payload.get("username") or payload.get("uid") or "unknown"
            return True, f"Authenticated as {username}."
    except urllib.error.HTTPError as exc:
        return False, f"{exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"


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


def main() -> int:
    load_environment()

    parser = argparse.ArgumentParser(description="Package and validate the DataRobot Neo4j agent.")
    parser.add_argument(
        "command",
        choices=("package", "validate", "package-and-validate"),
        help="Action to run.",
    )
    args = parser.parse_args()

    if args.command == "package":
        print_manual_upload_steps(package_agent())
        return 0

    if args.command == "validate":
        ok, message = validate_datarobot_access()
        print(message)
        return 0 if ok else 1

    print_manual_upload_steps(package_agent())
    ok, message = validate_datarobot_access()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
