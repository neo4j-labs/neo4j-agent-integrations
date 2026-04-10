"""Manages LLM token usage, rate limits, and OAuth 2.0 credentials."""
import hashlib
import logging
import uuid
import time
import jwt
from datetime import date
from neo4j import GraphDatabase
import google.auth
from google.cloud import secretmanager
from google.api_core.exceptions import AlreadyExists

from ..core.config import (
    TRACKING_NEO4J_URI,
    TRACKING_NEO4J_USER,
    TRACKING_NEO4J_PASS,
    DAILY_TOKEN_LIMIT,
    INTERNAL_SECRET_KEY 
)

class TokenManager:
    def __init__(self):
        """Initializes the TokenManager with database and GCP credentials."""
        logging.info("[token_manager] Initializing TokenManager")
        self.driver = GraphDatabase.driver(
            TRACKING_NEO4J_URI, auth=(TRACKING_NEO4J_USER, TRACKING_NEO4J_PASS)
        )
        self.default_daily_limit = int(DAILY_TOKEN_LIMIT)

        self.secret_client = secretmanager.SecretManagerServiceClient()
        _, self.project_id = google.auth.default()

        logging.info("[token_manager] TokenManager initialized successfully")

    def _store_password_in_secret_manager(self, order_id: str, password: str) -> str:
        """Creates a secret in GCP and adds the password as a new version."""
        parent = f"projects/{self.project_id}"
        secret_id = f"neo4j-cred-{order_id}"
        try:
            secret = self.secret_client.create_secret(
                request={"parent": parent, "secret_id": secret_id, "secret": {"replication": {"automatic": {}}}}
            )
            secret_name = secret.name
        except AlreadyExists:
            secret_name = f"{parent}/secrets/{secret_id}"

        payload = password.encode("UTF-8")
        self.secret_client.add_secret_version(request={"parent": secret_name, "payload": {"data": payload}})
        return secret_name

    def _get_password_from_secret_manager(self, secret_name: str) -> str:
        name = f"{secret_name}/versions/latest"
        response = self.secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")

    # ==========================================
    # 1. LLM TOKEN TRACKING LOGIC
    # ==========================================

    def check_limit(self, email: str, order_id: str) -> bool:
        """
        Checks if the user has exceeded their specific daily token limit.
        Resets the limit if it's a new day and enforces the is_active flag.
        """
        logging.info(f"[token_manager] Checking limit for user: {email} under order: {order_id}")
        today = date.today().isoformat()
        
        query = """
        MATCH (o:Order {id: $order_id})
        MERGE (u:User {email: $email})
        ON CREATE SET
            u.tokens_used_today = 0,
            u.total_tokens_used = 0,
            u.daily_token_limit = $default_limit,
            u.created_at = datetime()
        MERGE (u)-[:BELONGS_TO]->(o)
        WITH u, o, CASE WHEN u.last_reset_date <> $today THEN 0 ELSE u.tokens_used_today END AS used
        SET u.tokens_used_today = used,
            u.last_reset_date = $today,
            u.last_seen_at = datetime()
        RETURN used, u.daily_token_limit AS user_limit, o.is_active AS is_active
        """
        try:
            records, _, _ = self.driver.execute_query(
                query, email=email, order_id=order_id, today=today, default_limit=self.default_daily_limit
            )
            if not records:
                logging.warning(f"[token_manager] Limit check failed: Order {order_id} not found.")
                return False

            record = records[0]
            if not record["is_active"]:
                logging.warning(f"[token_manager] Blocked: Parent Order {order_id} is inactive.")
                return False

            return record["used"] < record["user_limit"]
        except Exception as e:
            logging.error(f"[token_manager] Failed to check token limit for {email}: {e}")
            return False

    def add_tokens(self, email: str, tokens: int):
        if tokens <= 0: return
        query = """
        MATCH (u:User {email: $email})
        SET u.tokens_used_today = u.tokens_used_today + $tokens,
            u.total_tokens_used = coalesce(u.total_tokens_used, 0) + $tokens,
            u.updated_at = datetime()
        """
        try:
            self.driver.execute_query(query, email=email, tokens=tokens)
        except Exception as e:
            logging.error(f"[token_manager] Failed to update token usage for {email}: {e}")

    # ==========================================
    # 2. OAUTH 2.0 & MULTI-TENANT LOGIC
    # ==========================================

    def hash_secret(self, secret_string: str) -> str:
        return hashlib.sha256(secret_string.encode('utf-8')).hexdigest()

    def register_new_client(self, order_id: str) -> dict:
        logging.info(f"[token_manager] Creating NEW client instance for order: {order_id}")
        new_client_id = f"client_{uuid.uuid4().hex[:12]}"
        new_client_secret = uuid.uuid4().hex
        hashed_secret = self.hash_secret(new_client_secret)
        today = date.today().isoformat()

        query = """
        MATCH (o:Order {id: $order_id})
        CREATE (c:OAuthClient {
            client_id: $new_client_id, 
            client_secret_hash: $hashed_secret,
            order_id: $order_id,
            created_at: datetime(),
            updated_at: datetime()
        })
        MERGE (o)-[:HAS_CLIENT]->(c)
        RETURN c.client_id AS client_id
        """
        try:
            records, _, _ = self.driver.execute_query(
                query, order_id=order_id, new_client_id=new_client_id, hashed_secret=hashed_secret, today=today
            )
            if not records:
                raise ValueError("Order ID not found. Ensure purchase is completed.")
            return {"client_id": new_client_id, "client_secret": new_client_secret}
        except Exception as e:
            logging.error(f"[token_manager] Failed to register OAuth client: {e}")
            raise Exception("Database error during client registration")
        
    def generate_auth_code(self, client_id: str, email: str) -> str:
        """Generates a temporary code, stores its HASH, and returns the plain text."""
        plain_code = f"code_{uuid.uuid4().hex}"
        hashed_code = self.hash_secret(plain_code)

        query = """
        CREATE (a:AuthCode {
            code_hash: $hashed_code, 
            client_id: $client_id, 
            email: $email,
            created_at: datetime()
        })
        """
        self.driver.execute_query(query, hashed_code=hashed_code, client_id=client_id, email=email)
        return plain_code 

    def exchange_code_for_token(self, client_id: str, client_secret: str, code: str) -> tuple[str, str, str]:
        """Validates hashed credentials, deletes the code, and issues a JWT."""
        hashed_secret = self.hash_secret(client_secret)
        hashed_code = self.hash_secret(code)

        query = """
        MATCH (c:OAuthClient {client_id: $client_id, client_secret_hash: $hashed_secret})
        MATCH (a:AuthCode {code_hash: $hashed_code, client_id: $client_id})
        WITH c, a, a.email AS user_email
        DELETE a  
        RETURN c.order_id AS order_id, user_email
        """
        records, _, _ = self.driver.execute_query(
            query, client_id=client_id, hashed_secret=hashed_secret, hashed_code=hashed_code
        )

        if not records:
            raise ValueError("Invalid client credentials or authorization code")

        order_id = records[0]["order_id"]
        user_email = records[0]["user_email"]

        payload = {"sub": client_id, "order_id": order_id, "email": user_email, "exp": time.time() + 3600}
        token = jwt.encode(payload, INTERNAL_SECRET_KEY, algorithm="HS256")
        return token, order_id, user_email

    def store_refresh_token(self, client_id: str, email: str, refresh_token: str) -> None:
        """Hashes and stores the refresh token in Neo4j."""
        hashed_refresh = self.hash_secret(refresh_token)
        query = """
        MATCH (c:OAuthClient {client_id: $client_id})
        MERGE (r:RefreshToken {client_id: $client_id, email: $email})
        SET r.hash = $hashed_refresh, r.updated_at = datetime()
        MERGE (c)-[:HAS_REFRESH_TOKEN]->(r)
        """
        self.driver.execute_query(query, client_id=client_id, email=email, hashed_refresh=hashed_refresh)

    def refresh_access_token(self, client_id: str, client_secret: str, refresh_token: str) -> str:
        """Validates the refresh token and issues a new JWT access token."""
        hashed_client_secret = self.hash_secret(client_secret)
        hashed_refresh_token = self.hash_secret(refresh_token)
        
        query = """
        MATCH (c:OAuthClient {client_id: $client_id, client_secret_hash: $hashed_secret})-[:HAS_REFRESH_TOKEN]->(r:RefreshToken {hash: $hashed_refresh})
        RETURN c.order_id AS order_id, r.email AS user_email
        """
        records, _, _ = self.driver.execute_query(
            query, client_id=client_id, hashed_secret=hashed_client_secret, hashed_refresh=hashed_refresh_token
        )
        if not records:
            raise ValueError("Invalid refresh token or client credentials")

        order_id = records[0]["order_id"]
        user_email = records[0]["user_email"]

        payload = {"sub": client_id, "order_id": order_id, "email": user_email, "exp": time.time() + 3600}
        return jwt.encode(payload, INTERNAL_SECRET_KEY, algorithm="HS256")

    def handle_marketplace_event(self, event_type: str, account_id: str = None, entitlement_id: str = None) -> None:
        """Handles lifecycle events from GCP."""
        if account_id:
            account_query = """
            MERGE (a:ProcurementAccount {id: $account_id})
            SET a.last_event = $event_type, a.updated_at = datetime()
            """
            self.driver.execute_query(account_query, account_id=account_id, event_type=event_type)

        if entitlement_id and event_type.startswith("ENTITLEMENT_"):
            status_map = {
                "ENTITLEMENT_OFFER_ACCEPTED": "PENDING",
                "ENTITLEMENT_CREATION_REQUESTED": "PENDING",
                "ENTITLEMENT_ACTIVE": "ACTIVE",
                "ENTITLEMENT_PLAN_CHANGED": "ACTIVE",
                "ENTITLEMENT_CANCELLED": "CANCELED",
                "ENTITLEMENT_PENDING_CANCELLATION": "ACTIVE",
                "ENTITLEMENT_SUSPENDED": "SUSPENDED"
            }
            new_status = status_map.get(event_type, "UNKNOWN")

            entitlement_query = """
            MERGE (o:Order {id: $entitlement_id})
            ON CREATE SET 
                o.created_at = datetime(),
                o.daily_token_limit = $default_limit,
                o.status = $new_status,
                o.is_active = CASE WHEN $new_status = 'ACTIVE' THEN true ELSE false END
            ON MATCH SET 
                o.status = $new_status,
                o.is_active = CASE WHEN $new_status = 'ACTIVE' THEN true ELSE false END,
                o.updated_at = datetime()
            """
            self.driver.execute_query(entitlement_query, entitlement_id=entitlement_id, new_status=new_status, default_limit=self.default_daily_limit)

            if account_id:
                link_query = """
                MATCH (a:ProcurementAccount {id: $account_id}), (o:Order {id: $entitlement_id})
                MERGE (a)-[:HAS_SUBSCRIPTION]->(o)
                """
                self.driver.execute_query(link_query, account_id=account_id, entitlement_id=entitlement_id)
                
    def activate_user_credentials(self, order_id: str, uri: str, user: str, password: str, database: str, email: str) -> None:
        """Saves DB credentials securely and activates their account."""
        secret_name = self._store_password_in_secret_manager(order_id, password)

        query = """
        MATCH (o:Order {id: $order_id})
        SET 
            o.target_uri = $uri,
            o.target_user = $user,
            o.target_password_secret = $secret_name,
            o.target_database = $database,
            o.admin_email = $email,
            o.status = 'ACTIVE',
            o.is_active = true,
            o.updated_at = datetime()
        """
        self.driver.execute_query(
            query, order_id=order_id, uri=uri, user=user, secret_name=secret_name, database=database, email=email
        )
        
    def get_user_credentials(self, order_id: str) -> dict:
        """
        Retrieves the target Neo4j credentials for a specific active customer,
        fetching the password dynamically from Secret Manager.
        """
        query = """
        MATCH (o:Order {id: $order_id, is_active: true})
        RETURN o.target_uri AS uri, o.target_user AS user, o.target_password_secret AS secret_name, o.target_database AS database
        """
        try:
            records, _, _ = self.driver.execute_query(query, order_id=order_id)
            if not records:
                return None

            secret_name = records[0]["secret_name"]
            password = self._get_password_from_secret_manager(secret_name) if secret_name else None

            return {
                "uri": records[0]["uri"],
                "user": records[0]["user"],
                "password": password, 
                "database": records[0]["database"]
            }
        except Exception as e:
            logging.error(f"Failed to retrieve target DB credentials for {order_id}: {e}")
            return None
        
    @staticmethod
    def verify_access_token(token: str) -> dict:
        """Validate incoming A2A requests."""
        try:
            return jwt.decode(token, INTERNAL_SECRET_KEY, algorithms=["HS256"])
        except Exception as e:
            raise ValueError(f"Invalid token: {e}")

    def close(self):
        """Closes the database driver connection."""
        logging.info("[token_manager] Closing database driver connection.")
        self.driver.close()
