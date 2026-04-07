"""
OAuth 2.0 Middleware for validating Google Access Tokens.
"""
import logging
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.config import current_user_identity 

class OAuthValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logging.info(f"[middleware] Intercepting request: {request.method} {request.url.path}")

        open_paths = [
            "/health", 
            "/docs", 
            "/.well-known/agent.json", 
            "/.well-known/agent-card.json", 
            "/favicon.ico",
            "/setup", 
            "/setup/save"
        ]

        if request.url.path in open_paths or (request.url.path == "/" and request.method == "GET"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logging.warning("[middleware] Missing or invalid Authorization header.")
            return JSONResponse({"error": "Unauthorized. Missing token."}, status_code=401)

        token = auth_header.split(" ")[1]

        try:
            # Ask Google to validate the token and give us the user's email
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {token}"}
                )

            if response.status_code != 200:
                logging.warning(f"[middleware] Google rejected the token: {response.text}")
                return JSONResponse({"error": "Invalid Google token"}, status_code=401)

            user_info = response.json()
            email = user_info.get("email")

            if not email:
                return JSONResponse({"error": "Google token missing email claim"}, status_code=401)

            # Store the email in the backpack for the agent_executor to find
            current_user_identity.set(email)
            logging.info(f"[middleware] Authenticated Google User: {email}")

            return await call_next(request)

        except Exception as e:
            logging.warning(f"[middleware] Token validation failed: {str(e)}")
            return JSONResponse({"error": "Server error during token validation"}, status_code=500)