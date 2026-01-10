# Reference Implementation: Industry Research Agent

This document describes the canonical "Industry Research Agent" that each platform integration should implement. Use this as a consistent pattern across all integrations.

## Overview

The Industry Research Agent is a multi-agent system that helps with investment research by:
1. Querying company data from Neo4j
2. Searching relevant news articles using vector search
3. Analyzing organizational relationships
4. Synthesizing research reports

## Agent Architecture

```
┌──────────────────────────┐
│  Research Coordinator    │
│  (Main Agent)            │
└────────────┬─────────────┘
             │
    ┌────────┴────────┐
    │                 │
┌───▼──────────┐  ┌──▼───────────────┐
│ Database     │  │ Analysis         │
│ Agent        │  │ Agent            │
│              │  │                  │
│ - Query org  │  │ - Synthesize     │
│ - Search     │  │ - Report         │
│   news       │  │ - Insights       │
└──────────────┘  └──────────────────┘
         │
    ┌────▼────┐
    │  Neo4j  │
    │Database │
    └─────────┘
```

## Core Functions

### 1. Query Company Data

Query organizational information including location, industry, and leadership.

**Input:** Company name
**Output:** Organization details, locations, industries, leadership

```python
def query_company(company_name: str) -> dict:
    """
    Query company information from Neo4j.

    Returns:
        {
            'name': str,
            'locations': [str],
            'industries': [str],
            'leadership': [{'name': str, 'title': str}]
        }
    """
    query = """
    MATCH (o:Organization {name: $company})
    RETURN o.name as name,
           [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
           [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
           [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
    LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        database_="companies"
    )
    return records[0].data() if records else {}
```

### 2. Search News Articles

Perform vector similarity search over news articles mentioning the company.

**Input:** Company name, search query, limit
**Output:** Relevant article chunks with similarity scores

