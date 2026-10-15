"""Verify that the configured Neo4j Aura instance is reachable."""

from graphrag_banking.config import get_driver, load_settings


def main() -> None:
    settings = load_settings()
    with get_driver(settings) as driver:
        driver.verify_connectivity()
        records, _, _ = driver.execute_query(
            "RETURN 1 AS ok", database_=settings.neo4j_database
        )
    print(f"Connected to {settings.neo4j_uri}, RETURN 1 -> {records[0]['ok']}")


if __name__ == "__main__":
    main()
