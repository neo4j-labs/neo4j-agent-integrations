"""
OAuth 2.0 Middleware for validating bearer tokens against Google's token info endpoint.
"""
import logging
import json
import os
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from ..core.config import current_user_identity

EXPECTED_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
class OAuthValidationMiddleware:
    """Stateless ASGI Middleware for secure Google token validation."""
    def __init__(self, app):
        self.app = app
        # Reusing a single client is efficient and keeps the code simple
        self.http_client = httpx.AsyncClient()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope["path"]
        method = scope["method"]

        open_paths = ["/health", "/docs", "/.well-known/agent.json", "/.well-known/agent-card.json", "/favicon.ico"]
        if path in open_paths or (path == "/" and method == "GET"):
            return await self.app(scope, receive, send)

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

        try:
            # 1. Secure validation (POST keeps token out of URLs)
            resp = await self.http_client.post(
                "https://oauth2.googleapis.com/tokeninfo",
                data={"access_token": token}
            )

            if resp.status_code != 200:
                logging.warning(f"Token validation failed at Google: {resp.text}")
                return await respond_401("Invalid or expired OAuth access token")

            token_data = resp.json()

            # 2. Strict Audience (aud) Validation
            if token_data.get("aud") != EXPECTED_CLIENT_ID:
                logging.warning(f"Audience mismatch. Expected {EXPECTED_CLIENT_ID}")
                return await respond_401("Token audience mismatch")

            # 3. Scope Validation
            user_identity = token_data.get("email")
            if not user_identity:
                return await respond_401("Token is missing required 'email' scope")

            current_user_identity.set(user_identity)
            logging.info(f"Authenticated request securely from user: {user_identity}")

            return await self.app(scope, receive, send)

        except Exception as e:
            logging.error(f"Middleware Error: {str(e)}")
            return await respond_401("Internal authentication error")