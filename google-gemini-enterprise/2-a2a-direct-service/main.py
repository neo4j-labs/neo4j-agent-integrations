"""Main application entry point for the A2A Agent Server."""
import logging
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from app.core.config import public_agent_card
from app.services.agent_executor import Neo4jADKExecutor
from app.api.middleware import OAuthValidationMiddleware
from app.api.marketplace import setup_page_handler, setup_save_handler


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)

def create_app():
    """
    Creates and configures the Starlette application.
    """
    logging.info("[main] Creating Starlette application")
    request_handler = DefaultRequestHandler(
        agent_executor=Neo4jADKExecutor(),
        task_store=InMemoryTaskStore()
    )
    logging.info("[main] Request handler configured")
    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler
    )
    logging.info("[main] A2AStarletteApplication instance created")
    app = server.build()
    logging.info("[main] Base Starlette app built")

    app.add_route("/setup", setup_page_handler, methods=["GET"])
    logging.info("[main] Added /setup route")
    app.add_route("/setup/save", setup_save_handler, methods=["POST"])
    logging.info("[main] Added /setup/save route")

    app.add_middleware(OAuthValidationMiddleware)
    logging.info("[main] OAuthValidationMiddleware added")

    logging.info("[main] Starlette application creation complete")
    return app

app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)