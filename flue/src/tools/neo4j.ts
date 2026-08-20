import { defineTool } from '@flue/runtime';
import neo4j, { type Driver } from 'neo4j-driver';
import * as v from 'valibot';

const DEFAULT_NEO4J_URI = 'neo4j+s://demo.neo4jlabs.com:7687';
const DEFAULT_NEO4J_USERNAME = 'companies';
const DEFAULT_NEO4J_PASSWORD = 'companies';
const DEFAULT_NEO4J_DATABASE = 'companies';

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(
    process.env.NEO4J_URI ?? DEFAULT_NEO4J_URI,
    neo4j.auth.basic(
      process.env.NEO4J_USERNAME ?? DEFAULT_NEO4J_USERNAME,
      process.env.NEO4J_PASSWORD ?? DEFAULT_NEO4J_PASSWORD,
    ),
    { disableLosslessIntegers: true },
  );

  return driver;
}

function asNullableString(value: unknown): string | null {
  return value == null ? null : String(value);
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

export type CompanyProfile = {
  name: string;
  summary: string | null;
  industries: string[];
  leadership: string[];
};

export type NewsArticle = {
  title: string;
  date: string | null;
  source: string | null;
  summary: string | null;
};

export async function findCompanyProfile(company: string): Promise<CompanyProfile | null> {
  const { records } = await getDriver().executeQuery(
    `MATCH (o:Organization)
     WHERE toLower(o.name) = toLower($company)
     RETURN o.name AS name,
            o.summary AS summary,
            [(o)-[:HAS_CATEGORY|IN_INDUSTRY]->(industry)
              WHERE industry.name IS NOT NULL | industry.name][..10] AS industries,
            ([(o)-[:HAS_CEO|HAS_BOARD_MEMBER]->(leader:Person)
              WHERE leader.name IS NOT NULL | leader.name] +
             [(o)<-[:WORKS_FOR]-(employee:Person)
              WHERE employee.name IS NOT NULL | employee.name])[..10] AS leadership
     LIMIT 1`,
    { company },
    { database: process.env.NEO4J_DATABASE ?? DEFAULT_NEO4J_DATABASE },
  );

  const record = records[0];
  if (!record) return null;

  return {
    name: String(record.get('name')),
    summary: asNullableString(record.get('summary')),
    industries: asStringList(record.get('industries')),
    leadership: asStringList(record.get('leadership')),
  };
}

export async function findRecentCompanyNews(
  company: string,
  limit: number,
): Promise<NewsArticle[]> {
  const { records } = await getDriver().executeQuery(
    `MATCH (a:Article)-[:MENTIONS]->(o:Organization)
     WHERE toLower(o.name) = toLower($company)
     WITH DISTINCT a
     RETURN coalesce(a.title, '(untitled)') AS title,
            toString(a.date) AS date,
            a.siteName AS source,
            a.summary AS summary
     ORDER BY a.date DESC
     LIMIT $limit`,
    { company, limit: neo4j.int(limit) },
    { database: process.env.NEO4J_DATABASE ?? DEFAULT_NEO4J_DATABASE },
  );

  return records.map((record) => ({
    title: String(record.get('title')),
    date: asNullableString(record.get('date')),
    source: asNullableString(record.get('source')),
    summary: asNullableString(record.get('summary')),
  }));
}

export const queryCompanyProfile = defineTool({
  name: 'query_company_profile',
  description:
    'Look up one company in Neo4j. Returns its summary, industries, and known leadership. Use an exact company name.',
  input: v.object({
    company: v.pipe(v.string(), v.minLength(1)),
  }),
  async run({ data }) {
    return { output: await findCompanyProfile(data.company) };
  },
});

export const searchCompanyNews = defineTool({
  name: 'search_company_news',
  description:
    'Find the most recently dated news articles stored in Neo4j that mention one company. Returns titles, dates, sources, and summaries.',
  input: v.object({
    company: v.pipe(v.string(), v.minLength(1)),
    limit: v.optional(
      v.pipe(v.number(), v.integer(), v.minValue(1), v.maxValue(10)),
      5,
    ),
  }),
  async run({ data }) {
    return { output: await findRecentCompanyNews(data.company, data.limit) };
  },
});

export async function closeNeo4j(): Promise<void> {
  await driver?.close();
  driver = undefined;
}
