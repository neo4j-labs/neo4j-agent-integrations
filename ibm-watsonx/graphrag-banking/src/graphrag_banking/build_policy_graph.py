"""Build the document layer: chunk, embed, and write the policy documents.

Runs a neo4j-graphrag ``Pipeline`` over ``data/policies/`` with no entity
extraction, then creates the vector index and links each rule node to its
chunks through ``Chunk.rule_codes``.

Chunks from customer documents also get the ``CustomerChunk`` label, and the
vector index covers only that label. Staff documents stay out of
``search_policies``. Staff tools read their policy text through ``FROM_CHUNK``.

Run after ``load-structured``. Running it twice without ``reset-db`` duplicates
the chunks, so use ``make rebuild``.
"""

import asyncio
import logging
import re
from collections.abc import Iterator
from itertools import pairwise

import neo4j
import yaml
from neo4j_graphrag.components.embedder import TextChunkEmbedder
from neo4j_graphrag.components.kg_writer import Neo4jWriter
from neo4j_graphrag.components.lexical_graph import LexicalGraphBuilder
from neo4j_graphrag.components.text_splitters.base import TextSplitter
from neo4j_graphrag.components.types import DocumentInfo, TextChunk
from neo4j_graphrag.experimental.pipeline import Pipeline
from neo4j_graphrag.indexes import create_vector_index

from graphrag_banking.config import (
    POLICIES_DIR,
    POLICY_FACTS_PATH,
    PROJECT_ROOT,
    Settings,
    get_driver,
    load_settings,
)
from graphrag_banking.models import SharedEmbedder
from graphrag_banking.tools import VECTOR_INDEX_NAME

logger = logging.getLogger(__name__)

_RULE_CODE_LINE = re.compile(r"^Rule code: (\S+)[ \t]*$", re.MULTILINE)
_SECTION_START = re.compile(r"^## ", re.MULTILINE)
_TITLE_LINE = re.compile(r"^# .*$", re.MULTILINE)

CUSTOMER_CHUNK_LABEL = "CustomerChunk"

_LABEL_CUSTOMER_CHUNKS = """
MATCH (c:Chunk)-[:FROM_DOCUMENT]->(:Document {audience: 'customer'})
SET c:CustomerChunk
RETURN count(c) AS chunks
"""

_LINK_RULES_TO_CHUNKS = """
MATCH (c:Chunk)
UNWIND c.rule_codes AS code
MATCH (r {rule_code: code})
WHERE r:FeeRule OR r:HoldRule OR r:ComplianceRule OR r:FraudRule OR r:LendingRule
MERGE (r)-[:FROM_CHUNK]->(c)
RETURN count(*) AS links
"""


class HeadingSplitter(TextSplitter):
    """Split a Markdown policy document into one chunk per ``## `` section.

    Each chunk keeps its section heading so the embedding has context. Text
    before the first section becomes a chunk only if it holds more than the
    ``# `` title line. The section's ``Rule code:`` lines are stored on the
    chunk as a ``rule_codes`` list.
    """

    def iter_chunks(self, text: str) -> Iterator[TextChunk]:
        for index, section in enumerate(_sections(text)):
            yield TextChunk(
                text=section,
                index=index,
                metadata={"rule_codes": _RULE_CODE_LINE.findall(section)},
            )


def _sections(text: str) -> list[str]:
    starts = [match.start() for match in _SECTION_START.finditer(text)]
    bounds = [0, *starts, len(text)]
    parts = [text[start:end].strip() for start, end in pairwise(bounds)]
    preamble, sections = parts[0], parts[1:]
    if _TITLE_LINE.sub("", preamble).strip():
        sections.insert(0, preamble)
    return sections


def _build_pipeline(driver: neo4j.Driver, settings: Settings) -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component(HeadingSplitter(), "splitter")
    pipeline.add_component(
        TextChunkEmbedder(SharedEmbedder(settings.embedding_config)), "embedder"
    )
    pipeline.add_component(LexicalGraphBuilder(), "lexical")
    pipeline.add_component(
        Neo4jWriter(driver, neo4j_database=settings.neo4j_database), "writer"
    )
    pipeline.connect("splitter", "embedder", {"text_chunks": "splitter"})
    pipeline.connect("embedder", "lexical", {"text_chunks": "embedder"})
    pipeline.connect("lexical", "writer", {"graph": "lexical.graph"})
    return pipeline


def _policies() -> list[dict[str, str]]:
    facts = yaml.safe_load(POLICY_FACTS_PATH.read_text())
    return facts["policies"]


async def _write_documents(driver: neo4j.Driver, settings: Settings) -> None:
    pipeline = _build_pipeline(driver, settings)
    for policy in _policies():
        path = POLICIES_DIR / policy["file"]
        document_info = DocumentInfo(
            path=str(path.relative_to(PROJECT_ROOT)),
            metadata={
                "title": policy["name"],
                "policy_id": policy["policy_id"],
                "audience": policy["audience"],
            },
        )
        await pipeline.run(
            {
                "splitter": {"text": path.read_text()},
                "lexical": {"document_info": document_info},
            }
        )
        logger.info("Wrote %s", path.name)


def build_policy_graph(settings: Settings) -> None:
    """Write the document layer, create the vector index, and link rules."""
    with get_driver(settings) as driver:
        asyncio.run(_write_documents(driver, settings))
        records, _, _ = driver.execute_query(
            _LABEL_CUSTOMER_CHUNKS, database_=settings.neo4j_database
        )
        logger.info("Labeled customer chunks: %d", records[0]["chunks"])

        dimensions = len(
            SharedEmbedder(settings.embedding_config).embed_query("dimensions")
        )
        create_vector_index(
            driver,
            name=VECTOR_INDEX_NAME,
            label=CUSTOMER_CHUNK_LABEL,
            embedding_property="embedding",
            dimensions=dimensions,
            similarity_fn="cosine",
            neo4j_database=settings.neo4j_database,
        )
        driver.execute_query(
            "CALL db.awaitIndexes()", database_=settings.neo4j_database
        )

        records, _, _ = driver.execute_query(
            _LINK_RULES_TO_CHUNKS, database_=settings.neo4j_database
        )
        logger.info("Linked rules to chunks: %d links", records[0]["links"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # One line per embedding request and per schema notice drowns out progress.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
    build_policy_graph(load_settings())
