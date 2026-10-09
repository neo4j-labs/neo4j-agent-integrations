import asyncio
import base64
import json
import logging
import time
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from app.services.token_manager import TokenManager
from starlette.templating import Jinja2Templates
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import google.auth
from google.auth.transport.requests import AuthorizedSession
from app.core.config import MARKETPLACE_PROVIDER_ID,MARKETPLACE_CERTS_URL

token_manager = TokenManager()
templates = Jinja2Templates(directory="app/templates")



def _post_with_retry(authed_session, url: str, json_body: dict, max_attempts: int = 3):
    """POSTs to the Procurement API, retrying with backoff on 429 (quota) responses."""
    delay_seconds = 2
    resp = None
    for attempt in range(1, max_attempts + 1):
        resp = authed_session.post(url, json=json_body)
        if resp.status_code != 429 or attempt == max_attempts:
            return resp
        logging.warning(
            f"[marketplace] Procurement API quota hit (429) on {url}, "
            f"retrying in {delay_seconds}s (attempt {attempt}/{max_attempts})"
        )
        time.sleep(delay_seconds)
        delay_seconds *= 2
    return resp

def approve_marketplace_account(procurement_account_id: str) -> bool:
    """Approves the GCP Procurement Account. Returns True on success."""
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        authed_session = AuthorizedSession(credentials)
        account_resource = f"providers/{MARKETPLACE_PROVIDER_ID}/accounts/{procurement_account_id}"
        account_url = f"https://cloudcommerceprocurement.googleapis.com/v1/{account_resource}:approve"

        resp = _post_with_retry(authed_session, account_url, {"approvalName": "signup"})
        if resp.status_code != 200:
            logging.error(f"Account approval failed: {resp.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"Error approving account: {e}")
        return False

def approve_marketplace_entitlement(entitlement_id: str) -> bool:
    """Approves the Entitlement to start the billing cycle AFTER setup. Returns True on success."""
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        authed_session = AuthorizedSession(credentials)
        entitlement_resource = f"providers/{MARKETPLACE_PROVIDER_ID}/entitlements/{entitlement_id}"
        entitlement_url = f"https://cloudcommerceprocurement.googleapis.com/v1/{entitlement_resource}:approve"

        resp = _post_with_retry(authed_session, entitlement_url, {})
        if resp.status_code != 200:
            logging.error(f"Entitlement approval failed: {resp.text}")
            return False
        return True
    except Exception as e:
        logging.error(f"Error approving entitlement: {e}")
        return False

def get_account_from_entitlement(entitlement_id: str) -> str:
    """Makes a GET request to Google to find the Account ID for an Entitlement."""
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        authed_session = AuthorizedSession(credentials)
        entitlement_resource = f"providers/{MARKETPLACE_PROVIDER_ID}/entitlements/{entitlement_id}"
        url = f"https://cloudcommerceprocurement.googleapis.com/v1/{entitlement_resource}"

        logging.info(f"Fetching entitlement details for {entitlement_id} to find missing account ID...")
        resp = authed_session.get(url)

        if resp.status_code != 200:
            logging.error(f"Failed to fetch entitlement details: {resp.text}")
            return None

        data = resp.json()
        account_resource_name = data.get("account", "")

        if account_resource_name:
            account_id = account_resource_name.split("/")[-1]
            return account_id

        return None
    except Exception as e:
        logging.error(f"Error fetching account for entitlement {entitlement_id}: {e}")
        return None
    
async def pubsub_handler(request: Request):
    """
    Receives push notifications from Google Cloud Pub/Sub about Marketplace events.
    Acknowledges quickly with 200 OK so messages do not accumulate or trigger redelivery storms.
    """
    try:
        body = await request.json()
        logging.info(f"[marketplace] Raw Pub/Sub body received: {body}")

        encoded_data = body.get("message", {}).get("data")
        if not encoded_data:
            logging.warning("[marketplace] Dropped request: No 'data' payload found in message.")
            return JSONResponse({"status": "ignored"}, status_code=200)

        event_data = json.loads(base64.b64decode(encoded_data).decode('utf-8'))
        event_type = event_data.get("eventType")

        account_id = event_data.get("account", {}).get("id")
        entitlement_id = event_data.get("entitlement", {}).get("id")

        if not event_type:
            return JSONResponse({"status": "ignored", "reason": "Missing eventType"}, status_code=200)

        # Fallback query if account_id is omitted by Google for an entitlement event
        if not account_id and entitlement_id:
            account_id = await asyncio.to_thread(get_account_from_entitlement, entitlement_id)
            if account_id:
                logging.info(f"[marketplace] Successfully retrieved missing account_id: {account_id}")
            else:
                logging.warning(f"[marketplace] Could not fetch account_id for entitlement {entitlement_id}")

        if not account_id and not entitlement_id:
            return JSONResponse({"status": "ignored", "reason": "Missing both Account and Entitlement IDs"}, status_code=200)

        logging.info(f"[marketplace] Received Event: {event_type} | Account: {account_id} | Entitlement: {entitlement_id}")

        # Record and update the internal Neo4j tracking state only.
        # Approvals are intentionally deferred until the admin completes the setup form.
        token_manager.handle_marketplace_event(event_type, account_id, entitlement_id)

        # Always return 200 to acknowledge the message and drain the Pub/Sub queue
        return JSONResponse({"status": "success"}, status_code=200)

    except Exception as e:
        logging.error(f"[marketplace] Error handling Pub/Sub message: {e}")
        # Return 200 to prevent poisoned or malformed payloads from entering an infinite retry loop
        return JSONResponse({"status": "error_handled", "error": str(e)}, status_code=200)
    
async def setup_page_handler(request: Request):
    """
    Renders the setup UI.
    Google redirects the admin here via POST immediately after they click 'Purchase',
    including the secure 'x-gcp-marketplace-token'.
    """
    order_id = ""

    if request.method == "POST":
        form = await request.form()
        token = form.get("x-gcp-marketplace-token")

        if token:
            try:
                payload = id_token.verify_token(
                    token,
                    google_requests.Request(),
                    certs_url=MARKETPLACE_CERTS_URL
                )

                google_account_id = payload.get("sub")
                logging.info(f"Marketplace SSO Login successful for Google Account: {google_account_id}")

                order_id = payload.get("commerce", {}).get("order_id", "") 

            except Exception as e:
                logging.error(f"Failed to verify Marketplace SSO Token: {e}")
                return HTMLResponse("<h2>Error: Invalid or Expired Marketplace Token.</h2>", status_code=401)
        else:
            return HTMLResponse("<h2>Error: Missing Marketplace Token.</h2>", status_code=400)
    
    elif request.method == "GET":
        order_id = request.query_params.get("order_id", "")

    return templates.TemplateResponse(
        request,
        "setup.html",
        {"order_id": order_id}
    )

async def setup_save_handler(request: Request):
    """
    Receives submitted credentials, updates the internal database, and
    triggers Google Procurement approvals off the main event loop.
    """
    try:
        form = await request.form()
        order_id = form.get("order_id")
        email = form.get("admin_email")
        database = form.get("neo4j_database", "neo4j")
        uri = form.get("neo4j_uri")
        user = form.get("neo4j_user")
        password = form.get("neo4j_password")

        if not all([order_id, email, uri, user, password]):
            return HTMLResponse("<h2>Error: Missing required fields. Please go back.</h2>", status_code=400)

        # 1. Activate credentials in tracking database
        token_manager.activate_user_credentials(
            order_id, uri, user, password, database, email
        )

        # 2. Retrieve the mapped account and entitlement IDs for this Order
        account_id = token_manager.get_account_id(order_id)
        entitlement_id = token_manager.get_entitlement_id(order_id)

        # 3. Offload synchronous HTTP requests + backoff sleep to a worker thread
        # so Starlette's asyncio event loop never blocks
        if account_id:
            account_approved = await asyncio.to_thread(approve_marketplace_account, account_id)
            if not account_approved:
                logging.error(f"[setup] Account approval failed for {account_id}")

        if entitlement_id:
            entitlement_approved = await asyncio.to_thread(approve_marketplace_entitlement, entitlement_id)
            if not entitlement_approved:
                logging.error(f"[setup] Entitlement approval failed for {entitlement_id}")

        return templates.TemplateResponse(request, "success.html")

    except ValueError as ve:
        logging.warning(f"Validation failed during setup: {ve}")
        return HTMLResponse(f"<h2>Security Error: {str(ve)}</h2><p>Please check your Procurement Account ID.</p>", status_code=403)
    except Exception as e:
        logging.error(f"Setup save error: {e}")
        return HTMLResponse(f"<h2>Server Error: {str(e)}</h2>", status_code=500)