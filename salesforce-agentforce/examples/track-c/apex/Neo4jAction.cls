public with sharing class Neo4jAction {
    
    public class Request {
        @InvocableVariable(label='Organization Name' description='The name of the organization to query (e.g., Acme Corp)' required=true)
        public String orgName;        
    }

    public class InsightsOutput {
        @InvocableVariable(
            label='Neo4j Insights'
            description='JSON string containing company profile, recent news headlines, and organizational relationships'
        )
        public String result;
    }

    @InvocableMethod(
        label='Get Neo4j Organization Insights' 
        description='Queries Neo4j for strategic insights about an organization, including competitors, suppliers, and geographic presence.'
    )
    public static List<InsightsOutput> getInsights(List<Request> requests) {
        List<InsightsOutput> outputs = new List<InsightsOutput>();

        for (Request req : requests) {
            String orgName = req.orgName;
            
            String query = 
                'MATCH (org:Organization {name: "' + orgName + '"}) ' +
                'OPTIONAL MATCH (org)-[:HAS_CEO]->(ceo:Person) ' +
                'WITH org, ceo, ' +
                '     [(org)-[:HAS_COMPETITOR]-(comp) | {organization: comp, ceo: [(comp)-[:HAS_CEO]->(c) | c][0]}] AS competitors, ' +
                '     [(org)-[:HAS_SUPPLIER]->(supp) | {organization: supp, ceo: [(supp)-[:HAS_CEO]->(c) | c][0]}] AS suppliers, ' +
                '     [(org)-[:HAS_SUBSIDIARY]->(sub) | {organization: sub, ceo: [(sub)-[:HAS_CEO]->(c) | c][0]}] AS subsidiaries ' +
                'CALL (org, competitors, suppliers, subsidiaries) { ' +
                '    WITH [c IN competitors | c.organization] +  ' +
                '         [s IN suppliers | s.organization] +  ' +
                '         [sub IN subsidiaries | sub.organization] +  ' +
                '         [org] AS targets ' +
                '    UNWIND targets AS target ' +
                '    WITH DISTINCT target WHERE target IS NOT NULL ' +
                '    MATCH (article:Article)-[:MENTIONS]->(target) ' +
                '    RETURN DISTINCT article ' +
                '    ORDER BY article.date DESC ' +
                '    LIMIT 10 ' +
                '} ' +
                'RETURN  ' +
                '    org,  ' +
                '    ceo,  ' +
                '    competitors,  ' +
                '    suppliers,  ' +
                '    subsidiaries,  ' +
                '    collect(article { .title, .siteName }) AS related_articles';

            try {
                Map<String, Object> rawResponse = Neo4jService.executeRawQuery(query);
                InsightsOutput output = new InsightsOutput();
                output.result = formatInsights(rawResponse);
                outputs.add(output);
            } catch (Exception e) {
                InsightsOutput errorOutput = new InsightsOutput();
                errorOutput.result = 'Error fetching insights: ' + e.getMessage();
                outputs.add(errorOutput);
            }
        }

        return outputs;
    }

    private static String formatInsights(Map<String, Object> rawResponse) {
        Map<String, Object> data = (Map<String, Object>) rawResponse.get('data');
        if (data == null) return '{}';

        List<Object> values = (List<Object>) data.get('values');
        if (values == null || values.isEmpty()) return '{"message": "No insights found."}';

        List<Object> row = (List<Object>) values[0];
        // Order of RETURN: org, ceo, competitors, suppliers, subsidiaries, related_articles
        
        Map<String, Object> result = new Map<String, Object>();
        result.put('org', simplify(row[0]));
        result.put('ceo', simplify(row[1]));
        result.put('competitors', simplifyList(row[2]));
        result.put('suppliers', simplifyList(row[3]));
        result.put('subsidiaries', simplifyList(row[4]));
        result.put('relatedArticles', simplifyList(row[5]));

        return JSON.serializePretty(result);
    }

    private static Object simplify(Object item) {
        if (item == null) return null;
        if (item instanceof Map<String, Object>) {
            Map<String, Object> node = (Map<String, Object>) item;
            
            // Handle Neo4j node structure (both _properties and properties)
            Object props = node.get('_properties');
            if (props == null) props = node.get('properties');
            
            if (props != null) {
                return simplify(props);
            }

            // If it's a map but not a standard node (or we already extracted props), 
            // recurse into its values
            Map<String, Object> simplifiedMap = new Map<String, Object>();
            for (String key : node.keySet()) {
                simplifiedMap.put(key, simplify(node.get(key)));
            }
            return simplifiedMap;
        } else if (item instanceof List<Object>) {
            List<Object> simplifiedList = new List<Object>();
            for (Object subItem : (List<Object>) item) {
                simplifiedList.add(simplify(subItem));
            }
            return simplifiedList;
        }
        return item;
    }

    private static List<Object> simplifyList(Object items) {
        return (List<Object>) simplify(items);
    }
}
