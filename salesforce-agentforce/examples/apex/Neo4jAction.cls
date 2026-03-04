/**
 * Neo4jAction.cls
 *
 * AgentForce Apex Actions for Neo4j Knowledge Graph integration.
 *
 * Each @InvocableMethod becomes a separate AgentForce action in Agent Builder.
 * The ARE (Atlas Reasoning Engine) reads the 'description' field to decide
 * which action to call — write descriptions carefully.
 *
 * REGISTERING IN SALESFORCE AGENT BUILDER
 * Setup → Agents → Your Agent → Topics → Your Topic → Actions → New Action
 *   Type: Apex
 *   Apex Class: Neo4jAction (select the method)
 *
 * NOTE ON DESCRIPTIONS
 * The 'description' on @InvocableMethod is critical — the ARE uses it as
 * the tool description for selection. Be specific about:
 *   - WHAT the action does
 *   - WHEN to use it (trigger phrases)
 *   - WHAT inputs look like
 *   - WHAT the output contains
 *
 * NOTE ON APEX
 * Apex is Salesforce's proprietary server-side language (Java-like syntax).
 * This code runs inside Salesforce's cloud — not on your servers.
 * Governor limits: 10 HTTP callouts/tx, 120s timeout, 6MB heap.
 */
public class Neo4jAction {

    // =======================================================================
    // ACTION 1: Full Company Research (Primary — use this for most queries)
    // =======================================================================

    public class ResearchInput {
        @InvocableVariable(
            label='Company Name'
            description='The full or common name of the company to research. Examples: "Apple", "Tesla", "JPMorgan Chase". Do not use ticker symbols.'
            required=true
        )
        public String companyName;
    }

    public class ResearchOutput {
        @InvocableVariable(
            label='Research Results'
            description='JSON string containing company profile, recent news headlines, and organizational relationships'
        )
        public String researchResults;

        @InvocableVariable(
            label='Company Name'
            description='Confirmed company name as found in the knowledge graph'
        )
        public String confirmedCompanyName;

        @InvocableVariable(
            label='Success'
            description='Whether the research completed successfully'
        )
        public Boolean success;

        @InvocableVariable(
            label='Error Message'
            description='Error details if success is false'
        )
        public String errorMessage;
    }

    @InvocableMethod(
        label='Research Company in Knowledge Graph'
        description='Retrieves comprehensive company information from the Neo4j knowledge graph in a single call. Returns company profile (industry, location, leadership, company ID), recent news headlines with sentiment, and organizational relationships. Use this as the PRIMARY action when a user asks about a company, its background, news, or competitive position. Input: company name as a string.'
        category='Neo4j Knowledge Graph'
    )
    public static List<ResearchOutput> researchCompany(List<ResearchInput> inputs) {
        List<ResearchOutput> outputs = new List<ResearchOutput>();

        for (ResearchInput input : inputs) {
            ResearchOutput output = new ResearchOutput();
            try {
                String result = Neo4jService.researchCompany(input.companyName);
                output.researchResults = result;
                output.success = true;

                // Extract company name from response for confirmation
                Map<String, Object> parsed =
                    (Map<String, Object>) JSON.deserializeUntyped(result);
                Map<String, Object> profile =
                    (Map<String, Object>) parsed.get('profile');
                if (profile != null) {
                    output.confirmedCompanyName = String.valueOf(profile.get('name'));
                }
            } catch (Neo4jService.Neo4jCalloutException e) {
                output.success = false;
                output.errorMessage = e.getMessage();
                output.researchResults = '{"error": "' + e.getMessage() + '"}';
            } catch (Exception e) {
                output.success = false;
                output.errorMessage = 'Unexpected error: ' + e.getMessage();
            }
            outputs.add(output);
        }
        return outputs;
    }

    // =======================================================================
    // ACTION 2: Search Companies
    // =======================================================================

    public class SearchInput {
        @InvocableVariable(
            label='Search Term'
            description='Partial or full company name to search for. Use when you do not know the exact company name.'
            required=true
        )
        public String searchTerm;
    }

    public class SearchOutput {
        @InvocableVariable(
            label='Companies Found'
            description='JSON array of matching companies with name, company_id, and summary'
        )
        public String companiesJson;

