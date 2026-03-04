/**
 * Neo4jService.cls
 *
 * HTTP callout service for querying the Neo4j Knowledge Graph from Salesforce.
 * Called by Neo4jAction.cls (@InvocableMethod) which is registered as an
 * AgentForce action.
 *
 * AUTHENTICATION
 * Uses a Named Credential named "Neo4j_KG_API" that stores:
 *   - Base URL of the Neo4j REST bridge (mcp_bridge_server.py)
 *   - API Key via Custom Header: X-Api-Key: {your-key}
 *
 * SETUP IN SALESFORCE
 * 1. Setup → Security → External Credentials → New (Custom, Named Principal)
 *    Add header: X-Api-Key = <your-bridge-api-key>
 * 2. Setup → Security → Named Credentials → New
 *    URL: https://your-neo4j-bridge.example.com
 *    External Credential: Neo4j_KG_API
 * 3. Setup → Security → Remote Site Settings (if NOT using Named Cred URL)
 *    Remote Site URL: https://your-neo4j-bridge.example.com
 *
 * GOVERNOR LIMITS (Apex in agent context)
 * - Max 10 HTTP callouts per transaction
 * - Max 120 seconds total callout time
 * - Max 1MB response body
 * - Max 6MB heap
 */
public class Neo4jService {

    private static final String NAMED_CREDENTIAL = 'Neo4j_KG_API';
    private static final Integer CALLOUT_TIMEOUT_MS = 30000; // 30s

    // -----------------------------------------------------------------------
    // Public API
    // -----------------------------------------------------------------------

    /**
     * Full company research: profile + news + relationships in one callout.
     * Uses the /research/company combined endpoint to avoid multiple callouts.
     */
    public static String researchCompany(String companyName) {
        Map<String, Object> body = new Map<String, Object>{
            'company_name' => companyName
        };
        return makePostRequest('/research/company', body);
    }

    /**
     * Get company profile: name, company_id, industries, locations, leadership.
     */
    public static String getCompanyProfile(String companyName) {
        Map<String, Object> body = new Map<String, Object>{
            'company_name' => companyName
        };
        return makePostRequest('/tools/query_company', body);
    }

    /**
     * Search for companies matching a name or term.
     */
    public static String searchCompanies(String searchTerm) {
        Map<String, Object> body = new Map<String, Object>{
            'search' => searchTerm
        };
        return makePostRequest('/tools/search_companies', body);
    }

    /**
     * Get companies in a specific industry category.
     */
    public static String getCompaniesByIndustry(String industry) {
        Map<String, Object> body = new Map<String, Object>{
            'industry' => industry
        };
        return makePostRequest('/tools/companies_in_industry', body);
    }

    /**
     * Get all available industry categories.
     */
    public static String listIndustries() {
        return makeGetRequest('/tools/list_industries');
    }

    /**
     * Search news articles about a company using semantic search.
     * Note: Requires OPENAI_API_KEY on the bridge server for embeddings.
     */
    public static String searchCompanyNews(String companyName, String queryText) {
        Map<String, Object> body = new Map<String, Object>{
            'company_name' => companyName,
            'query' => queryText,
            'limit' => 5
        };
        return makePostRequest('/tools/search_news', body);
    }

    /**
     * Get organizations related to a company.
     */
    public static String analyzeRelationships(String companyName) {
        Map<String, Object> body = new Map<String, Object>{
            'company_name' => companyName,
            'max_depth' => 2
        };
        return makePostRequest('/tools/analyze_relationships', body);
    }

    /**
     * Get most influential companies by PageRank.
     */
    public static String getInfluentialCompanies(Integer topN) {
        Map<String, Object> body = new Map<String, Object>{
            'limit' => topN
        };
        return makePostRequest('/tools/find_influential_companies', body);
    }

    /**
     * Health check — verify bridge server connectivity.
     */
    public static Boolean isHealthy() {
        try {
            String response = makeGetRequest('/health');
            Map<String, Object> result =
                (Map<String, Object>) JSON.deserializeUntyped(response);
            return result.get('status') == 'healthy';
        } catch (Exception e) {
            return false;
        }
    }

    // -----------------------------------------------------------------------
    // Private HTTP helpers
    // -----------------------------------------------------------------------

    private static String makePostRequest(String path, Map<String, Object> body) {
        HttpRequest req = new HttpRequest();
        req.setEndpoint('callout:' + NAMED_CREDENTIAL + path);
        req.setMethod('POST');
        req.setHeader('Content-Type', 'application/json');
        req.setTimeout(CALLOUT_TIMEOUT_MS);
        req.setBody(JSON.serialize(body));

        return executeRequest(req);
    }

    private static String makeGetRequest(String path) {
        HttpRequest req = new HttpRequest();
        req.setEndpoint('callout:' + NAMED_CREDENTIAL + path);
        req.setMethod('GET');
        req.setTimeout(CALLOUT_TIMEOUT_MS);

        return executeRequest(req);
    }

    private static String executeRequest(HttpRequest req) {
        Http http = new Http();
        HttpResponse res = http.send(req);

        if (res.getStatusCode() >= 200 && res.getStatusCode() < 300) {
            return res.getBody();
        }

        // Parse error response
        String errorMsg;
        try {
            Map<String, Object> err =
                (Map<String, Object>) JSON.deserializeUntyped(res.getBody());
            errorMsg = String.valueOf(err.get('detail'));
        } catch (Exception parseEx) {
            errorMsg = res.getBody();
        }

        throw new Neo4jCalloutException(
            'Neo4j API error ' + res.getStatusCode() + ': ' + errorMsg
        );
    }

    // -----------------------------------------------------------------------
    // Custom Exception
    // -----------------------------------------------------------------------

    public class Neo4jCalloutException extends Exception {}
}
