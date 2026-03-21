@IsTest
public class Neo4jActionTest {
    private class Neo4jMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setHeader('Content-Type', 'application/json');
            // Mocking the structure: org, ceo, competitors, suppliers, subsidiaries, related_articles
            res.setBody('{"data": {"values": [[' + 
                '{"_properties": {"name": "Neo4j"}}, ' + 
                '{"_properties": {"name": "Emil"}}, ' + 
                '[{"organization": {"_properties": {"name": "GraphBase"}}}], ' + 
                '[], ' + 
                '[], ' + 
                '[]' + 
            ']]}}');
            res.setStatusCode(200);
            return res;
        }
    }

    @IsTest
    static void testGetInsights() {
        System.Test.setMock(HttpCalloutMock.class, new Neo4jMock());
        
        Neo4jAction.Request req = new Neo4jAction.Request();
        req.orgName = 'Neo4j';
        
        System.Test.startTest();
        List<Neo4jAction.InsightsOutput> outputs = Neo4jAction.getInsights(new List<Neo4jAction.Request>{req});
        System.Test.stopTest();
        
        System.assertEquals(1, outputs.size());
        System.assert(outputs[0].result.contains('Neo4j'), 'Result should contain Neo4j: ' + outputs[0].result);
    }
}
