import logging
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from app.services.token_manager import TokenManager
from neo4j import GraphDatabase

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

        # Main DB Creds
        uri = form.get("neo4j_uri")
        user = form.get("neo4j_user")
        db = form.get("neo4j_database", "neo4j")
        pwd = form.get("neo4j_password")

        if not all([email, uri, user, pwd]):
            return HTMLResponse("<h2>Error: Missing required main database fields.</h2>", status_code=400)

        try:
            test_driver = GraphDatabase.driver(uri, auth=(user, pwd))
            test_driver.execute_query("RETURN 1", database_=db)
            test_driver.close()
        except Exception as e:
            logging.error(f"Setup validation failed for main DB: {e}")
            return HTMLResponse(f"<h2>Error: Failed to authenticate to main DB: {str(e)}</h2>", status_code=400)

        enable_memory = form.get("enable_memory") == "on"  
        memory_uri = form.get("memory_uri")
        memory_user = form.get("memory_user")
        memory_db = form.get("memory_database", "neo4j")
        memory_pwd = form.get("memory_password")
        nams_api_key = form.get("nams_api_key")

        # When memory is enabled, accept either memory DB credentials OR a NAMS API key
        if enable_memory:
            using_nams = bool(nams_api_key and nams_api_key.strip())
            has_memory_creds = all([memory_uri and memory_uri.strip(), memory_user and memory_user.strip(), memory_pwd and memory_pwd.strip()])

            if not (using_nams or has_memory_creds):
                return HTMLResponse("<h2>Error: Missing required memory database fields or NAMS API key.</h2>", status_code=400)

            if has_memory_creds and not using_nams:
                try:
                    mem_driver = GraphDatabase.driver(memory_uri, auth=(memory_user, memory_pwd))
                    mem_driver.execute_query("RETURN 1", database_=memory_db)
                    mem_driver.close()
                except Exception as e:
                    logging.error(f"Setup validation failed for memory DB: {e}")
                    return HTMLResponse(f"<h2>Error: Failed to authenticate to memory DB: {str(e)}</h2>", status_code=400)

            if using_nams:
                if len(nams_api_key.strip()) < 10:
                    return HTMLResponse("<h2>Error: NAMS API key appears invalid.</h2>", status_code=400)

        token_manager.save_tenant_config(
            email=email, 
            uri=uri, 
            db_user=user, 
            db_pass=pwd, 
            db_name=db,
            memory_uri=memory_uri if enable_memory else None,
            memory_user=memory_user if enable_memory else None,
            memory_pass=memory_pwd if enable_memory else None,
            memory_db=memory_db if enable_memory else None,
            nams_api_key=nams_api_key if nams_api_key else None
        )

        logging.info(f"Successfully registered new tenant database for: {email} (Memory Enabled: {enable_memory})")

        return HTMLResponse(
            "<h2>Setup Complete!</h2><p>You can now go to Gemini Enterprise, sign in with your Google account, and start chatting with your database.</p>"
        )

    except Exception as e:
        logging.error(f"Setup save error: {e}")
        return HTMLResponse(f"<h2>Server Error: {str(e)}</h2>", status_code=500)