        @InvocableVariable(label='Success')
        public Boolean success;

        @InvocableVariable(label='Error Message')
        public String errorMessage;
    }

    @InvocableMethod(
        label='Search Companies in Knowledge Graph'
        description='Full-text search for companies matching a name or keyword. Returns matching company names and IDs. Use this when the user mentions a company but you are not sure of the exact name, or when browsing companies in a sector. Returns company_id values for use in follow-up queries.'
        category='Neo4j Knowledge Graph'
    )
    public static List<SearchOutput> searchCompanies(List<SearchInput> inputs) {
        List<SearchOutput> outputs = new List<SearchOutput>();

        for (SearchInput input : inputs) {
            SearchOutput output = new SearchOutput();
            try {
                output.companiesJson = Neo4jService.searchCompanies(input.searchTerm);
                output.success = true;
            } catch (Exception e) {
                output.success = false;
                output.errorMessage = e.getMessage();
            }
            outputs.add(output);
        }
        return outputs;
    }

    // =======================================================================
    // ACTION 3: Industry Companies
    // =======================================================================

    public class IndustryInput {
        @InvocableVariable(
            label='Industry Name'
            description='Industry category name. Use "List Industries" action first to get valid names.'
            required=true
        )
        public String industryName;
    }

    public class IndustryOutput {
        @InvocableVariable(
            label='Companies in Industry'
            description='JSON array of companies in the specified industry'
        )
        public String companiesJson;

        @InvocableVariable(label='Industry Searched')
        public String industrySearched;

        @InvocableVariable(label='Success')
        public Boolean success;

        @InvocableVariable(label='Error Message')
        public String errorMessage;
    }

    @InvocableMethod(
        label='Get Companies in Industry from Knowledge Graph'
        description='Returns all companies in a specific industry category from the knowledge graph. Use when the user asks about companies in a sector (e.g., "software companies", "banks", "automotive"). Use the List Industries action first if the exact category name is unknown.'
        category='Neo4j Knowledge Graph'
    )
    public static List<IndustryOutput> getCompaniesByIndustry(List<IndustryInput> inputs) {
        List<IndustryOutput> outputs = new List<IndustryOutput>();

        for (IndustryInput input : inputs) {
            IndustryOutput output = new IndustryOutput();
            output.industrySearched = input.industryName;
            try {
                output.companiesJson =
                    Neo4jService.getCompaniesByIndustry(input.industryName);
                output.success = true;
            } catch (Exception e) {
                output.success = false;
                output.errorMessage = e.getMessage();
            }
            outputs.add(output);
        }
        return outputs;
    }

    // =======================================================================
    // ACTION 4: Find Influential Companies
    // =======================================================================

    public class PageRankInput {
        @InvocableVariable(
            label='Number of Results'
            description='How many top influential companies to return (default 10)'
            required=false
        )
        public Integer topN;
    }

    public class PageRankOutput {
        @InvocableVariable(
            label='Influential Companies'
            description='JSON array of most influential companies by PageRank score'
        )
        public String companiesJson;

        @InvocableVariable(label='Success')
        public Boolean success;

        @InvocableVariable(label='Error Message')
        public String errorMessage;
    }

    @InvocableMethod(
        label='Find Most Influential Companies by Network Analysis'
        description='Uses the PageRank graph algorithm to identify the most influential companies in the knowledge graph based on their organizational relationships and connections. Higher scores mean more interconnected companies. Use when the user asks about market leaders, the most connected companies, or wants a network-based ranking.'
        category='Neo4j Knowledge Graph'
    )
    public static List<PageRankOutput> findInfluentialCompanies(List<PageRankInput> inputs) {
        List<PageRankOutput> outputs = new List<PageRankOutput>();

        for (PageRankInput input : inputs) {
            PageRankOutput output = new PageRankOutput();
            try {
                Integer limit = (input.topN != null && input.topN > 0) ? input.topN : 10;
                output.companiesJson = Neo4jService.getInfluentialCompanies(limit);
                output.success = true;
            } catch (Exception e) {
                output.success = false;
                output.errorMessage = e.getMessage();
            }
            outputs.add(output);
        }
        return outputs;
    }
}
