"""
OAuth 2.0 Middleware for validating bearer tokens against Google's token info endpoint.
"""
import logging
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import json
from ..core.config import (
    current_user_identity
)

class OAuthValidationMiddleware:
    """Pure ASGI Middleware to ensure context variables survive to the A2A Executor."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope["path"]
        method = scope["method"]
        logging.info(f"Request received for {method} {path}")

        # Open routing bypass
        open_paths = ["/health", "/docs", "/.well-known/agent.json", "/.well-known/agent-card.json", "/favicon.ico"]
        if path in open_paths or (path == "/" and method == "GET"):
            logging.info(f"Bypassing auth for open path: {path}")
            return await self.app(scope, receive, send)

        # ASGI headers are byte-strings and always lowercase
        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8")

        async def respond_401(message):
            logging.warning(f"Authentication failed: {message}")
            response = json.dumps({"error": message}).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")]
            })
            await send({"type": "http.response.body", "body": response})

        if not auth_header or not auth_header.startswith("Bearer "):
            return await respond_401("Missing or invalid Authorization header")

        token = auth_header.split(" ")[1]
        logging.debug("Token extracted from header.")

        # Verify token with Google
        async with httpx.AsyncClient() as client:
            logging.info("Verifying token with Google...")
            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}")
            logging.info(f"Google token info response status: {resp.status_code}")

        if resp.status_code != 200:
            logging.warning(f"Token validation failed with status {resp.status_code}. Response: {resp.text}")
            return await respond_401("Invalid OAuth access token")

        token_data = resp.json()

        user_identity = token_data.get("email", token_data.get("sub", "unknown_user"))
        if user_identity == "unknown_user":
            logging.warning("Could not determine user identity from token.")

        current_user_identity.set(user_identity)
        logging.info(f"Authenticated request from user: {user_identity}")

        return await self.app(scope, receive, send)