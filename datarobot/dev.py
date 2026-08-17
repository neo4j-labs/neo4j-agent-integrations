"""IDE-friendly development server entrypoint for the Neo4j research agent.

Runs ``nat dragent serve`` in-process (single worker, no reload) so IDE
debuggers (VS Code, PyCharm) can attach and hit breakpoints in
``agent/myagent.py``/``agent/register.py``. For terminal use with
auto-reload, prefer ``task dev`` (see Taskfile.yml), which runs
``nat dragent serve --config_file agent/workflow.yaml --reload true`` directly.

Usage:
    python dev.py
"""

from __future__ import annotations

import os

from datarobot_genai.dragent.cli.commands import dragent_command


def main() -> None:
    port = os.environ.get("NEO4J_AGENT_PORT", "8842")
    print(f"Running development server on http://localhost:{port}")

    dragent_command.main(
        args=["serve", "--config_file", "agent/workflow.yaml", "--port", port],
        standalone_mode=False,
    )


if __name__ == "__main__":
    main()
