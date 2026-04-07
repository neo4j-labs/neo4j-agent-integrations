import logging
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.services.token_manager import TokenManager

token_manager = TokenManager()
templates = Jinja2Templates(directory="app/templates")

async def setup_page_handler(request: Request):
    """Renders the setup UI where users map their Google email to their DB."""
    return templates.TemplateResponse(
        "setup.html",
        {"request": request}
    )

async def setup_save_handler(request: Request):
    """Saves the user's DB credentials tied to their Google Workspace email."""
    try:
        form = await request.form()

        email = form.get("work_email")

        uri = form.get("neo4j_uri")
        user = form.get("neo4j_user")
        db = form.get("neo4j_database", "neo4j")
        pwd = form.get("neo4j_password")

        if not all([email, uri, user, pwd]):
            return HTMLResponse("<h2>Error: Missing required fields.</h2>", status_code=400)

        token_manager.save_tenant_config(
            email=email, 
            uri=uri, 
            db_user=user, 
            db_pass=pwd, 
            db_name=db
        )

        logging.info(f"Successfully registered new tenant database for: {email}")

        # 4. Show success page
        return HTMLResponse(
            "<h2>Setup Complete!</h2><p>You can now go to Gemini Enterprise, sign in with your Google account, and start chatting with your database.</p>"
        )

    except Exception as e:
        logging.error(f"Setup save error: {e}")
        return HTMLResponse(f"<h2>Server Error: {str(e)}</h2>", status_code=500)