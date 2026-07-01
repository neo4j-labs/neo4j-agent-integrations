"""FastAPI wrapper exposing the Neo4j research agent over HTTP for DataRobot's
Workload API (Path C).

The Workload API runs an arbitrary container as a managed service — it does
not know about DRUM's `chat()` convention, so this process must speak plain
HTTP. It reuses the exact same `agent/custom.py::chat()` logic that Path A's
DRUM custom model calls, so behavior (memory, MCP tools, Neo4j) is identical;
only the transport differs.

Endpoints:
  GET  /healthz              liveness probe
  GET  /readyz                readiness probe
  POST /v1/chat/completions  OpenAI-compatible chat completions
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:  # type: ignore[misc]
        return False

try:
    from .custom import chat as run_chat
    from .custom import load_model
except ImportError:
    from custom import chat as run_chat  # type: ignore[no-redef]
    from custom import load_model  # type: ignore[no-redef]

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "server.py requires fastapi + uvicorn. Install with: "
        "pip install fastapi 'uvicorn[standard]'"
    ) from exc

app = FastAPI(title="Neo4j DataRobot Agent (Workload API)")

_READY = False


@app.on_event("startup")
def _startup() -> None:
    global _READY
    load_model(code_dir=str(Path(__file__).resolve().parent))
    _READY = True


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness probe — required env/config has been loaded."""
    if not _READY:
        return JSONResponse(status_code=503, content={"status": "not-ready"})
    return JSONResponse(status_code=200, content={"status": "ready"})


@app.post("/v1/chat/completions")
def chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
    """OpenAI-compatible chat completions endpoint backed by the Neo4j agent."""
    try:
        return run_chat(payload, model=payload.get("model"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
