#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "snowflake-connector-python>=3.6",
# ]
# ///
"""Drop the objects the create-agent-via-ui screencast creates, so each recording starts clean.

It leaves the Terraform setup alone: the TERRAFORM_SVC user and role, and the warehouse grants.
It signs in as TERRAFORM_SVC with its key, and reads the settings from terraform.tfvars.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import snowflake.connector


CORTEX_DIR = Path(__file__).resolve().parents[1]
TFVARS = CORTEX_DIR / "samples" / "1-terraform" / "terraform.tfvars"
# The same statements the screencast's hidden cleanup step runs.
CLEANUP_SQL = CORTEX_DIR / "shared" / "sql" / "cleanup.sql"


def read_tfvars(path: Path) -> dict[str, str]:
    text = path.read_text()
    out: dict[str, str] = {}
    for match in re.finditer(r'^\s*([a-z_]+)\s*=\s*"([^"]*)"\s*$', text, re.MULTILINE):
        out[match.group(1)] = match.group(2)
    return out


def main() -> int:
    tfvars = read_tfvars(TFVARS)
    private_key_path = Path(os.path.expanduser(tfvars["snowflake_private_key_path"]))

    conn = snowflake.connector.connect(
        account=f'{tfvars["snowflake_organization_name"]}-{tfvars["snowflake_account_name"]}',
        user=tfvars["snowflake_service_user"],
        private_key_file=str(private_key_path),
        role="TERRAFORM_SVC",
        warehouse=tfvars["warehouse"],
    )
    try:
        cur = conn.cursor()
        for stmt in (line.rstrip(";") for line in CLEANUP_SQL.read_text().splitlines() if line.strip()):
            print(f"-> {stmt}", file=sys.stderr)
            cur.execute(stmt)
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
