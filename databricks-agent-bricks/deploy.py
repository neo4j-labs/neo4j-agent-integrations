#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///

import argparse
import json
import shutil
import subprocess
import sys

import yaml


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description="Deploy Neo4j MCP app to Databricks")
    parser.add_argument("--app-name", required=True, help="App name (must start with 'mcp-')")
    parser.add_argument("--profile", default=None, help="Databricks CLI profile")
    parser.add_argument("--sync", action="store_true", help="Only sync files without full deploy")
    args = parser.parse_args()

    if not args.app_name.startswith("mcp-"):
        print("❌ App name must start with 'mcp-' for Databricks to treat it as an MCP server.")
        sys.exit(1)

    # Check Databricks CLI authentication
    auth_cmd = ["databricks", "current-user", "me"]
    if args.profile:
        auth_cmd += ["--profile", args.profile]

    result = run_cmd(auth_cmd)
    if result.returncode != 0:
        print("❌ Databricks CLI unauthenticated.")
        print()
        print("You must login first:")
        print("databricks auth login --host https://<your-databricks-workspace>")
        sys.exit(1)

    try:
        user_info = json.loads(result.stdout)
        if not user_info.get("active", False):
            print("❌ Databricks CLI user is not active.")
            sys.exit(1)
    except json.JSONDecodeError:
        print("❌ Unexpected response from Databricks CLI.")
        sys.exit(1)

    print("✅ Databricks CLI authenticated")

    if args.sync:
        print(f"Syncing files for app '{args.app_name}'...")

        sync_cmd = ["databricks", "workspace", "import-dir", "./app",
                     f"/Workspace/Users/{user_info['userName']}/.bundle/{args.app_name}/default/files/app",
                     "--overwrite"]
        if args.profile:
            sync_cmd += ["--profile", args.profile]

        result = subprocess.run(sync_cmd)
        if result.returncode != 0:
            print("❌ File sync failed.")
            sys.exit(1)

        print(f"✅ Files synced for app '{args.app_name}'")
    else:
        print(f"Deploying app '{args.app_name}'...")

        # Generate databricks.yml
        bundle_config = {
            "bundle": {"name": args.app_name},
            "resources": {
                "apps": {
                    "neo4j-mcp": {
                        "name": args.app_name,
                        "source_code_path": "./app",
                        "resources": [
                            {
                                "name": "neo4j-uri",
                                "secret": {
                                    "scope": "neo4j-agent",
                                    "key": "neo4j-uri",
                                    "permission": "READ",
                                },
                            },
                            {
                                "name": "username",
                                "secret": {
                                    "scope": "neo4j-agent",
                                    "key": "username",
                                    "permission": "READ",
                                },
                            },
                            {
                                "name": "password",
                                "secret": {
                                    "scope": "neo4j-agent",
                                    "key": "password",
                                    "permission": "READ",
                                },
                            },
                        ],
                    }
                }
            },
        }

        with open("databricks.yml", "w") as f:
            yaml.dump(bundle_config, f, default_flow_style=False, sort_keys=False)

        # Clean stale local Terraform state to avoid old app name references
        shutil.rmtree(".databricks/bundle", ignore_errors=True)

        # Deploy the bundle
        deploy_cmd = ["databricks", "bundle", "deploy"]
        if args.profile:
            deploy_cmd += ["--profile", args.profile]

        result = subprocess.run(deploy_cmd)
        if result.returncode != 0:
            print("❌ Deployment failed.")
            sys.exit(1)

        print(f"✅ App '{args.app_name}' deployed successfully")


if __name__ == "__main__":
    main()
