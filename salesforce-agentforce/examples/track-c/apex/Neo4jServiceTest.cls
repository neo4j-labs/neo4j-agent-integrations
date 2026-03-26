@IsTest
public class Neo4jServiceTest {
    private class Neo4jMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setHeader('Content-Type', 'application/json');
            res.setBody('{"data": {"values": [[{"_properties": {"name": "Test Org"}}]]}}');
            res.setStatusCode(200);
            return res;
        }
    }

    @IsTest
    static void testQueryCompanies() {
        System.Test.setMock(HttpCalloutMock.class, new Neo4jMock());
        
        System.Test.startTest();
        List<Map<String, Object>> results = Neo4jService.queryCompanies('MATCH (n) RETURN n LIMIT 1');
        System.Test.stopTest();
        
        System.assertEquals(1, results.size(), 'Should return one result');
        System.assertEquals('Test Org', results[0].get('name'), 'Name should match mock');
    }

    @IsTest
    static void testQueryCompaniesError() {
        System.Test.setMock(HttpCalloutMock.class, new ErrorMock());
        
        System.Test.startTest();
        try {
            Neo4jService.queryCompanies('MATCH (n) RETURN n LIMIT 1');
            System.assert(false, 'Should have thrown an exception');
        } catch (CalloutException e) {
            System.assert(e.getMessage().contains('Neo4j query failed'), 'Exception message should contain failure info');
        }
        System.Test.stopTest();
    }

    private class ErrorMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setStatusCode(500);
            res.setBody('Internal Server Error');
            return res;
        }
    }
}
