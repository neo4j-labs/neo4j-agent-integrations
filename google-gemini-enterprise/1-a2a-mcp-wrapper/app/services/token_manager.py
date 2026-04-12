"""Manages token usage and daily limits for users."""
import logging
from datetime import date
from neo4j import GraphDatabase
from ..core.config import (
    TRACKING_NEO4J_URI,
    TRACKING_NEO4J_USER,
    TRACKING_NEO4J_PASS,
    DAILY_TOKEN_LIMIT,
)

class TokenManager:
    def __init__(self):
        """Initializes the TokenManager with database credentials."""
        self.driver = GraphDatabase.driver(
            TRACKING_NEO4J_URI, auth=(TRACKING_NEO4J_USER, TRACKING_NEO4J_PASS)
        )
        self.default_daily_limit = int(DAILY_TOKEN_LIMIT)

    def check_limit(self, user_id: str) -> bool:
        """
        Checks if the user has exceeded their specific daily token limit.
        Resets the limit if it's a new day and enforces the is_active flag.
        """
        logging.info(f"Checking token limit for user: {user_id}")
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
                return True 

            record = records[0]
            tokens_used = record["used"]
            user_limit = record["user_limit"]
            is_active = record["is_active"]

            if not is_active:
                logging.warning(f"Blocked request: User {user_id} is marked as inactive.")
                return False

            logging.info(f"User {user_id} has used {tokens_used}/{user_limit} tokens today.")
            return tokens_used < user_limit

        except Exception as e:
            logging.error(f"Failed to check token limit for user {user_id}: {e}")
            return False

    def add_tokens(self, user_id: str, tokens: int):
        """Adds the used tokens to the user's daily total and updates the timestamp."""
        if tokens <= 0:
            return

        logging.info(f"Adding {tokens} tokens to user {user_id}'s daily total.")

        query = """
        MATCH (u:User {id: $user_id})
        SET u.tokens_used_today = u.tokens_used_today + $tokens,
            u.updated_at = datetime()
        """
        try:
            self.driver.execute_query(query, user_id=user_id, tokens=tokens)
            logging.info(f"Successfully added {tokens} tokens for user {user_id}.")
        except Exception as e:
            logging.error(f"Failed to update token usage for user {user_id}: {e}")

    def close(self):
        """Closes the database driver connection."""
        self.driver.close()