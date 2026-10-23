# Build from the graphrag-banking folder, so the image can copy src/:
#   docker build -f custom_knowledge_service/Dockerfile -t neo4j-knowledge-service .
FROM python:3.13-slim

WORKDIR /app
COPY custom_knowledge_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/graphrag_banking src/graphrag_banking
COPY custom_knowledge_service/app.py .
ENV PYTHONPATH=/app/src

# Settings come from environment variables. No .env file is copied in.
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
