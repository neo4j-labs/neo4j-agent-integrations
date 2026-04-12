"""Main application entry point for the A2A Agent Server."""
import logging
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from app.core.config import public_agent_card, REDIRECT_URL
from app.services.agent_executor import Neo4jADKExecutor
from app.api.middleware import OAuthValidationMiddleware
from app.api.marketplace import pubsub_handler, setup_page_handler, setup_save_handler

from app.api.auth_routes import dcr_handler, authorize_handler, token_handler
from starlette.responses import RedirectResponse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True)

async def root_redirect_handler(request):
    """
    Redirects root traffic (HTTP 301) to official page.
    """
    return RedirectResponse(url=REDIRECT_URL, status_code=301)

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

    app.add_route("/dcr", dcr_handler, methods=["POST"])
    logging.info("[main] Added /dcr route")
    app.add_route("/auth/authorize", authorize_handler, methods=["GET"])
    logging.info("[main] Added /auth/authorize route")
    app.add_route("/auth/token", token_handler, methods=["POST"])
    logging.info("[main] Added /auth/token route")
    app.add_route("/pubsub", pubsub_handler, methods=["POST"])
    logging.info("[main] Added /pubsub route")
    app.add_route("/setup", setup_page_handler, methods=["GET","POST"])
    logging.info("[main] Added /setup route")
    app.add_route("/setup/save", setup_save_handler, methods=["POST"])
    logging.info("[main] Added /setup/save route")
    app.add_route("/", root_redirect_handler, methods=["GET"])
    logging.info("[main] Added / root redirect route")

    app.add_middleware(OAuthValidationMiddleware)
    logging.info("[main] OAuthValidationMiddleware added")

    logging.info("[main] Starlette application creation complete")
    return app

app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)