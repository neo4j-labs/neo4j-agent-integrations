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

## Additional Core Functions

These additional tools provide richer data access for comprehensive research:

### 5. List Industries

Query all industry categories in the database.

**Input:** None
**Output:** List of industry names

```python
def list_industries() -> list:
    """
    Get all industry categories.

    Returns:
        [
            {'industry': str}
        ]
    """
    query = """
    MATCH (i:IndustryCategory)
    RETURN i.name as industry
    ORDER BY i.name
    """
    records, summary, keys = driver.execute_query(
        query,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 6. Companies in Industry

Find all companies in a specific industry category.

**Input:** Industry name
**Output:** Company details (id, name, summary)

```python
def companies_in_industry(industry: str) -> list:
    """
    Get companies in a specific industry.

    Excludes subsidiaries, returns only independent companies.

    Returns:
        [
            {
                'company_id': str,
                'name': str,
                'summary': str
            }
        ]
    """
    query = """
    MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
    WHERE NOT EXISTS { (c)<-[:HAS_SUBSIDARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    """
    records, summary, keys = driver.execute_query(
        query,
        industry=industry,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 7. Search Companies

Full-text search across all companies.

**Input:** Search term (partial company name)
**Output:** Matching companies with relevance scores

```python
def search_companies(search: str) -> list:
    """
    Full-text search for companies by name.

    Returns up to 100 results ordered by relevance.

    Returns:
        [
            {
                'company_id': str,
                'name': str,
                'summary': str
            }
        ]
    """
    query = """
    CALL db.index.fulltext.queryNodes('entity', $search, {limit: 100})
    YIELD node as c, score
    WHERE c:Organization
    AND NOT EXISTS { (c)<-[:HAS_SUBSIDARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    ORDER BY score DESC
    """
    records, summary, keys = driver.execute_query(
        query,
        search=search,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 8. Articles in Month

Find articles published within a specific month.

**Input:** Date (yyyy-mm-dd format)
**Output:** Articles from that month with metadata

```python
def articles_in_month(date: str) -> list:
    """
    Get articles published in a specific month.

    Args:
        date: Start date in yyyy-mm-dd format

    Returns:
        [
            {
                'article_id': str,
                'author': str,
                'title': str,
                'date': str,
                'sentiment': float
            }
        ]
    """
    query = """
    MATCH (a:Article)
    WHERE date($date) <= date(a.date) < date($date) + duration('P1M')
    RETURN a.id as article_id,
           a.author as author,
           a.title as title,
           toString(a.date) as date,
           a.sentiment as sentiment
    ORDER BY a.date DESC
    LIMIT 25
    """
    records, summary, keys = driver.execute_query(
        query,
        date=date,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 9. Get Article Details

Retrieve complete article content including all text chunks.

**Input:** Article ID
**Output:** Full article with aggregated content

```python
def get_article(article_id: str) -> dict:
    """
    Get complete article details with full text content.

    Returns:
        {
            'article_id': str,
            'author': str,
            'title': str,
            'date': str,
            'summary': str,
            'site': str,
            'sentiment': float,
            'content': str  # Aggregated from all chunks
        }
    """
    query = """
    MATCH (a:Article)-[:HAS_CHUNK]->(c:Chunk)
    WHERE a.id = $article_id
    WITH a, c ORDER BY id(c) ASC
    WITH a, collect(c.text) as contents
    RETURN a.id as article_id,
           a.author as author,
           a.title as title,
           toString(a.date) as date,
           a.summary as summary,
           a.siteName as site,
           a.sentiment as sentiment,
           apoc.text.join(contents, ' ') as content
    """
    records, summary, keys = driver.execute_query(
        query,
        article_id=article_id,
        database_="companies"
    )
    return records[0].data() if records else {}
```

### 10. Companies in Article

Find all companies mentioned in a specific article.

**Input:** Article ID
**Output:** Companies mentioned (id, name, summary)

```python
def companies_in_article(article_id: str) -> list:
    """
    Get companies mentioned in a specific article.

    Excludes subsidiaries.

    Returns:
        [
            {
                'company_id': str,
                'name': str,
                'summary': str
            }
        ]
    """
    query = """
    MATCH (a:Article)-[:MENTIONS]->(c:Organization)
    WHERE a.id = $article_id
    AND NOT EXISTS { (c)<-[:HAS_SUBSIDARY]-() }
    RETURN c.id as company_id, c.name as name, c.summary as summary
    """
    records, summary, keys = driver.execute_query(
        query,
        article_id=article_id,
        database_="companies"
    )
    return [record.data() for record in records]
```

### 11. People at Company

Find people associated with a specific company and their roles.

**Input:** Company ID
**Output:** People with roles and company details

```python
def people_at_company(company_id: str) -> list:
    """
    Get people associated with a company and their roles.

    Returns:
        [
            {
                'role': str,
                'person_name': str,
                'company_id': str,
                'company_name': str
            }
        ]
    """
    query = """
    MATCH (c:Organization)-[role]-(p:Person)
    WHERE c.id = $company_id
    RETURN replace(type(role), "HAS_", "") as role,
           p.name as person_name,
           c.id as company_id,
           c.name as company_name
    """
    records, summary, keys = driver.execute_query(
        query,
        company_id=company_id,
        database_="companies"
    )
    return [record.data() for record in records]
```

## Graph Algorithm Functions

Use Neo4j Graph Data Science (GDS) library for advanced graph analytics:

### 12. Find Influential Companies (PageRank)

Identify the most influential companies based on their relationships using PageRank algorithm.

**Input:** None (analyzes entire organization network)
**Output:** Top companies by PageRank score

```python
def find_influential_companies(limit: int = 10) -> list:
    """
    Find most influential companies using PageRank algorithm.

    Uses GDS to:
    1. Create in-memory graph projection of organization relationships
    2. Calculate PageRank scores
    3. Return top-ranked companies

    Returns:
        [
            {
                'company_name': str,
                'company_id': str,
                'score': float
            }
        ]
    """
    query = """
    CALL gds.graph.drop('companies', false) YIELD graphName
    WITH count(*) as _

    MATCH (o1:Organization)--(o2:Organization)
    WITH o1, o2, count(*) as freq
    WHERE freq > 1
    WITH gds.graph.project(
        'companies',
        o1,
        o2,
        {
            relationshipProperties: {weight: freq}
        },
        {
            undirectedRelationshipTypes: ['*']
        }
    ) as graph

    CALL gds.pageRank.stream('companies')
    YIELD nodeId, score
    WITH * ORDER BY score DESC LIMIT $limit
    RETURN gds.util.asNode(nodeId).name as company_name,
           gds.util.asNode(nodeId).id as company_id,
           score
    """
    records, summary, keys = driver.execute_query(
        query,
        limit=limit,
        database_="companies"
    )
    return [record.data() for record in records]
```

**Example Output:**

```
Call: find_influential_companies(limit=5)

┌────────────────────────┬──────────────────────────┬────────┐
│ company_name           │ company_id               │ score  │
├────────────────────────┼──────────────────────────┼────────┤
│ Microsoft Corporation  │ EIsFKrN_ZNLSWsvxdQfWutQ  │ 47.69  │
│ Apple                  │ EHb0_0NEcMQyY8b083taTTw  │ 33.04  │
│ IBM                    │ EPdsrDmLiMQCskvBLp_dloQ  │ 18.69  │
│ Oracle                 │ EfHwtIuViMbug8__vI3vlQQ  │ 15.15  │
│ Salesforce             │ ESRC2KU5QOJ6rsk7VEjQRKQ  │ 12.91  │
└────────────────────────┴──────────────────────────┴────────┘
```

**Interpretation:**
- **Higher scores** indicate more influential companies with stronger network positions
- Microsoft (47.69) has the highest influence, indicating extensive organizational connections
- Scores reflect both the number and importance of relationships in the organization network
- Use these scores to contextualize a company's market position and network effects

**Note:** Additional graph algorithms can be added:
- Community detection (Louvain, Label Propagation)
- Similarity (Node Similarity, K-Nearest Neighbors)
- Centrality (Betweenness, Closeness, Degree)
- Path finding (Shortest Path, All Pairs Shortest Path)

For production deployments, consider using Neo4j Aura Graph Analytics for managed graph projections and algorithm execution.

## Example Workflow

### Single-Agent Pattern

For simpler frameworks, implement as a single agent with multiple tools:

```python
# Define core tools
core_tools = [
    query_company,
    search_news,
    analyze_relationships,
    synthesize_report
]

# Additional data access tools
data_tools = [
    list_industries,
    companies_in_industry,
    search_companies,
    articles_in_month,
    get_article,
    companies_in_article,
    people_at_company
]

# Graph algorithm tools
graph_tools = [
    find_influential_companies
]

# Combine all tools
all_tools = core_tools + data_tools + graph_tools

# Create agent
agent = create_agent(
    name="investment_research",
    tools=all_tools,
    instructions="""
    You are an investment research analyst with access to a comprehensive
    knowledge graph of companies (organizations), people, articles about companies,
    industry categories, and technologies.

    Your mission is to provide thorough, data-driven research and analysis by
    leveraging the full power of the graph database.

    ## Available Tools

    **Company Discovery & Analysis:**
    - list_industries() - Browse all industry categories
    - companies_in_industry(industry) - Find companies in specific industries
    - search_companies(search) - Full-text search by company name
    - query_company(company_name) - Get detailed company profile with locations,
      industries, and leadership

    **News & Content Analysis:**
    - search_news(company_name, query, limit) - Vector search for relevant articles
    - articles_in_month(date) - Time-based article discovery
    - get_article(article_id) - Retrieve full article content
    - companies_in_article(article_id) - See which companies are mentioned

    **Relationship & Network Analysis:**
    - analyze_relationships(company_name, max_depth) - Explore organizational connections
    - people_at_company(company_id) - Identify key people and their roles
    - find_influential_companies(limit) - PageRank analysis to identify network hubs

    ## Critical Guidelines

    1. **Always return IDs**: When providing company, article, or people information,
       ALWAYS include the relevant IDs (company_id, article_id, etc.). This allows
       follow-up queries and deeper investigation.

    2. **Choose appropriate formats**:
       - Use tables for comparing multiple entities
       - Use bullet lists for attributes of a single entity
       - Include relevant IDs in all outputs

    3. **Comprehensive research approach**:
       - Start broad (industry overview, search) then narrow down
       - Always check recent news and sentiment
       - Explore organizational relationships and networks
       - Identify key people and their roles
       - Use PageRank to understand industry influence

    4. **Multi-faceted analysis**:
       - Don't rely on a single data source
       - Cross-reference company data with news articles
       - Examine both direct attributes and network position
       - Consider temporal trends (use articles_in_month)

    5. **Synthesize insights**:
       - Connect dots between company data, news, and relationships
       - Highlight significant patterns or anomalies
       - Provide context using industry and competitor information

    ## Research Workflow

    For company research requests:
    1. Identify or search for target companies (search_companies, companies_in_industry)
    2. Get detailed company profile (query_company) - note the company_id
    3. Analyze recent news and sentiment (search_news, articles_in_month)
    4. Investigate key relationships (analyze_relationships, people_at_company)
    5. Assess industry position (find_influential_companies, companies_in_industry)
    6. Synthesize findings into actionable insights

    For industry analysis requests:
    1. List relevant industries (list_industries)
    2. Get companies in sector (companies_in_industry)
    3. Identify market leaders (find_influential_companies)
    4. Analyze recent industry news (articles_in_month, search_news)
    5. Map competitive landscape (analyze_relationships)

    For event/news-driven research:
    1. Find relevant articles (search_news, articles_in_month)
    2. Identify mentioned companies (companies_in_article)
    3. Get company details using returned company_ids
    4. Assess impact on relationships (analyze_relationships)
    5. Contextualize within industry

    Always strive for comprehensive, evidence-based analysis supported by
    data from multiple tools and perspectives.
    """
)

# Execute
result = agent.run("Research Google's recent activities and industry influence")
```

### Multi-Agent Pattern

For platforms supporting multi-agent orchestration:

```python
# Database Agent - handles all Neo4j queries
database_agent = Agent(
    name="database_agent",
    tools=[
        query_company,
        search_companies,
        companies_in_industry,
        list_industries,
        search_news,
        articles_in_month,
        get_article,
        companies_in_article,
        people_at_company,
        analyze_relationships,
        find_influential_companies
    ],
    instructions="""
    You are a data access agent with access to a comprehensive knowledge graph
    of companies (organizations), people involved with them, articles about companies,
    industry categories, and technologies.

    You will be tasked by other agents to fetch specific information from the
    knowledge graph. Your role is to execute queries efficiently and return
    comprehensive, well-structured data.

    ## Your Responsibilities

    1. **Execute precise queries**: Use the appropriate tool for each request
    2. **Return complete information**: Always include IDs (company_id, article_id, etc.)
       along with descriptive data to enable follow-up queries
    3. **Format appropriately**: Use tabular formats or bullet lists as suitable
    4. **Be thorough**: When asked about a company, provide all available aspects
       (profile, news, relationships, people) unless specifically told otherwise

    ## Tool Selection Guidelines

    - For company discovery: Use search_companies or companies_in_industry
    - For detailed profiles: Use query_company (returns name, locations, industries, leadership)
    - For news analysis: Use search_news (vector search) or articles_in_month (time-based)
    - For full content: Use get_article when article_id is known
    - For relationships: Use analyze_relationships or companies_in_article
    - For people: Use people_at_company with company_id
    - For industry overview: Use list_industries then companies_in_industry
    - For influence analysis: Use find_influential_companies (PageRank)

    ## Output Requirements

    **CRITICAL**: Always output the company_id when returning company information
    from any tool call. The company_id is essential for subsequent tool calls by
    other agents.

    Format examples:
    - Tables for multiple entities with comparable attributes
    - Bullet lists for attributes of a single entity
    - Include all relevant IDs (company_id, article_id) in outputs

    Be responsive, accurate, and always include IDs for downstream processing.
    """
)

# Analysis Agent - synthesizes information
analyst_agent = Agent(
    name="analyst",
    tools=[synthesize_report],  # May have access to LLM/synthesis tools
    instructions="""
    You are an investment research analyst responsible for synthesizing
    raw data into actionable insights and comprehensive reports.

    You receive structured data from the database agent containing:
    - Company profiles (locations, industries, leadership)
    - News articles (titles, dates, sentiment, content)
    - Organizational relationships and networks
    - Industry context and competitive landscape
    - Network influence metrics (PageRank scores)
    - People and their roles

    Your task is to transform this raw data into valuable investment insights.

    ## Analysis Guidelines

    1. **Contextualize data**: Don't just repeat facts - explain what they mean
    2. **Identify patterns**: Look for trends, anomalies, or significant changes
    3. **Connect the dots**: Link company data, news, relationships, and network position
    4. **Assess implications**: What does this mean for investors?
    5. **Be specific**: Use concrete examples and data points from the graph

    ## Report Structure

    Your research reports should include:

    **Executive Summary**: 2-3 sentence overview of key findings

    **Company Profile**:
    - Core business and industries
    - Geographic presence
    - Leadership structure

    **Recent Developments**:
    - Key news and events (with dates)
    - Sentiment analysis
    - Strategic moves and announcements

    **Network Analysis**:
    - Organizational relationships and partnerships
    - Network position and influence (PageRank scores)
    - Key people and their roles

    **Industry Context:**
    - Industry positioning
    - Competitive landscape
    - Market trends

    **Risk Factors & Opportunities:**
    - Identified from news sentiment and relationship analysis
    - Market position concerns
    - Growth opportunities

    **Investment Outlook:**
    - Data-driven assessment
    - Key metrics and indicators
    - Recommendations based on evidence

    Always cite specific data points, IDs, and sources in your analysis.
    """
)

# Coordinator - orchestrates the multi-agent workflow
coordinator = Agent(
    name="coordinator",
    agents=[database_agent, analyst_agent],
    instructions="""
    You are a research coordinator managing a team of specialized agents
    to conduct comprehensive investment research.

    ## Available Agents

    **database_agent**: Queries the Neo4j knowledge graph for companies, news,
    relationships, people, and industry data. Always includes IDs in responses.

    **analyst**: Synthesizes raw data into insights and investment reports.

    ## Research Orchestration

    For any research request, coordinate the workflow:

    1. **Data Gathering Phase** (database_agent):
       - Search for or identify target companies
       - Retrieve company profiles (get company_ids)
       - Collect recent news and sentiment
       - Analyze organizational relationships
       - Get people and role information
       - Calculate network influence (PageRank)
       - Gather industry context

    2. **Analysis Phase** (analyst):
       - Pass all collected data to analyst
       - Ensure company_ids, article_ids are included
       - Request comprehensive report synthesis

    3. **Quality Check**:
       - Verify all key data points are covered
       - Ensure analysis is backed by specific evidence
       - Confirm actionable insights are provided

    ## Coordination Tips

    - Be explicit when requesting data: "Get company profile for X including company_id"
    - Ask database_agent for related data: "Find news about company_id ABC"
    - Provide complete context to analyst: "Here's company profile, news, relationships..."
    - Request specific analyses: "Assess network position using PageRank scores"

    Your goal is to deliver thorough, multi-dimensional research that combines
    structured data with thoughtful analysis.
    """
)

# Execute
result = coordinator.run("Research Google's position in the technology industry")
```

## Implementation Checklist

When implementing for a platform, ensure you:

**Database Connection:**
- [ ] Connect to demo database (neo4j+s://demo.neo4jlabs.com:7687)
- [ ] Use credentials: username=companies, password=companies, database=companies
- [ ] Use `driver.execute_query()` (not deprecated `session()`)

**Core Functions (Required):**
- [ ] Implement `query_company(company_name)` - company profiles
- [ ] Implement `search_news(company_name, query, limit)` - vector search
- [ ] Implement `search_companies(search)` - full-text search
- [ ] Implement `companies_in_industry(industry)` - industry filtering

**Extended Functions (Recommended):**
- [ ] Implement `list_industries()` - browse industries
- [ ] Implement `articles_in_month(date)` - time-based news
- [ ] Implement `get_article(article_id)` - full article content
- [ ] Implement `companies_in_article(article_id)` - article analysis
- [ ] Implement `people_at_company(company_id)` - people & roles
- [ ] Implement `analyze_relationships(company_name, max_depth)` - network traversal

**Graph Algorithms (Advanced):**
- [ ] Implement `find_influential_companies(limit)` - PageRank analysis
- [ ] Consider additional algorithms (community detection, centrality, similarity)

**Agent Configuration:**
- [ ] Create agent(s) with comprehensive instructions (see examples above)
- [ ] Emphasize returning IDs (company_id, article_id) in outputs
- [ ] Configure appropriate output formats (tables, bullet lists)
- [ ] Handle authentication (API keys, OAuth, platform IAM)

**Testing & Validation:**
- [ ] Test with example companies ("Google", "Microsoft", "Tesla")
- [ ] Verify all tools return proper IDs
- [ ] Test vector search with relevant queries
- [ ] Validate PageRank returns scores
- [ ] Test multi-step workflows (search → profile → news → relationships)

**Documentation:**
- [ ] Document platform-specific adaptations
- [ ] Note any challenges or limitations encountered
- [ ] Include example queries and expected outputs
- [ ] Document authentication setup steps

## Test Queries

Use these to verify your implementation:

**Basic company lookup:**
```
"Get information about Google"
Expected tools: query_company → should return company_id, locations, industries, leadership
```

**Full-text search:**
```
"Find companies related to artificial intelligence"
Expected tools: search_companies → should return multiple companies with company_ids
```

**Industry exploration:**
```
"What companies are in the software industry?"
Expected tools: list_industries → companies_in_industry → returns filtered list
```

**News analysis:**
```
"Find recent news about Microsoft"
Expected tools: search_news → returns articles with article_ids, dates, sentiment
```

**Time-based news:**
```
"What articles were published in January 2024?"
Expected tools: articles_in_month("2024-01-01") → returns chronological articles
```

**Deep article analysis:**
```
"Get full details of article ABC123"
Expected tools: get_article(article_id) → companies_in_article → returns full content + companies
```

**People and roles:**
```
"Who are the key people at company XYZ?"
Expected tools: query_company → people_at_company(company_id) → returns roles and names
```

**Relationship analysis:**
```
"Analyze Tesla's organizational network"
Expected tools: query_company → analyze_relationships → shows connected organizations
```

**Network influence:**
```
"Which companies are most influential in the technology sector?"
Expected tools: companies_in_industry → find_influential_companies → PageRank scores
```

**Multi-step research:**
```
"Research recent developments at Microsoft, including news and partnerships"
Expected workflow:
1. query_company("Microsoft") → get company_id
2. search_news("Microsoft", "recent developments")
3. analyze_relationships("Microsoft")
4. people_at_company(company_id)
5. synthesize_report()
```

**Comparative analysis:**
```
"Compare Google and Microsoft's AI initiatives"
Expected workflow:
1. search_companies("Google"), search_companies("Microsoft")
2. query_company() for both
3. search_news() with query="AI initiatives" for both
4. companies_in_industry("Software")
5. find_influential_companies() for ranking
6. Synthesis comparing both companies
```

**Industry deep-dive:**
```
"Analyze the technology industry landscape"
Expected workflow:
1. list_industries() → identify tech categories
2. companies_in_industry() for each category
3. find_influential_companies() → identify leaders
4. articles_in_month() → recent industry news
5. Comprehensive industry report
```

## Expected Output

A complete research report should include:

```markdown
# Investment Research Report: [Company Name]
**Company ID**: [company_id for reference]

## Executive Summary
[2-3 sentence overview of key findings, highlighting most significant insights]

## Company Profile

**Basic Information**:
- Name: [Company Name]
- Company ID: [company_id]
- Industries: [Industry sectors from query_company]
- Geographic Presence: [Locations from query_company]

**Leadership**:
[People and roles from people_at_company]
- [Name]: [Role] (from company_id analysis)
- [Name]: [Role]

## Recent Developments

**News Summary** (from search_news):
[Synthesized overview with sentiment analysis]

**Key Articles**:
1. **[Article Title]** ([Date]) - Sentiment: [score]
   - Article ID: [article_id]
   - Summary: [Brief description]
   - Source: [Site name from get_article]

2. **[Article Title]** ([Date]) - Sentiment: [score]
   - Article ID: [article_id]
   - Summary: [Brief description]

[Include 3-5 most relevant articles]

## Organizational Network

**Direct Relationships** (from analyze_relationships):
- Connected to [Company Name] (company_id: [id]) - Distance: [1-2]
- Type: [Relationship types]

**Network Influence** (from find_influential_companies):
- PageRank Score: [score]
- Ranking: [#X in industry/overall]
- Comparison to peers: [Context]

**Key People & Roles** (from people_at_company):
| Person | Role | Company |
|--------|------|---------|
| [Name] | [Role] | [Company] (company_id: [id]) |

## Industry Context

**Industry Positioning** (from companies_in_industry):
- Industry: [Category names]
- Competitors: [List with company_ids]
- Market Share Indicators: [From relationship analysis]

**Recent Industry Trends** (from articles_in_month):
- [Trend 1 based on article analysis]
- [Trend 2 from sentiment patterns]

## Risk Factors & Concerns

**From News Sentiment Analysis**:
- Negative sentiment articles: [Count and themes]
- Emerging concerns: [Based on recent news]

**From Network Analysis**:
- Dependency risks: [Based on relationship concentration]
- Competitive threats: [From PageRank and industry position]

**Identified Risks**:
1. [Risk factor with supporting data]
2. [Risk factor with article references]

## Opportunities

**Strategic Opportunities** (data-driven):
- [Opportunity based on relationship gaps]
- [Growth area from news analysis]
- [Network position advantage from PageRank]

**Market Position**:
- Strengths: [From multiple data sources]
- Advantages: [Network effects, influence scores]

## Investment Outlook

**Assessment**: [Positive/Neutral/Cautious]

**Key Metrics**:
- Network Influence: [PageRank score and context]
- News Sentiment: [Average and trend]
- Industry Position: [Relative to competitors]
- Relationship Strength: [Network analysis summary]

**Recommendation**:
[Data-driven investment perspective based on graph analysis, news sentiment,
 network position, and industry context]

**Follow-up Actions**:
- Monitor articles about: [Specific topics]
- Track relationships with: [company_ids]
- Re-evaluate if: [Specific conditions]

---
*Generated by [Platform Name] + Neo4j Knowledge Graph*
*Report Date: [Timestamp]*
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

### For MCP-based platforms/frameworks
- Use Neo4j MCP server's pre-built tools
- Configure authentication in MCP client setup
- May not need custom query functions
- If possible add to the integration listings / documentation
- Document and implement example

### For direct integration platforms
- Implement functions as native platform tools and extension points
- Handle Neo4j driver correctly (reuse single instance)

### For cloud platforms
- Store credentials in platform secret manager or handle via OIDC
- Deploy query functions as cloud functions
- Consider connection latency and timeouts
- If possible add to Agent Marketplaces

### For Agent Platforms
- Pick the right integration patterns for the platform for data integration
- Integrate initially using MCP
- Use platform extension points for deeper integration
- Ensure proper authentication mechanisms that are required by the platform are used
- Observe security, observability best practices
- If possible add data integration or graph construction
- Apply graph algorithms for additional benefit

### For low-code platforms
- Define queries as reusable components/nodes
- Use visual workflow for agent coordination
- Document node configuration requirements

## Additional Features

Where possible look at additional features for more user benefits

- Agent Memory e.g. using https://github.com/neo4j-labs/agent-memory
- Graph Algorithms
- Observability / Tracing in the graph
- Context Graphs