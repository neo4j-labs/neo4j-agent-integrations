"""Main application entry point for the A2A Agent Server."""
import logging
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from app.core.config import public_agent_card
from app.services.agent_executor import Neo4jADKExecutor
from app.api.middleware import OAuthValidationMiddleware

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def create_app() -> A2AStarletteApplication:
    """
    Creates and configures the Starlette application.
    """
    request_handler = DefaultRequestHandler(
        agent_executor=Neo4jADKExecutor(),
        task_store=InMemoryTaskStore()
    )
    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler
    )
    app = server.build()

    app.add_middleware(OAuthValidationMiddleware)

    return app

app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)
