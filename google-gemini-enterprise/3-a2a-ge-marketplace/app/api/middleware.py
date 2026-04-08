"""
Internal OAuth 2.0 Middleware for validating locally-issued AaaS tokens.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.context import current_order_id
from app.services.token_manager import TokenManager

class OAuthValidationMiddleware(BaseHTTPMiddleware):
    """Starlette HTTP Middleware for secure internal token validation."""

    async def dispatch(self, request, call_next):
        logging.info(f"[middleware] Intercepting request: {request.method} {request.url.path}")

        open_paths = [
            "/health", 
            "/docs", 
            "/.well-known/agent.json", 
            "/.well-known/agent-card.json", 
            "/favicon.ico",
            "/dcr", 
            "/auth/authorize", 
            "/auth/token",
            "/pubsub",  
            "/setup",
            "/setup/save"
        ]

        if request.url.path in open_paths or (request.url.path == "/" and request.method == "GET"):
            logging.info(f"[middleware] Path {request.url.path} is open, skipping auth.")
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logging.warning("[middleware] Missing or invalid Authorization header format.")
            return JSONResponse({"error": "Unauthorized. Missing token."}, status_code=401)

        token = auth_header.split(" ")[1]

        try:
            logging.info("[middleware] Verifying access token")
            payload = TokenManager.verify_access_token(token)

            order_id = payload.get("order_id")
            if not order_id:
                logging.warning("[middleware] Token is missing 'order_id' claim")
                return JSONResponse({"error": "Token missing order_id claim"}, status_code=401)

            current_order_id.set(order_id)
            logging.info(f"[middleware] Authenticated request securely for Order ID: {order_id}")

            return await call_next(request)

        except Exception as e:
            logging.warning(f"[middleware] Token validation failed: {str(e)}")
            return JSONResponse({"error": f"Invalid or expired access token: {str(e)}"}, status_code=401)