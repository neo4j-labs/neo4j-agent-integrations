/**
 * @description Service class to interact with Neo4j Graph Database.
 * 
 * ## SETUP INSTRUCTIONS FOR SALESFORCE ADMINS:
 * 
 * 1. EXTERNAL CREDENTIALS - Setup → Security → External Credentials → New (Custom, Named Principal)
 *    - Name: "demo_companies_neo4jlabs_auth" (or similar)
 *    - Authentication Protocol: Basic Authentication
 *    - Principals: Create a Principal with:
 *      - Parameter Name: "username", Value: "companies"
 *      - Parameter Name: "password", Value: "companies"
 *    - Note: Ensure the "Generate Authorization Header" option is used or handle it via Custom Headers 
 *      if using legacy Named Credentials.
 * 
 * 2. NAMED CREDENTIALS - Setup → Security → Named Credentials → New
 *    - Name: "demo_companies_neo4jlabs_url" (Matches ENDPOINT constant below)
 *    - URL: "https://demo.neo4jlabs.com:7473"
 *    - External Credential: The one created in Step 1.
 *    - Allowed Namespaces for Callouts: Ensure your namespace (or 'None') is allowed.
 * 
 * 3. REMOTE SITE SETTINGS - Setup → Security → Remote Site Settings
 *    - Although Named Credentials bypass Remote Site Settings for the specific URL,
 *      if not using Named Credentials, the server "https://demo.neo4jlabs.com:7473" needs to be added
 *      to Remote Site Settings to ensure platform-wide connectivity for this endpoint.
 * 
 * 4. PERMISSIONS - Setup →
 *    - Ensure the User/Profile/Permission Set running the Agent has "Enabled External Credential Principal Access"
 *      for the External Credential created in Step 1.
 */
public with sharing class Neo4jService {
    /**
     * @description The endpoint using Named Credential syntax. 
     * The 'callout:' prefix tells Salesforce to use the 'demo_companies_neo4jlabs_url' Named Credential.
     */
    private static final String ENDPOINT = 'callout:demo_companies_neo4jlabs_url/db/companies/query/v2';

    /**
     * @description Executes a Cypher query against the Neo4j companies database.
     * @param statement The Cypher query to execute.
     * @return A list of result maps, where each map represents a node's properties or a row's values.
     * @throws CalloutException if the HTTP request fails or returns a non-200 status code.
     */
    public static List<Map<String, Object>> queryCompanies(String statement) {
        HttpRequest req = new HttpRequest();
        req.setEndpoint(ENDPOINT);
        req.setMethod('POST');
        req.setHeader('Content-Type', 'application/json');
        req.setHeader('Accept', 'application/json');
        
        // The Authorization header is automatically managed by the Named Credential
        
        Map<String, String> bodyMap = new Map<String, String>{
            'statement' => statement
        };
        req.setBody(JSON.serialize(bodyMap));
        req.setTimeout(60000);

        Http http = new Http();
        HttpResponse res = http.send(req);

        if (res.getStatusCode() < 200 || res.getStatusCode() >= 300) {
            System.debug('Neo4j query failed: ' + res.getStatusCode() + ' ' + res.getBody());
            throw new CalloutException(
                'Neo4j query failed: ' + res.getStatusCode() + ' ' + res.getBody()
            );
        }

        return parseResponse(res.getBody());
    }

    /**
     * @description Executes a Cypher query and returns the raw response as a Map.
     * @param statement The Cypher query to execute.
     * @return The raw JSON response map.
     */
    public static Map<String, Object> executeRawQuery(String statement) {
        HttpRequest req = new HttpRequest();
        req.setEndpoint(ENDPOINT);
        req.setMethod('POST');
        req.setHeader('Content-Type', 'application/json');
        req.setHeader('Accept', 'application/json');
        
        Map<String, String> bodyMap = new Map<String, String>{
            'statement' => statement
        };
        req.setBody(JSON.serialize(bodyMap));
        req.setTimeout(60000);

        Http http = new Http();
        HttpResponse res = http.send(req);

        if (res.getStatusCode() < 200 || res.getStatusCode() >= 300) {
            throw new CalloutException(
                'Neo4j query failed: ' + res.getStatusCode() + ' ' + res.getBody()
            );
        }

        return (Map<String, Object>) JSON.deserializeUntyped(res.getBody());
    }

    /**
     * @description Parses the Neo4j JSON response into a list of property maps.
     * @param responseBody Raw JSON response from Neo4j.
     * @return List of maps containing entity properties.
     */
    private static List<Map<String, Object>> parseResponse(String responseBody) {
        List<Map<String, Object>> results = new List<Map<String, Object>>();

        Map<String, Object> root = (Map<String, Object>) JSON.deserializeUntyped(responseBody);
        Map<String, Object> data = (Map<String, Object>) root.get('data');
        if (data == null) return results;

        List<Object> values = (List<Object>) data.get('values');
        if (values == null) return results;

        for (Object rowObj : values) {
            List<Object> row = (List<Object>) rowObj;
            for (Object item : row) {
                if (item instanceof Map<String, Object>) {
                    Map<String, Object> node = (Map<String, Object>) item;
                    // Neo4j v2 API returns properties under the '_properties' key for nodes
                    Map<String, Object> props = (Map<String, Object>) node.get('_properties');
                    if (props != null) {
                        results.add(props);
                    } else {
                        // If it's a map but not a standard node object, add as is
                        results.add(node);
                    }
                } else if (item != null) {
                    // Fallback for primitive Cypher returns
                    results.add(new Map<String, Object>{'value' => item});
                }
            }
        }

        return results;
    }
}
