import base64
import json
import urllib.parse
import httpx
import logging
import secrets

from starlette.responses import JSONResponse, RedirectResponse
from starlette.requests import Request
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.core.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SERVICE_URL, PROVIDER_URL, AGENTSPACE_SA_EMAIL, GOOGLE_CERTS_URL
from app.services.token_manager import TokenManager 



token_manager = TokenManager()

async def dcr_handler(request: Request):
    """Handles Dynamic Client Registration (DCR) securely using Google Auth."""
    logging.info("[auth] dcr_handler: Received DCR request")
    try:
        body = await request.json()

        software_statement = body.get("software_statement")

        if not software_statement:
            logging.warning("[auth] dcr_handler: Missing software_statement in request")
            return JSONResponse({"error": "Missing software_statement"}, status_code=400)

        logging.info("[auth] dcr_handler: Verifying software_statement token")
        decoded_payload = id_token.verify_token(
            software_statement,
            google_requests.Request(),
            audience=PROVIDER_URL,
            certs_url=GOOGLE_CERTS_URL
        )

        valid_issuers = [AGENTSPACE_SA_EMAIL, f"https://{AGENTSPACE_SA_EMAIL}", GOOGLE_CERTS_URL]
        if decoded_payload.get("iss") not in valid_issuers:
             logging.warning(f"[auth] dcr_handler: Invalid issuer: {decoded_payload.get('iss')}")
             return JSONResponse({"error": "Invalid issuer"}, status_code=400)

        order_info = decoded_payload.get("google", {})
        order_id = order_info.get("order")

        if not order_id:
            logging.error("[auth] dcr_handler: Missing Marketplace Order ID in DCR payload")
            raise ValueError("Missing Marketplace Order ID in DCR payload")

        logging.info(f"[auth] DCR verification successful. Resolving client for Order: {order_id}")

        creds = token_manager.register_new_client(order_id)

        logging.info("[auth] dcr_handler: Returning credentials to Gemini Enterprise")
        return JSONResponse({
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "client_secret_expires_at": 0  
        })

    except ValueError as e:
        logging.error(f"[auth] DCR JWT Invalid: {e}")
        return JSONResponse({"error": "Invalid token"}, status_code=401)
    except Exception as e:
        logging.error(f"[auth] DCR Handler Error: {e}")
        return JSONResponse({"error": "Internal server error"}, status_code=500)



async def authorize_handler(request: Request):
    """
    Step 1: Intercept Gemini's auth request and redirect to Google OIDC to get the user's email.
    """
    logging.info("[auth_routes] authorize_handler: Initiating Federated Google Auth")
    client_id = request.query_params.get("client_id")
    redirect_uri = request.query_params.get("redirect_uri")
    gemini_state = request.query_params.get("state")

    if not client_id or not redirect_uri:
        return JSONResponse({"error": "Missing client_id or redirect_uri"}, status_code=400)

    state_data = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "gemini_state": gemini_state
    }
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

    google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{SERVICE_URL}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email",
        "state": encoded_state,
        "access_type": "online",
        "prompt": "select_account"
    }

    redirect_url = f"{google_auth_url}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(redirect_url)



async def google_callback_handler(request: Request):
    """
    Step 2: Receive Google's token, extract email, and redirect back to Gemini.
    """
    logging.info("[auth_routes] google_callback_handler: Received Google auth callback")
    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state")

    if not code or not encoded_state:
        return JSONResponse({"error": "Missing code or state from Google"}, status_code=400)

    try:
        state_data = json.loads(base64.urlsafe_b64decode(encoded_state.encode()).decode())
        client_id = state_data["client_id"]
        redirect_uri = state_data["redirect_uri"]
        gemini_state = state_data["gemini_state"]

        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": f"{SERVICE_URL}/auth/google/callback"
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=data)
            resp.raise_for_status()
            token_data = resp.json()

        id_token_jwt = token_data.get("id_token")
        if not id_token_jwt:
            raise ValueError("Failed to retrieve ID token from Google")

        id_info = id_token.verify_oauth2_token(id_token_jwt, google_requests.Request(), GOOGLE_CLIENT_ID)
        user_email = id_info.get("email")

        if not user_email:
            raise ValueError("Email scope not provided by Google")

        logging.info(f"[auth_routes] Successfully authenticated user: {user_email}")

        auth_code = token_manager.generate_auth_code(client_id, user_email)

        params = {"code": auth_code}
        if gemini_state:
            params["state"] = gemini_state

        final_redirect = f"{redirect_uri}?{urllib.parse.urlencode(params)}"
        return RedirectResponse(final_redirect)

    except Exception as e:
        logging.error(f"[auth_routes] Google Callback Error: {e}", exc_info=True)
        return JSONResponse({"error": "Authentication failed"}, status_code=500)



async def token_handler(request: Request):
    """
    Step 3 of the OAuth Flow.
    Token exchange with strict RFC 6749 headers and refresh token support.
    """
    logging.info("[auth] token_handler: Received token request")
    form = await request.form()
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    code = form.get("code")
    refresh_token = form.get("refresh_token")
    grant_type = form.get("grant_type", "authorization_code")

    headers = {
        "Cache-Control": "no-store",
        "Pragma": "no-cache"
    }

    try:
        if grant_type == "authorization_code":
            logging.info("[auth] token_handler: Handling authorization_code grant")
            if not all([client_id, client_secret, code]):
                return JSONResponse({"error": "invalid_request"}, status_code=400)

            access_token, order_id, user_email = token_manager.exchange_code_for_token(client_id, client_secret, code)

            secure_refresh_token = secrets.token_urlsafe(64)

            token_manager.store_refresh_token(client_id, user_email, secure_refresh_token)

            return JSONResponse({
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token": secure_refresh_token,
                "scope": "marketplacescopes.read"
            }, headers=headers)

        elif grant_type == "refresh_token":
            logging.info("[auth_routes] token_handler: Handling refresh_token grant")
            if not refresh_token or not client_id or not client_secret:
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            new_access_token = token_manager.refresh_access_token(client_id, client_secret, refresh_token)

            return JSONResponse({
                "access_token": new_access_token,
                "token_type": "bearer",
                "expires_in": 3600
            }, headers=headers)

        else:
             return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    except ValueError as e:
        logging.warning(f"[auth_routes] Token exchange rejected: {e}")
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    except Exception as e:
        logging.error(f"[auth_routes] Token exchange error: {e}", exc_info=True)
        return JSONResponse({"error": "server_error"}, status_code=500)