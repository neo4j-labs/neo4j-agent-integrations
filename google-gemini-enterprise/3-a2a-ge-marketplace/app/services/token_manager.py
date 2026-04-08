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

        # 1. Create the secret container
        try:
            secret = self.secret_client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}}
                }
            )
            secret_name = secret.name
        except AlreadyExists:
            secret_name = f"{parent}/secrets/{secret_id}"

        payload = password.encode("UTF-8")
        self.secret_client.add_secret_version(
            request={
                "parent": secret_name,
                "payload": {"data": payload}
            }
        )

        logging.info("[token_manager] Saved password to Secret Manager")
        return secret_name

    def _get_password_from_secret_manager(self, secret_name: str) -> str:
        """Retrieves the latest version of a secret from GCP."""
        name = f"{secret_name}/versions/latest"
        response = self.secret_client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    # ==========================================
    # 1. LLM TOKEN TRACKING LOGIC
    # ==========================================

    def check_limit(self, user_id: str) -> bool:
        """
        Checks if the user has exceeded their specific daily token limit.
        Resets the limit if it's a new day and enforces the is_active flag.
        """
        logging.info(f"[token_manager] Checking token limit for user: {user_id}")
        today = date.today().isoformat()

        query = """
        MERGE (u:User {id: $user_id})
        ON CREATE SET
            u.tokens_used_today = 0,
            u.last_reset_date = $today,
            u.daily_token_limit = $default_limit,
            u.is_active = true,
            u.created_at = datetime(),
            u.updated_at = datetime()
        WITH u
        SET u.tokens_used_today = CASE WHEN u.last_reset_date <> $today THEN 0 ELSE u.tokens_used_today END,
            u.last_reset_date = $today,
            u.last_seen_at = datetime()
        RETURN
            u.tokens_used_today AS used,
            u.daily_token_limit AS user_limit,
            u.is_active AS is_active
        """
        try:
            records, _, _ = self.driver.execute_query(
                query,
                user_id=user_id,
                today=today,
                default_limit=self.default_daily_limit
            )
            if not records:
                logging.info(f"[token_manager] No record found for user {user_id}, creating new one.")
                return True
            record = records[0]
            logging.info(f"[token_manager] User {user_id} record: {record}")
            if not record["is_active"]:
                logging.warning(f"[token_manager] Blocked request: User {user_id} is inactive.")
                return False
            
            limit_ok = record["used"] < record["user_limit"]
            logging.info(f"[token_manager] User {user_id} token limit check: {limit_ok}")
            return limit_ok
        except Exception as e:
            logging.error(f"[token_manager] Failed to check token limit for user {user_id}: {e}")
            return False

    def add_tokens(self, user_id: str, tokens: int):
        """Adds the used tokens to the user's daily total and updates the timestamp."""
        if tokens <= 0: return
        logging.info(f"[token_manager] Adding {tokens} tokens for user: {user_id}")
        query = """
        MATCH (u:User {id: $user_id})
        SET u.tokens_used_today = u.tokens_used_today + $tokens,
            u.updated_at = datetime()
        """
        try:
            self.driver.execute_query(query, user_id=user_id, tokens=tokens)
            logging.info(f"[token_manager] Successfully updated token usage for user {user_id}")
        except Exception as e:
            logging.error(f"[token_manager] Failed to update token usage for user {user_id}: {e}")

    # ==========================================
    # 2. NEW OAUTH 2.0 MANAGEMENT LOGIC
    # ==========================================

    def hash_secret(self, secret_string: str) -> str:
        """Creates a secure SHA-256 hash of a machine-generated secret."""
        return hashlib.sha256(secret_string.encode('utf-8')).hexdigest()

    def register_new_client(self, order_id: str) -> dict:
        """
        Called by DCR. Generates and stores HASHED credentials for a Marketplace order.
        If the order already exists, this rotates the credentials.
        """
        logging.info(f"[token_manager] Registering/Rotating client for order_id: {order_id}")

        new_client_id = f"client_{uuid.uuid4().hex[:12]}"
        new_client_secret = uuid.uuid4().hex

        hashed_secret = self.hash_secret(new_client_secret)

        query = """
        MERGE (c:OAuthClient {order_id: $order_id})
        SET 
            c.client_id = $new_client_id, 
            c.client_secret_hash = $hashed_secret, 
            c.updated_at = datetime()
        RETURN c.client_id AS client_id
        """
        try:
            self.driver.execute_query(
                query, 
                order_id=order_id,
                new_client_id=new_client_id,
                hashed_secret=hashed_secret
            )

            logging.info(f"[token_manager] DCR Client credentials hashed and stored for order: {order_id}.")

            return {
                "client_id": new_client_id, 
                "client_secret": new_client_secret
            }

        except Exception as e:
            logging.error(f"[token_manager] Failed to register OAuth client for order {order_id}: {e}")
            raise Exception("Database error during client registration")
        

    def generate_auth_code(self, client_id: str) -> str:
        """Generates a temporary code, stores its HASH, and returns the plain text."""
        logging.info(f"[token_manager] Generating auth code for client_id: {client_id}")

        plain_code = f"code_{uuid.uuid4().hex}"

        hashed_code = self.hash_secret(plain_code)

        query = """
        CREATE (a:AuthCode {
            code_hash: $hashed_code, 
            client_id: $client_id, 
            created_at: datetime()
        })
        """
        try:
            self.driver.execute_query(query, hashed_code=hashed_code, client_id=client_id)
            logging.info(f"[token_manager] Successfully stored hashed auth code for client_id: {client_id}")
            return plain_code 
        except Exception as e:
            logging.error(f"[token_manager] Failed to save auth code for client_id {client_id}: {e}")
            raise Exception("Database error during authorization")

    def exchange_code_for_token(self, client_id: str, client_secret: str, code: str) -> tuple[str, str]:
        """Validates hashed credentials, deletes the code, and issues a JWT."""
        logging.info(f"[token_manager] Exchanging auth code for token for client_id: {client_id}")

        hashed_secret = self.hash_secret(client_secret)
        hashed_code = self.hash_secret(code)

        query = """
        MATCH (c:OAuthClient {client_id: $client_id, client_secret_hash: $hashed_secret})
        MATCH (a:AuthCode {code_hash: $hashed_code, client_id: $client_id})
        WITH c, a
        DELETE a  
        RETURN c.order_id AS order_id
        """
        try:
            records, _, _ = self.driver.execute_query(
                query, 
                client_id=client_id, 
                hashed_secret=hashed_secret, 
                hashed_code=hashed_code
            )

            if not records:
                logging.warning(f"[token_manager] Invalid credentials or auth code for client_id: {client_id}")
                raise ValueError("Invalid client credentials or authorization code")

            order_id = records[0]["order_id"]

            payload = {
                "sub": client_id,
                "order_id": order_id,
                "exp": time.time() + 3600 
            }
            token = jwt.encode(payload, INTERNAL_SECRET_KEY, algorithm="HS256")
            return token, order_id

        except Exception as e:
            logging.error(f"[token_manager] Token exchange failed for client_id {client_id}: {e}")
            raise
        
    def store_refresh_token(self, client_id: str, order_id: str, refresh_token: str) -> None:
        """Hashes and stores the refresh token in Neo4j."""

        hashed_refresh = self.hash_secret(refresh_token)

        query = """
        MATCH (c:OAuthClient {client_id: $client_id, order_id: $order_id})
        SET c.refresh_token_hash = $hashed_refresh, c.updated_at = datetime()
        """
        try:
            self.driver.execute_query(
                query,
                client_id=client_id,
                order_id=order_id,
                hashed_refresh=hashed_refresh
            )
            logging.info(f"[token_manager] Hashed and stored refresh token for client_id: {client_id}")
        except Exception as e:
            logging.error(f"[token_manager] Failed to store refresh token for {client_id}: {e}")
            raise

    def refresh_access_token(self, client_id: str, client_secret: str, refresh_token: str) -> str:
        """Validates the refresh token and issues a new JWT access token."""
        logging.info(f"[token_manager] Validating refresh token for client_id: {client_id}")
        hashed_client_secret = hashlib.sha256(client_secret.encode('utf-8')).hexdigest()
        hashed_refresh_token = hashlib.sha256(refresh_token.encode('utf-8')).hexdigest()
        
        query = """
        MATCH (c:OAuthClient {
            client_id: $client_id, 
            client_secret_hash: $hashed_secret, 
            refresh_token_hash: $hashed_refresh
        })
        RETURN c.order_id AS order_id
        """
        try:
            records, _, _ = self.driver.execute_query(
                query,
                client_id=client_id,
                hashed_secret=hashed_client_secret,
                hashed_refresh=hashed_refresh_token
            )
            if not records:
                logging.warning(f"[token_manager] Security Alert: Invalid refresh token attempt for client_id: {client_id}")
                raise ValueError("Invalid refresh token or client credentials")

            order_id = records[0]["order_id"]
            logging.info(f"[token_manager] Successfully validated refresh token. Restored order_id: {order_id}")

            payload = {
                "sub": client_id,
                "order_id": order_id,
                "exp": time.time() + 3600
            }
            new_token = jwt.encode(payload, INTERNAL_SECRET_KEY, algorithm="HS256")
            logging.info(f"[token_manager] Issued NEW JWT token for client_id: {client_id}")
            return new_token

        except Exception as e:
            logging.error(f"[token_manager] Refresh token exchange failed for client_id {client_id}: {e}")
            raise
        
    def handle_marketplace_event(self, event_type: str, account_id: str = None, entitlement_id: str = None) -> None:
        """Handles lifecycle events from GCP."""

        if account_id:
            account_query = """
            MERGE (a:ProcurementAccount {id: $account_id})
            SET a.last_event = $event_type, a.updated_at = datetime()
            """
            try:
                self.driver.execute_query(account_query, account_id=account_id, event_type=event_type)
            except Exception as e:
                logging.error(f"Failed to merge Account {account_id}: {e}")
                raise


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
            MERGE (u:User {id: $entitlement_id})
            ON CREATE SET 
                u.created_at = datetime(),
                u.tokens_used_today = 0,
                u.daily_token_limit = $default_limit,
                u.status = $new_status,
                u.is_active = CASE WHEN $new_status = 'ACTIVE' THEN true ELSE false END
            ON MATCH SET 
                u.status = $new_status,
                u.is_active = CASE WHEN $new_status = 'ACTIVE' THEN true ELSE false END,
                u.updated_at = datetime()
            """
            try:
                self.driver.execute_query(entitlement_query, entitlement_id=entitlement_id, new_status=new_status, default_limit=self.default_daily_limit)

                if account_id:
                    link_query = """
                    MATCH (a:ProcurementAccount {id: $account_id}), (u:User {id: $entitlement_id})
                    MERGE (a)-[:HAS_SUBSCRIPTION]->(u)
                    """
                    self.driver.execute_query(link_query, account_id=account_id, entitlement_id=entitlement_id)

                logging.info(f"Entitlement Processed: {entitlement_id} is now {new_status}")
            except Exception as e:
                logging.error(f"Failed to process Entitlement {entitlement_id}: {e}")
                raise
                
    def activate_user_credentials(self, order_id: str, uri: str, user: str, password: str, database: str, email: str) -> None:
        """Saves DB credentials securely and activates their account."""
        secret_name = self._store_password_in_secret_manager(order_id, password)

        query = """
        MATCH (u:User {id: $order_id})
        SET 
            u.target_uri = $uri,
            u.target_user = $user,
            u.target_password_secret = $secret_name,
            u.target_database = $database,
            u.admin_email = $email,
            u.status = 'ACTIVE',
            u.is_active = true,
            u.updated_at = datetime()
        RETURN u
        """
        try:
            records, _, _ = self.driver.execute_query(
                query, 
                order_id=order_id, 
                uri=uri, 
                user=user, 
                secret_name=secret_name,
                database=database,
                email=email
            )
            if not records:
                raise ValueError("Activation failed: Order ID not found or Procurement Account ID mismatch.")
            logging.info(f"Order {order_id} successfully configured and ACTIVATED.")
        except Exception as e:
            logging.error(f"Failed to activate user {order_id}: {e}")
            raise
        
    def get_user_credentials(self, order_id: str) -> dict:
        """
        Retrieves the target Neo4j credentials for a specific active customer,
        fetching the password dynamically from Secret Manager.
        """
        query = """
        MATCH (u:User {id: $order_id, is_active: true})
        RETURN u.target_uri AS uri, u.target_user AS user, u.target_password_secret AS secret_name, u.target_database AS database
        """
        try:
            records, _, _ = self.driver.execute_query(query, order_id=order_id)
            if not records:
                return None

            secret_name = records[0]["secret_name"]

            if secret_name:
                password = self._get_password_from_secret_manager(secret_name)
            else:
                password = None

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
        """Called by Middleware to validate incoming A2A requests."""
        logging.info("[token_manager] Verifying access token")
        try:
            payload = jwt.decode(token, INTERNAL_SECRET_KEY, algorithms=["HS256"])
            logging.info(f"[token_manager] Access token verified successfully. Payload: {payload}")
            return payload
        except jwt.ExpiredSignatureError as e:
            logging.warning(f"[token_manager] Access token expired: {e}")
            raise ValueError("Token expired")
        except jwt.InvalidTokenError as e:
            logging.warning(f"[token_manager] Invalid access token: {e}")
            raise ValueError("Invalid token")

    def close(self):
        """Closes the database driver connection."""
        logging.info("[token_manager] Closing database driver connection.")
        self.driver.close()