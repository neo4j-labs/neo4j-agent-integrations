"""Empty the database: delete all nodes, then drop constraints and indexes.

Every rebuild starts from empty (PRD section 8). ``make rebuild`` runs this
before ``make ingest``.
"""

import logging

import neo4j

from graphrag_banking.config import Settings, get_driver, load_settings

logger = logging.getLogger(__name__)

# CALL { } IN TRANSACTIONS needs an auto-commit transaction, so this runs
# through session.run rather than execute_query.
_DELETE_ALL_NODES = """
MATCH (n)
CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS
"""


def _quote(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _drop_constraints(driver: neo4j.Driver, database: str) -> int:
    records, _, _ = driver.execute_query(
        "SHOW CONSTRAINTS YIELD name", database_=database
    )
    for record in records:
        driver.execute_query(
            f"DROP CONSTRAINT {_quote(record['name'])} IF EXISTS",
            database_=database,
        )
    return len(records)


def _drop_indexes(driver: neo4j.Driver, database: str) -> int:
    # Token lookup indexes back label and relationship type scans, so keep them.
    records, _, _ = driver.execute_query(
        "SHOW INDEXES YIELD name, type WHERE type <> 'LOOKUP' RETURN name",
        database_=database,
    )
    for record in records:
        driver.execute_query(
            f"DROP INDEX {_quote(record['name'])} IF EXISTS", database_=database
        )
    return len(records)


def reset_db(settings: Settings) -> None:
    """Delete all nodes and relationships, then drop constraints and indexes."""
    database = settings.neo4j_database
    with get_driver(settings) as driver:
        with driver.session(database=database) as session:
            session.run(_DELETE_ALL_NODES).consume()
        logger.info("Deleted all nodes")
        # Drop constraints first, since each owns a backing index.
        logger.info("Dropped %d constraints", _drop_constraints(driver, database))
        logger.info("Dropped %d indexes", _drop_indexes(driver, database))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    reset_db(load_settings())