```python
def search_news(company_name: str, query: str, limit: int = 5) -> list:
    """
    Vector search for news articles about a company.

    Returns:
        [
            {
                'title': str,
                'date': str,
                'text': str,
                'score': float
            }
        ]
    """
    query_cypher = """
    MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
    MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
    CALL db.index.vector.queryNodes('news', $limit, $embedding)
    YIELD node, score
    WHERE node = c
    RETURN a.title as title,
           a.date as date,
           c.text as text,
           score
    ORDER BY score DESC
    """
    # Generate embedding from query
    embedding = embed_query(query)

    records, summary, keys = driver.execute_query(
        query_cypher,
        company=company_name,
        limit=limit,
        embedding=embedding,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 3. Analyze Organizational Relationships

Explore relationships between organizations (subsidiaries, partnerships, competitors).

**Input:** Company name, relationship types
**Output:** Connected organizations with relationship types

```python
def analyze_relationships(company_name: str, max_depth: int = 2) -> list:
    """
    Find related organizations through graph traversal.

    Returns:
        [
            {
                'organization': str,
                'relationships': [str],
                'distance': int
            }
        ]
    """
    query = """
    MATCH path = (o1:Organization {name: $company})
                 -[*1..$depth]-(o2:Organization)
    WHERE o1 <> o2
    RETURN DISTINCT o2.name as organization,
           [r in relationships(path) | type(r)] as relationships,
           length(path) as distance
    ORDER BY distance
    LIMIT 20
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        depth=max_depth,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 4. Synthesize Research Report

Combine data from multiple sources into a coherent investment research report.

**Input:** Company data, news analysis, relationships
**Output:** Formatted research report

```python
def synthesize_report(
    company_data: dict,
    news_articles: list,
    relationships: list
) -> str:
    """
    Generate investment research report using LLM.

    Returns formatted markdown report with:
    - Executive Summary
    - Company Overview
    - Recent Developments
    - Organizational Network
    - Risk Factors
    - Investment Outlook
    """
    prompt = f"""
    Generate an investment research report for {company_data['name']}.

    Company Information:
    - Locations: {', '.join(company_data['locations'])}
    - Industries: {', '.join(company_data['industries'])}
    - Leadership: {len(company_data['leadership'])} key executives

    Recent News ({len(news_articles)} articles):
    {format_news_summary(news_articles)}

    Organizational Network:
    {format_relationships(relationships)}

    Provide: Executive summary, key developments, risks, and outlook.
    """
    # Call LLM and return formatted report
```

## Example Workflow

### Single-Agent Pattern

For simpler frameworks, implement as a single agent with multiple tools:

```python
# Define tools
tools = [
    query_company,
    search_news,
    analyze_relationships
]

# Create agent
agent = create_agent(
    name="investment_research",
    tools=tools,
    instructions="""
    You are an investment research analyst.
    Use the available tools to research companies and generate reports.

    Workflow:
    1. Query company data
    2. Search recent news
    3. Analyze organizational relationships
    4. Synthesize findings into a report
    """
)

# Execute
result = agent.run("Research Google's recent activities")
```

### Multi-Agent Pattern

For platforms supporting multi-agent orchestration:

```python
# Database Agent - handles all Neo4j queries
database_agent = Agent(
    name="database_agent",
    tools=[query_company, search_news, analyze_relationships],
    instructions="You query Neo4j for company and news data."
)

# Analysis Agent - synthesizes information
analyst_agent = Agent(
    name="analyst",
    tools=[],
    instructions="""
    You are an investment analyst.
    Synthesize data into insights and reports.
    """
)

# Coordinator - orchestrates workflow
coordinator = Agent(
    name="coordinator",
    agents=[database_agent, analyst_agent],
    instructions="""
    Coordinate research tasks:
    1. Use database_agent to gather data
    2. Use analyst to synthesize report
    """
)

# Execute
result = coordinator.run("Research Google")
```

## Implementation Checklist

When implementing for a platform, ensure you:

- [ ] Connect to demo database (neo4j+s://demo.neo4jlabs.com:7687)
- [ ] Implement `query_company` function/tool
- [ ] Implement `search_news` with vector search
- [ ] Implement `analyze_relationships` (optional but recommended)
- [ ] Create agent(s) with appropriate instructions
- [ ] Handle authentication (API keys, OAuth, etc.)
- [ ] Test with example companies ("Google", "Microsoft", "Tesla")
- [ ] Document any platform-specific adaptations
- [ ] Note challenges or limitations encountered

## Test Queries

Use these to verify your implementation:

**Basic query:**
```
"Get information about Google"
```

**Research query:**
```
"Research recent developments at Microsoft, including news and partnerships"
```

**Analysis query:**
```
"Analyze Tesla's organizational network and recent news coverage"
```

**Complex query:**
```
"Compare the recent activities of Google and Microsoft, focusing on AI initiatives"
```

## Expected Output

A complete research report should include:

```markdown
# Investment Research Report: [Company Name]

## Executive Summary
[2-3 sentence overview of findings]

## Company Overview
- Headquarters: [Location]
- Industries: [Industry sectors]
- Key Leadership: [Names and titles]

## Recent Developments
[Summary of recent news based on vector search]

1. [News item 1]
2. [News item 2]
3. [News item 3]

## Organizational Network
[Key relationships and partnerships identified]

## Risk Factors
[Identified risks from news analysis]

## Investment Outlook
[Synthesis and recommendation]

---
*Generated by [Platform Name] + Neo4j*
```

## Database Schema Reference

Quick reference for the data model:

**Organizations:**
- Properties: `name`, `description`, `website`
- Outgoing: `[:LOCATED_IN]->(:Location)`
- Outgoing: `[:IN_INDUSTRY]->(:Industry)`
- Incoming: `[:WORKS_FOR]-(:Person)`
- Incoming: `[:MENTIONS]-(:Article)`

**Articles:**
- Properties: `title`, `date`, `url`
- Outgoing: `[:MENTIONS]->(:Organization)`
- Outgoing: `[:HAS_CHUNK]->(:Chunk)`

**Chunks:**
- Properties: `text`, `embedding` (vector)
- Vector index: `news`
- Incoming: `[:HAS_CHUNK]-(:Article)`

**People:**
- Properties: `name`, `title`
- Outgoing: `[:WORKS_FOR]->(:Organization)`

## Platform-Specific Notes

When implementing for different platforms:

### For MCP-based platforms
- Use Neo4j MCP server's pre-built tools
- Configure authentication in MCP client setup
- May not need custom query functions

### For direct integration platforms
- Implement functions as native platform tools
- Handle Neo4j driver connection pooling
- May need to adapt query syntax

### For low-code platforms
- Define queries as reusable components/nodes
- Use visual workflow for agent coordination
- Document node configuration requirements

### For cloud platforms
- Store credentials in platform secret manager
- Deploy query functions as cloud functions
- Consider connection latency and timeouts

## Variations and Extensions

Feel free to extend the reference implementation with:

- **Financial data integration**: Add stock prices, financials
- **Competitive analysis**: Compare multiple companies
- **Trend analysis**: Track topics over time
- **Alert system**: Monitor for specific events
- **Multi-language support**: Non-English news sources
- **Custom embeddings**: Domain-specific embedding models

The core pattern remains the same: query structured data, search unstructured content, synthesize insights.
