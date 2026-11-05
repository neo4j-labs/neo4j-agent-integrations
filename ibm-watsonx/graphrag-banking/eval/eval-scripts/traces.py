"""List recent agent traces, or dump one trace's observations, from agentops-v3.

`orchestrate observability traces export` never sends the start-time window that
/observations requires, so this calls the API directly.

Run with the ADK's Python:

    ADK_PY="$(uv tool dir)/ibm-watsonx-orchestrate/bin/python"
    "$ADK_PY" -I eval/eval-scripts/traces.py list <minutes>
    "$ADK_PY" -I eval/eval-scripts/traces.py get <trace_id> <out.json>

A trace's sessionId is the run's thread_id. Only traces from the last four hours
can be dumped.
"""

import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ibm_watsonx_orchestrate.cli.commands.observability.traces.traces_controller import (
    TracesController,
)
from ibm_watsonx_orchestrate_clients.common.base_client import ClientAPIException

FMT = "%Y-%m-%dT%H:%M:%SZ"
MAX_WINDOW_MINUTES = 239  # /observations rejects windows over four hours


def window(minutes: int) -> tuple[str, str]:
    now = datetime.now(UTC)
    start = now - timedelta(minutes=minutes)
    return start.strftime(FMT), (now + timedelta(minutes=1)).strftime(FMT)


def get(client, path: str, params: dict) -> dict:
    # /observations allows four requests per minute, so wait out a 429.
    for attempt in range(6):
        try:
            return client._get(f"{client.base_endpoint}/{path}", params=params)
        except ClientAPIException as e:
            if e.response is None or e.response.status_code != 429 or attempt == 5:
                raise
            time.sleep(20)
    raise RuntimeError("unreachable")


def main() -> None:
    client = TracesController().get_client()
    if sys.argv[1] == "list":
        start, end = window(int(sys.argv[2]))
        params = {
            "page": 1,
            "limit": 200,
            "fromTimestamp": start,
            "toTimestamp": end,
            "orderBy": "timestamp.asc",
        }
        for t in get(client, "traces", params)["data"]:
            attrs = (t.get("metadata") or {}).get("attributes") or {}
            if attrs.get("agent.name"):
                print(
                    t["id"],
                    t.get("timestamp"),
                    attrs["agent.name"],
                    t.get("sessionId"),
                    t.get("latency"),
                )
    else:
        trace_id, out = sys.argv[2], sys.argv[3]
        start, end = window(MAX_WINDOW_MINUTES)
        obs, page = [], 1
        while True:
            params = {
                "page": page,
                "limit": 100,
                "traceId": trace_id,
                "fromStartTime": start,
                "toStartTime": end,
            }
            r = get(client, "observations", params)
            obs += r["data"]
            if page >= (r.get("meta") or {}).get("totalPages", 1):
                break
            page += 1
        obs.sort(key=lambda o: o["startTime"])
        Path(out).write_text(json.dumps(obs, indent=1, default=str))
        print(f"{len(obs)} observations -> {out}")


if __name__ == "__main__":
    main()
