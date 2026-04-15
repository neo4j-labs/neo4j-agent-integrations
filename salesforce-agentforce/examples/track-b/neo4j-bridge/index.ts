import { AutoRouter } from 'itty-router';
import { fromIttyRouter, OpenAPIRoute } from 'chanfana';
import { z } from 'zod';

// Exported environment bindings
export interface Env {
	// Add your bindings here (e.g. KV, D1, etc.)
}

export class GetInsights extends OpenAPIRoute {
	schema = {
		tags: ['Insights'],
		summary: 'Get insights for a company',
		request: {
			query: z.object({
				company: z.string({
					message: 'Missing required query parameter: "company"',
				}).describe('The company to get insights for'),
			}),
		},
		responses: {
			'200': {
				description: 'Successful response',
				content: {
					'application/json': {
						schema: z.object({
							success: z.boolean(),
							company: z.string(),
							insights: z.object({
								org: z.record(z.string(), z.any()).nullable(),
								ceo: z.record(z.string(), z.any()).nullable(),
								competitors: z.array(z.record(z.string(), z.any())),
								suppliers: z.array(z.record(z.string(), z.any())),
								subsidiaries: z.array(z.record(z.string(), z.any())),
								related_articles: z.array(z.record(z.string(), z.any())),
							}).nullable()
						}),
					},
				},
			},
		},
	};

	async handle() {
		// Get validated data using the defined schema
		const data = await this.getValidatedData<typeof this.schema>();

		const url = 'https://demo.neo4jlabs.com:7473/db/companies/query/v2';
		const auth = 'Basic ' + btoa('companies:companies');

		const cypherQuery = `
			MATCH (org:Organization {name: $company}) 
			OPTIONAL MATCH (org)-[:HAS_CEO]->(ceo:Person) 
			WITH org, ceo, 
				[(org)-[:HAS_COMPETITOR]-(comp) | {organization: comp, ceo: [(comp)-[:HAS_CEO]->(c) | c][0]}] AS competitors, 
				[(org)-[:HAS_SUPPLIER]->(supp) | {organization: supp, ceo: [(supp)-[:HAS_CEO]->(c) | c][0]}] AS suppliers, 
				[(org)-[:HAS_SUBSIDIARY]->(sub) | {organization: sub, ceo: [(sub)-[:HAS_CEO]->(c) | c][0]}] AS subsidiaries 
			CALL (org, competitors, suppliers, subsidiaries) { 
				WITH [c IN competitors | c.organization] +  
					[s IN suppliers | s.organization] +  
					[sub IN subsidiaries | sub.organization] +  
					[org] AS targets 
				UNWIND targets AS target 
				WITH DISTINCT target WHERE target IS NOT NULL 
				MATCH (article:Article)-[:MENTIONS]->(target) 
				RETURN DISTINCT article 
				ORDER BY article.date DESC 
				LIMIT 10 
			} 
			RETURN  
				org,  
				ceo,  
				competitors,  
				suppliers,  
				subsidiaries,  
				collect(article { .title, .siteName }) AS related_articles
		`;

		const response = await fetch(url, {
			method: 'POST',
			headers: {
				'content-type': 'application/json',
				'accept': 'application/json',
				'authorization': auth
			},
			body: JSON.stringify({
				statement: cypherQuery,
				parameters: { company: data.query.company }
			})
		});

		if (!response.ok) {
			return new Response(JSON.stringify({ error: `Neo4j request failed: ${response.statusText}` }), {
				status: 500,
				headers: { 'content-type': 'application/json' }
			});
		}

		const json = await response.json() as any;
		
		let insights = null;
		
		if (json.data?.values && json.data.values.length > 0) {
			const row = json.data.values[0];
			
			// Helper to extract properties from Neo4j node objects
			const extractProps = (node: any) => node?.properties || node || null;
			
			// Helper to extract properties from an array of complex Neo4j objects (like competitors: [{organization, ceo}])
			const extractComplexArray = (arr: any[]) => {
				if (!Array.isArray(arr)) return [];
				return arr.map(item => {
					// Handle structure {organization: Node, ceo: Node}
					if (item && typeof item === 'object' && !item.properties) {
						const mapped: any = {};
						for (const [k, v] of Object.entries(item)) {
							mapped[k] = extractProps(v);
						}
						return mapped;
					}
					return extractProps(item);
				});
			};

			insights = {
				org: extractProps(row[0]),
				ceo: extractProps(row[1]),
				competitors: extractComplexArray(row[2]),
				suppliers: extractComplexArray(row[3]),
				subsidiaries: extractComplexArray(row[4]),
				related_articles: row[5] || []
			};
		}

		// Returning an object automatically creates a JSON response
		return insights;
	}
}

// Initialize chanfana with itty-router
const router = fromIttyRouter(AutoRouter());

router.get('/get-insights', GetInsights);

// Export the router's fetch handler for Cloudflare Workers
export default {
	fetch: router.fetch,
} satisfies ExportedHandler<Env>;
