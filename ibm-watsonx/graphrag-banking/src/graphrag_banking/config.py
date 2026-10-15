"""Settings and shared helpers, loaded from the project's .env file."""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
GENERATED_DIR = DATA_DIR / "generated"
POLICY_TEMPLATES_DIR = DATA_DIR / "policy_templates"
POLICIES_DIR = DATA_DIR / "policies"
POLICY_FACTS_PATH = DATA_DIR / "policy_facts.yaml"
HERO_FIXTURES_PATH = DATA_DIR / "hero_fixtures.yaml"
PROMPTS_DIR = PROJECT_ROOT / "prompts"
EVAL_DIR = PROJECT_ROOT / "eval"


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Missing credentials are empty strings until used."""

    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    openai_api_key: str
    # Shared by the agent and the local baseline, so beat 1 is a fair comparison.
    chat_model: str
    embedding_model: str
    demo_as_of: date
    demo_customer_id: str
    data_seed: int

    @property
    def embedding_config(self) -> dict[str, str]:
        """Settings passed to embeddings.embed(text, config)."""
        return {
            "provider": "openai",
            "model": self.embedding_model,
            "api_key": _require(self.openai_api_key, "OPENAI_API_KEY"),
        }


def load_settings() -> Settings:
    """Read settings from the environment, after loading the project .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        neo4j_uri=os.environ.get("NEO4J_URI", ""),
        neo4j_username=os.environ.get("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", ""),
        neo4j_database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        chat_model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-5.6-terra"),
        embedding_model=os.environ.get(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        ),
        demo_as_of=date.fromisoformat(os.environ.get("DEMO_AS_OF", "2026-10-08")),
        demo_customer_id=os.environ.get("DEMO_CUSTOMER_ID", "C-1001"),
        data_seed=int(os.environ.get("DATA_SEED", "42")),
    )


def get_driver(settings: Settings) -> Driver:
    """Open a Neo4j driver. Use it as a context manager and pass
    ``database_=settings.neo4j_database`` to ``execute_query``."""
    return GraphDatabase.driver(
        _require(settings.neo4j_uri, "NEO4J_URI"),
        auth=(
            settings.neo4j_username,
            _require(settings.neo4j_password, "NEO4J_PASSWORD"),
        ),
    )


def _require(value: str, name: str) -> str:
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy env.sample to .env and fill it in."
        )
    return value
