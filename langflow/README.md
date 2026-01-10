# Langflow + Neo4j Integration

## Overview

**Langflow** is a low-code agent builder with visual workflows, MCP support (2025), and the ability to export to LangChain/LangGraph code.

**Official Resources:**
- Website: https://www.langflow.org
- Documentation: https://docs.langflow.org/

## Extension Points

### 1. Neo4j Component

Create Neo4j components in visual builder:

```python
from langflow.components import Component
from neo4j import GraphDatabase

class Neo4jQueryComponent(Component):
    display_name = "Neo4j Query"

    def build(self, query: str, company_name: str) -> dict:
        driver = GraphDatabase.driver(
            "neo4j+s://demo.neo4jlabs.com:7687",
            auth=("companies", "companies")
        )
        records, summary, keys = driver.execute_query(
            query,
            company=company_name,
            database_="companies"
        )
        return records[0].data() if records else {}
```

### 2. MCP Support (2025)

Connect to MCP servers as workflow components.

### 3. Export to Code

Build visually, export to LangChain/LangGraph, integrate Neo4j directly.

## MCP Authentication

✅ **Drag-and-drop** - Visual workflows

✅ **MCP** - MCP support (2025)

✅ **Webhook auth** - Various auth methods

## Resources

- **Langflow**: https://docs.langflow.org/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Visual workflow builder
- ✅ MCP support (2025)
- ✅ Export to code
- **Effort Score**: 3/10
- **Impact Score**: 2/10
