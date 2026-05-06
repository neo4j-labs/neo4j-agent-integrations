import logging
from datetime import date
from neo4j import GraphDatabase

from app.core.config import (
    TRACKING_NEO4J_URI,
    TRACKING_NEO4J_USER,
    TRACKING_NEO4J_PASS,
    DAILY_TOKEN_LIMIT
)

class TokenManager:
    def __init__(self):
        """Initializes the TokenManager with tracking database credentials."""
        logging.info("[token_manager] Initializing TokenManager")
        self.driver = GraphDatabase.driver(
            TRACKING_NEO4J_URI, auth=(TRACKING_NEO4J_USER, TRACKING_NEO4J_PASS)
        )
        self.default_daily_limit = int(DAILY_TOKEN_LIMIT)

    # ==========================================
    # 1. TENANT CONFIGURATION
    # ==========================================
    def save_tenant_config(
        self, 
        email: str, 
        uri: str, 
        db_user: str, 
        db_pass: str, 
        db_name: str,
        memory_uri: str = None,
        memory_user: str = None,
        memory_pass: str = None,
        memory_db: str = None,
        nams_api_key: str = None
    ) -> None:
        """Saves the user's specific Neo4j DB credentials and optional memory DB credentials."""
        query = """
        MERGE (u:User {email: $email})
        SET u.target_uri = $uri,
            u.target_user = $db_user,
            u.target_password = $db_pass,
            u.target_database = $db_name,
            u.memory_uri = $memory_uri,
            u.memory_user = $memory_user,
            u.memory_password = $memory_pass,
            u.memory_database = $memory_db,
            u.nams_api_key = $nams_api_key,
            u.is_active = true,
            u.created_at = coalesce(u.created_at, datetime()),
            u.updated_at = datetime(),
            u.tokens_used_today = coalesce(u.tokens_used_today, 0),
            u.daily_token_limit = coalesce(u.daily_token_limit, $default_limit)
        """
        try:
            self.driver.execute_query(
                query, 
                email=email, 
                uri=uri, 
                db_user=db_user, 
                db_pass=db_pass, 
                db_name=db_name,
                memory_uri=memory_uri,
                memory_user=memory_user,
                memory_pass=memory_pass,
                memory_db=memory_db,
                nams_api_key=nams_api_key,
                default_limit=self.default_daily_limit
            )
            logging.info(f"[token_manager] Successfully registered tenant config for: {email} (Memory configured: {bool(memory_uri)})")
        except Exception as e:
            logging.error(f"[token_manager] Failed to save tenant config for {email}: {e}")
            raise

    def get_user_credentials(self, email: str) -> dict:
        """Retrieves the target Neo4j credentials and optional memory credentials for a specific active user."""
        query = """
         MATCH (u:User {email: $email, is_active: true})
         RETURN u.target_uri AS uri, 
             u.target_user AS user, 
             u.target_password AS password, 
             u.target_database AS database,
             coalesce(u.memory_uri, null) AS memory_uri,
             coalesce(u.memory_user, null) AS memory_user,
             coalesce(u.memory_password, null) AS memory_password,
             coalesce(u.memory_database, null) AS memory_database,
             coalesce(u.nams_api_key, null) AS nams_api_key
        """
        try:
            records, _, _ = self.driver.execute_query(query, email=email)
            if not records:
                return None

            record = records[0]
            try:
                nams_key = record.get("nams_api_key", None)
            except Exception:
                nams_key = record["nams_api_key"] if "nams_api_key" in record else None

            return {
                "uri": record["uri"],
                "user": record["user"],
                "password": record["password"],
                "database": record["database"],
                "memory_uri": record["memory_uri"],
                "memory_user": record["memory_user"],
                "memory_password": record["memory_password"],
                "memory_database": record["memory_database"],
                "nams_api_key": nams_key
            }
        except Exception as e:
            logging.error(f"Failed to retrieve DB credentials for {email}: {e}")
            return None

    # ==========================================
    # 2. LLM TOKEN TRACKING LOGIC
    # ==========================================

    def check_limit(self, email: str) -> bool:
        """Checks if the user has exceeded their daily token limit."""
        today = date.today().isoformat()
        query = """
        MATCH (u:User {email: $email})
        SET u.tokens_used_today = CASE WHEN u.last_reset_date <> $today THEN 0 ELSE u.tokens_used_today END,
            u.last_reset_date = $today,
            u.last_seen_at = datetime()
        RETURN u.tokens_used_today AS used, u.daily_token_limit AS user_limit, u.is_active AS is_active
        """
        records, _, _ = self.driver.execute_query(query, email=email, today=today)
        if not records:
            return True  
        record = records[0]
        if not record["is_active"]:
            return False
        return record["used"] < record["user_limit"]

    def add_tokens(self, email: str, tokens: int):
        """Adds used tokens to the user's daily count."""
        if tokens <= 0: return
        query = """
        MATCH (u:User {email: $email})
        SET u.tokens_used_today = u.tokens_used_today + $tokens,
            u.updated_at = datetime()
        """
        try:
            self.driver.execute_query(query, email=email, tokens=tokens)
        except Exception as e:
            logging.error(f"[token_manager] Failed to add tokens for {email}: {e}")

    def close(self):
        """Closes the database driver connection."""
        self.driver.close()