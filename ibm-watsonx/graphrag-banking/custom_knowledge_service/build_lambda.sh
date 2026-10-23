#!/usr/bin/env bash
# Build orchestrate/build/knowledge_service.zip for AWS Lambda (python3.13, arm64).
# Run from the graphrag-banking folder:
#   ./custom_knowledge_service/build_lambda.sh
set -euo pipefail

SERVICE_DIR=custom_knowledge_service
OUT=orchestrate/build/knowledge_service
ZIP="$PWD/orchestrate/build/knowledge_service.zip"

rm -rf "$OUT" "$ZIP"
mkdir -p "$OUT"

# Install Linux arm64 wheels, whatever this machine is. Lambda cannot compile.
uv pip install --quiet --target "$OUT" \
  --python-platform aarch64-manylinux2014 --python-version 3.13 \
  --only-binary :all: -r "$SERVICE_DIR/requirements-lambda.txt"

cp -r src/graphrag_banking "$OUT/graphrag_banking"
cp "$SERVICE_DIR/app.py" "$SERVICE_DIR/lambda_handler.py" "$OUT/"
find "$OUT" -name __pycache__ -type d -prune -exec rm -rf {} +

(cd "$OUT" && zip -q -r "$ZIP" .)
echo "Built $ZIP ($(du -h "$ZIP" | cut -f1))"
