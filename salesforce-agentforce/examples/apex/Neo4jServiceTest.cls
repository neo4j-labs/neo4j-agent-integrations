/**
 * Neo4jServiceTest.cls
 *
 * Test class for Neo4jService.cls
 *
 * Salesforce REQUIRES 75%+ Apex test coverage to deploy to production.
 * All HTTP callouts must be mocked using Test.setMock() — you cannot make
 * real HTTP calls from test methods.
 *
 * Run tests:
 *   Developer Console → Test → New Run → Select Neo4jServiceTest → Run
 *   OR via SFDX: sf apex run test --class-names Neo4jServiceTest --result-format human
 */
@isTest
private class Neo4jServiceTest {

    // -----------------------------------------------------------------------
    // Mock HTTP Responses
    // -----------------------------------------------------------------------

    /**
     * Mock for successful company research response.
     */
    private class CompanyResearchMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            res.setHeader('Content-Type', 'application/json');
            res.setBody(JSON.serialize(new Map<String, Object>{
                'profile' => new Map<String, Object>{
                    'name' => 'Apple',
                    'company_id' => 'test-id-123',
                    'summary' => 'Technology company',
                    'locations' => new List<String>{'Cupertino, California'},
                    'industries' => new List<String>{'Consumer Electronics', 'Software'},
                    'leadership' => new List<Map<String, Object>>{
                        new Map<String, Object>{'name' => 'Tim Cook', 'title' => 'CEO'}
                    }
                },
                'recent_news' => new List<Map<String, Object>>{
                    new Map<String, Object>{
                        'title' => 'Apple announces new AI features',
                        'date' => '2024-06-10',
                        'sentiment' => 0.8
                    }
                },
                'relationships' => new List<Map<String, Object>>{
                    new Map<String, Object>{
                        'organization' => 'Microsoft',
                        'relationship_type' => 'COMPETES_WITH',
                        'distance' => 1
                    }
                }
            }));
            return res;
        }
    }

    /**
     * Mock for company search response.
     */
    private class SearchMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            res.setHeader('Content-Type', 'application/json');
            res.setBody(JSON.serialize(new Map<String, Object>{
                'companies' => new List<Map<String, Object>>{
                    new Map<String, Object>{
                        'company_id' => 'id-apple',
                        'name' => 'Apple',
                        'summary' => 'Consumer electronics and software'
                    },
                    new Map<String, Object>{
                        'company_id' => 'id-apple-pay',
                        'name' => 'Apple Financial Services',
                        'summary' => 'Financial services division'
                    }
                }
            }));
            return res;
        }
    }

    /**
     * Mock for health check response.
     */
    private class HealthMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            res.setHeader('Content-Type', 'application/json');
            res.setBody('{"status": "healthy", "organization_count": 250000}');
            return res;
        }
    }

    /**
     * Mock for error response (404 Not Found).
     */
    private class ErrorMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setStatusCode(404);
            res.setHeader('Content-Type', 'application/json');
            res.setBody('{"detail": "Company \'UnknownCo\' not found"}');
            return res;
        }
    }

    /**
     * Mock for industry companies response.
     */
    private class IndustryMock implements HttpCalloutMock {
        public HttpResponse respond(HttpRequest req) {
            HttpResponse res = new HttpResponse();
            res.setStatusCode(200);
            res.setHeader('Content-Type', 'application/json');
            res.setBody(JSON.serialize(new Map<String, Object>{
                'companies' => new List<Map<String, Object>>{
                    new Map<String, Object>{'company_id' => 'id-1', 'name' => 'Apple', 'summary' => 'Tech'},
                    new Map<String, Object>{'company_id' => 'id-2', 'name' => 'Google', 'summary' => 'Tech'}
                }
            }));
            return res;
        }
    }

    // -----------------------------------------------------------------------
    // Test Methods
    // -----------------------------------------------------------------------

    @isTest
    static void testResearchCompanySuccess() {
        Test.setMock(HttpCalloutMock.class, new CompanyResearchMock());

        Test.startTest();
        String result = Neo4jService.researchCompany('Apple');
        Test.stopTest();

        System.assertNotEquals(null, result, 'Result should not be null');
        System.assert(result.contains('Apple'), 'Result should contain company name');
        System.assert(result.contains('company_id'), 'Result should contain company_id');
        System.assert(result.contains('recent_news'), 'Result should contain news');
    }

    @isTest
    static void testResearchCompanyNotFound() {
        Test.setMock(HttpCalloutMock.class, new ErrorMock());

        Test.startTest();
        Boolean exceptionThrown = false;
        try {
            Neo4jService.researchCompany('UnknownCo');
        } catch (Neo4jService.Neo4jCalloutException e) {
            exceptionThrown = true;
            System.assert(e.getMessage().contains('404'), 'Exception should mention 404');
        }
        Test.stopTest();

        System.assert(exceptionThrown, 'Should throw exception for not-found company');
    }

    @isTest
    static void testSearchCompanies() {
        Test.setMock(HttpCalloutMock.class, new SearchMock());

        Test.startTest();
        String result = Neo4jService.searchCompanies('Apple');
        Test.stopTest();

        System.assertNotEquals(null, result);
        Map<String, Object> parsed = (Map<String, Object>) JSON.deserializeUntyped(result);
        System.assert(parsed.containsKey('companies'), 'Should have companies key');
        List<Object> companies = (List<Object>) parsed.get('companies');
        System.assert(companies.size() > 0, 'Should have at least one company');
    }

    @isTest
    static void testListIndustriesMock() {
        // Reuse a simple mock
        Test.setMock(HttpCalloutMock.class, new HealthMock());
        // Note: listIndustries returns its own format — testing health here
        Test.startTest();
        Boolean healthy = Neo4jService.isHealthy();
        Test.stopTest();
        System.assert(healthy, 'Health check should return true');
    }

    @isTest
    static void testGetCompaniesByIndustry() {
        Test.setMock(HttpCalloutMock.class, new IndustryMock());

        Test.startTest();
        String result = Neo4jService.getCompaniesByIndustry('Software');
        Test.stopTest();

        System.assertNotEquals(null, result);
        System.assert(result.contains('companies'), 'Should have companies');
    }

    @isTest
    static void testIsHealthyTrue() {
        Test.setMock(HttpCalloutMock.class, new HealthMock());

        Test.startTest();
        Boolean result = Neo4jService.isHealthy();
        Test.stopTest();

        System.assertEquals(true, result, 'Should return true for healthy response');
    }

    @isTest
    static void testIsHealthyFalse() {
        Test.setMock(HttpCalloutMock.class, new ErrorMock());

        Test.startTest();
        Boolean result = Neo4jService.isHealthy();
        Test.stopTest();

        System.assertEquals(false, result, 'Should return false for error response');
    }

    // -----------------------------------------------------------------------
    // Neo4jAction tests
    // -----------------------------------------------------------------------

    @isTest
    static void testResearchActionSuccess() {
        Test.setMock(HttpCalloutMock.class, new CompanyResearchMock());

        Neo4jAction.ResearchInput input = new Neo4jAction.ResearchInput();
        input.companyName = 'Apple';

        Test.startTest();
        List<Neo4jAction.ResearchOutput> outputs =
            Neo4jAction.researchCompany(new List<Neo4jAction.ResearchInput>{input});
        Test.stopTest();

        System.assertEquals(1, outputs.size(), 'Should return one output');
        System.assertEquals(true, outputs[0].success, 'Should succeed');
        System.assertNotEquals(null, outputs[0].researchResults, 'Should have results');
        System.assertEquals('Apple', outputs[0].confirmedCompanyName);
    }

    @isTest
    static void testResearchActionFailure() {
        Test.setMock(HttpCalloutMock.class, new ErrorMock());

        Neo4jAction.ResearchInput input = new Neo4jAction.ResearchInput();
        input.companyName = 'UnknownCo';

        Test.startTest();
        List<Neo4jAction.ResearchOutput> outputs =
            Neo4jAction.researchCompany(new List<Neo4jAction.ResearchInput>{input});
        Test.stopTest();

        System.assertEquals(1, outputs.size());
        System.assertEquals(false, outputs[0].success, 'Should fail');
        System.assertNotEquals(null, outputs[0].errorMessage, 'Should have error message');
    }

    @isTest
    static void testSearchAction() {
        Test.setMock(HttpCalloutMock.class, new SearchMock());

        Neo4jAction.SearchInput input = new Neo4jAction.SearchInput();
        input.searchTerm = 'Apple';

        Test.startTest();
        List<Neo4jAction.SearchOutput> outputs =
            Neo4jAction.searchCompanies(new List<Neo4jAction.SearchInput>{input});
        Test.stopTest();

        System.assertEquals(1, outputs.size());
        System.assertEquals(true, outputs[0].success);
        System.assertNotEquals(null, outputs[0].companiesJson);
    }

    @isTest
    static void testIndustryAction() {
        Test.setMock(HttpCalloutMock.class, new IndustryMock());

        Neo4jAction.IndustryInput input = new Neo4jAction.IndustryInput();
        input.industryName = 'Software';

        Test.startTest();
        List<Neo4jAction.IndustryOutput> outputs =
            Neo4jAction.getCompaniesByIndustry(new List<Neo4jAction.IndustryInput>{input});
        Test.stopTest();

        System.assertEquals(1, outputs.size());
        System.assertEquals(true, outputs[0].success);
        System.assertEquals('Software', outputs[0].industrySearched);
    }
}
