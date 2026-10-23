"""Standalone embedding call shared by the retrieval tools and ingestion.

This module must not import neo4j-graphrag. The tools import it directly, and it
ships with them into watsonx Orchestrate.

Each provider's SDK is imported inside that provider's branch, so a deployment
only needs the SDK of the provider it uses. Phase 4 adds a ``watsonx`` branch.
"""

from functools import lru_cache
from typing import Any


def embed(text: str, config: dict[str, str]) -> list[float]:
    """Embed one piece of text with the configured provider.

    Args:
        text: The text to embed.
        config: Provider settings with the keys ``provider``, ``model``, and
            ``api_key``. Passed in rather than read from the environment, so
            Orchestrate can supply them from a connection.

    Returns:
        The embedding vector.

    Raises:
        ValueError: If the provider is not supported.
    """
    match config["provider"]:
        case "openai":
            client = _openai_client(config["api_key"])
            response = client.embeddings.create(model=config["model"], input=text)
            return response.data[0].embedding
        case provider:
            raise ValueError(f"Unsupported embedding provider: {provider!r}")


@lru_cache(maxsize=4)
def _openai_client(api_key: str) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key)
