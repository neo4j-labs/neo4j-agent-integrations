# Container image for DataRobot's Workload API (Path C).
#
# Builds and serves the Neo4j research agent (agent/server.py, wrapping the
# same agent/custom.py::chat() used by Path A's DRUM custom model) as a plain
# HTTP service. Must be linux/amd64 — the Workload API's platform crash-loops
# with "exec format error" on ARM64-only images (common on Apple Silicon).
#
# Build (from the datarobot/ directory):
#   docker buildx build --platform linux/amd64 -t <registry>/<org>/neo4j-datarobot-agent:latest --push .
#
# Deploy: see infra/workload.py (uses the resulting imageUri).

FROM python:3.11-slim

WORKDIR /app

COPY agent/requirements.txt ./agent/requirements.txt
RUN pip install --no-cache-dir -r agent/requirements.txt \
    && pip install --no-cache-dir fastapi "uvicorn[standard]" httpx

COPY agent/ ./agent/

ENV PORT=8080
EXPOSE 8080

# Port must be >=1024 per the Workload API; readiness/liveness probes hit
# /readyz and /healthz respectively (see infra/workload.py spec).
CMD ["python", "-m", "uvicorn", "agent.server:app", "--host", "0.0.0.0", "--port", "8080"]
