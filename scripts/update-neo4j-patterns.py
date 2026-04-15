#!/usr/bin/env python3
"""
Update Neo4j code patterns across all README files.
Changes:
1. driver.session() -> driver.execute_query()
2. OPTIONAL MATCH + collect -> pattern comprehensions
3. Parameter $name -> $company
"""

import re
from pathlib import Path

def update_session_to_execute_query(content: str) -> str:
    """Replace session context managers with execute_query."""

    # Pattern 1: with driver.session(...) as session: session.run(...)
    pattern1 = r'with driver\.session\((.*?)\) as session:\s*\n\s*result = session\.run\((.*?)\)'

    def replace1(match):
        db_param = match.group(1)
        query_params = match.group(2)

        # Extract database parameter if it exists
        db_match = re.search(r'database[_]?=["\'](.*?)["\']', db_param)
        db_name = db_match.group(1) if db_match else "companies"

        return f'records, summary, keys = driver.execute_query(\n        {query_params},\n        database_="{db_name}"\n    )'

    content = re.sub(pattern1, replace1, content, flags=re.DOTALL)

    return content

def update_optional_match_to_pattern_comp(content: str) -> str:
    """Replace OPTIONAL MATCH + collect with pattern comprehensions."""

    # Common pattern: OPTIONAL MATCH (o)-[:REL]->(target) ... collect(target.prop)
    replacements = [
        # Locations
        (
            r'OPTIONAL MATCH \(o\)-\[:LOCATED_IN\]->\(loc:?Location?\)\s*\n\s*RETURN.*?collect\(DISTINCT loc\.name\) as locations',
            lambda m: m.group(0).replace(
                'OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc:Location)',
                ''
            ).replace(
                'collect(DISTINCT loc.name) as locations',
                '[(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations'
            )
        ),
        # Industries
        (
            r'OPTIONAL MATCH \(o\)-\[:IN_INDUSTRY\]->\(ind:?Industry?\)\s*\n\s*RETURN.*?collect\(DISTINCT ind\.name\) as industries',
            lambda m: m.group(0).replace(
                'OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind:Industry)',
                ''
            ).replace(
                'collect(DISTINCT ind.name) as industries',
                '[(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries'
            )
        ),
        # Leadership/People
        (
            r'OPTIONAL MATCH \(p:?Person?\)-\[:WORKS_FOR\]->\(o\)\s*\n\s*RETURN.*?collect\(\{name: p\.name, title: p\.title\}\) as leadership',
            lambda m: m.group(0).replace(
                'OPTIONAL MATCH (p:Person)-[:WORKS_FOR]->(o)',
                ''
            ).replace(
                'collect({name: p.name, title: p.title}) as leadership',
                '[(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership'
            )
        ),
    ]

    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content, flags=re.DOTALL | re.IGNORECASE)

    return content

def update_parameter_names(content: str) -> str:
    """Change parameter from $name to $company for organization queries."""

    # Replace $name with $company in organization queries
    content = re.sub(
        r'\{name: \$name\}',
        '{name: $company}',
        content
    )

    # Replace name=... parameter with company=...
    content = re.sub(
        r'(\s+)name=([a-zA-Z_]+)',
        r'\1company=\2',
        content
    )

    # Replace params={"name": with params={"company":
    content = re.sub(
        r'params=\{["\']name["\']:',
        'params={"company":',
        content
    )

    return content

def process_file(filepath: Path) -> bool:
    """Process a single README file."""
    try:
        content = filepath.read_text(encoding='utf-8')
        original = content

        # Apply transformations
        content = update_session_to_execute_query(content)
        content = update_optional_match_to_pattern_comp(content)
        content = update_parameter_names(content)

        if content != original:
            filepath.write_text(content, encoding='utf-8')
            print(f"✓ Updated {filepath}")
            return True
        else:
            print(f"  No changes needed: {filepath.name}")
            return False

    except Exception as e:
        print(f"✗ Error processing {filepath}: {e}")
        return False

def main():
    """Main function."""
    repo_root = Path(__file__).parent.parent

    # Find all README files
    readme_files = list(repo_root.glob('**/README.md'))

    print(f"Found {len(readme_files)} README files")
    print("=" * 80)

    updated_count = 0
    for readme_file in sorted(readme_files):
        if process_file(readme_file):
            updated_count += 1

    print("=" * 80)
    print(f"Updated {updated_count} files")

if __name__ == '__main__':
    main()
