"""neo4j-graphrag model classes for ingestion and the local baseline.

The ``Embedder`` wraps ``embeddings.embed``, so chunks written at ingestion and
questions embedded by the tools always use the same model. Phase 4 adds a
``WatsonxLLM`` here for the local baseline.
"""

from neo4j_graphrag.embeddings.base import Embedder

from graphrag_banking.embeddings import embed


class SharedEmbedder(Embedder):
    """neo4j-graphrag ``Embedder`` backed by the shared ``embed`` function.

    Args:
        config: Provider settings with the keys ``provider``, ``model``, and
            ``api_key``.
    """

    def __init__(self, config: dict[str, str]) -> None:
        super().__init__()
        self._config = config

    def embed_query(self, text: str) -> list[float]:
        return embed(text, self._config)
