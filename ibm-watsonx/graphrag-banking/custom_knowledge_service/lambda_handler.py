"""AWS Lambda entry point for the Custom service knowledge source.

Mangum turns a Lambda Function URL event into an ASGI request, so the FastAPI
app in ``app.py`` runs unchanged. Set the function handler to
``lambda_handler.handler``.
"""

from app import app
from mangum import Mangum

# Startup runs once per cold start. It opens the Neo4j driver and checks that
# KNOWLEDGE_SERVICE_API_KEY is set.
handler = Mangum(app, lifespan="auto")
