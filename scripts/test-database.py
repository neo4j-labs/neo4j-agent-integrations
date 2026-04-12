#!/usr/bin/env python3
"""
Test connection to the demo Neo4j database and validate queries.
"""

from neo4j import GraphDatabase
import sys

# Demo database credentials
NEO4J_URI = "neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_USERNAME = "companies"
NEO4J_PASSWORD = "companies"
NEO4J_DATABASE = "companies"

def test_connection():
    """Test basic connection to the database."""
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("✓ Connected to Neo4j database successfully")
        return driver
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)

def check_schema(driver):
    """Check the database schema."""
    print("\n" + "=" * 80)
    print("DATABASE SCHEMA")
    print("=" * 80)

    # Check node labels
    records, summary, keys = driver.execute_query(
        "CALL db.labels() YIELD label RETURN label ORDER BY label",
        database_=NEO4J_DATABASE
    )
    print(f"\nNode Labels ({len(records)}):")
    for record in records:
        print(f"  - {record['label']}")

    # Check relationship types
    records, summary, keys = driver.execute_query(
        "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType",
        database_=NEO4J_DATABASE
    )
    print(f"\nRelationship Types ({len(records)}):")
    for record in records:
        print(f"  - {record['relationshipType']}")

    # Check node counts
    records, summary, keys = driver.execute_query(
        """
        CALL db.labels() YIELD label
        CALL {
            WITH label
            MATCH (n) WHERE label IN labels(n)
            RETURN count(n) as count
        }
        RETURN label, count
        ORDER BY count DESC
        """,
        database_=NEO4J_DATABASE
    )
    print(f"\nNode Counts:")
    for record in records:
        print(f"  {record['label']}: {record['count']:,}")

def test_company_query(driver):
    """Test querying company data."""
    print("\n" + "=" * 80)
    print("TESTING COMPANY QUERY")
    print("=" * 80)

    # First, find some actual company names
    records, summary, keys = driver.execute_query(
        "MATCH (o:Organization) RETURN o.name as name LIMIT 10",
        database_=NEO4J_DATABASE
    )

    if not records:
        print("✗ No organizations found in database")
        return

    print("\nSample organizations:")
    for record in records:
        print(f"  - {record['name']}")

    # Test the pattern comprehension query
    test_company = records[0]['name']
    print(f"\n\nTesting query for: {test_company}")

    query = """
    MATCH (o:Organization {name: $name})
    RETURN o.name as name,
           [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
           [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
           [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
    LIMIT 1
    """

    records, summary, keys = driver.execute_query(
        query,
        name=test_company,
        database_=NEO4J_DATABASE
    )

    if records:
        print(f"✓ Query successful")
        result = records[0]
        print(f"  Name: {result['name']}")
        print(f"  Locations: {result['locations'][:3]}")
        print(f"  Industries: {result['industries'][:3]}")
        print(f"  Leadership: {len(result['leadership'])} people")
    else:
        print(f"✗ Query returned no results")

def test_article_query(driver):
    """Test querying articles."""
    print("\n" + "=" * 80)
    print("TESTING ARTICLE QUERY")
    print("=" * 80)

    # Check if Article nodes exist
    records, summary, keys = driver.execute_query(
        "MATCH (a:Article) RETURN count(a) as count",
        database_=NEO4J_DATABASE
    )

    article_count = records[0]['count'] if records else 0
    print(f"Total articles in database: {article_count:,}")

    if article_count == 0:
        print("⚠ No articles found - news search queries may not work")
        return

    # Test article query with a company
    records, summary, keys = driver.execute_query(
        """
        MATCH (o:Organization)
        WHERE exists((o)<-[:MENTIONS]-(:Article))
        RETURN o.name as name
        LIMIT 1
        """,
        database_=NEO4J_DATABASE
    )

    if not records:
        print("✗ No organizations with articles found")
        return

    test_company = records[0]['name']
    print(f"\nTesting article query for: {test_company}")

    query = """
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
    RETURN a.title as title, a.date as date
    ORDER BY a.date DESC
    LIMIT 5
    """

    records, summary, keys = driver.execute_query(
        query,
        company=test_company,
        database_=NEO4J_DATABASE
    )

    if records:
        print(f"✓ Found {len(records)} articles")
        for record in records[:3]:
            print(f"  - {record['title']}")
    else:
        print(f"✗ No articles found for {test_company}")

def test_vector_index(driver):
    """Check if vector index exists."""
    print("\n" + "=" * 80)
    print("TESTING VECTOR INDEX")
    print("=" * 80)

    # Check for vector indexes
    records, summary, keys = driver.execute_query(
        "SHOW INDEXES YIELD name, type, labelsOrTypes, properties WHERE type = 'VECTOR' RETURN name, labelsOrTypes, properties",
        database_=NEO4J_DATABASE
    )

    if records:
        print(f"✓ Found {len(records)} vector index(es):")
        for record in records:
            print(f"  - {record['name']}: {record['labelsOrTypes']} on {record['properties']}")
    else:
        print("⚠ No vector indexes found - vector search may not be available")

def main():
    """Main test function."""
    print("Neo4j Demo Database Validation")
    print("=" * 80)

    driver = test_connection()

    try:
        check_schema(driver)
        test_company_query(driver)
        test_article_query(driver)
        test_vector_index(driver)

        print("\n" + "=" * 80)
        print("VALIDATION COMPLETE")
        print("=" * 80)

    finally:
        driver.close()

if __name__ == '__main__':
    main()
