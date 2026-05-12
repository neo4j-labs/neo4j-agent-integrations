import { NextRequest, NextResponse } from 'next/server';
import { convertToModelMessages, streamText, tool, type UIMessage } from 'ai';
import { google } from '@ai-sdk/google';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import neo4j from 'neo4j-driver';
import {
  getMemoryService,
  getMemoryConfigSourceLabel,
  isMemoryConfigured,
} from '../../../lib/memoryService';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const DEMO_AGENT_ID = process.env.DEMO_AGENT_ID || 'vercel-neo4j-demo';

const memorySavePayloadSchema = z.object({
  title: z.string().min(1).transform((value) => value.trim()).pipe(z.string().min(1)),
  content: z.string().min(1).transform((value) => value.trim()).pipe(z.string().min(1)),
  kind: z.enum(['semantic', 'procedural', 'episodic']).optional().default('episodic'),
  polarity: z.enum(['positive', 'negative']).optional().default('positive'),
  confidence: z.number().min(0).max(1).optional().default(0.65),
  utility: z.number().min(0).max(1).optional().default(0.4),
  tags: z
    .array(z.string().transform((tag) => tag.trim()).pipe(z.string().min(2)))
    .max(10)
    .optional(),
});

function extractTags(text: string): string[] {
  const words = text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((word) => word.trim())
    .filter((word) => word.length >= 4);

  const tags = Array.from(new Set(words)).slice(0, 8);
  return tags.length > 0 ? tags : ['demo'];
}

function getMessageText(message: UIMessage | undefined): string {
  if (!message) return '';
  const candidate = message as unknown as {
    content?: unknown;
    parts?: Array<{ type?: string; text?: string }>;
  };

  if (typeof candidate.content === 'string') {
    return candidate.content;
  }

  if (Array.isArray(candidate.parts)) {
    return candidate.parts
      .filter((part) => part?.type === 'text' && typeof part?.text === 'string')
      .map((part) => part.text || '')
      .join('\n')
      .trim();
  }

  return '';
}

function getLatestUserMessage(messages: UIMessage[]): UIMessage | undefined {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i]?.role === 'user') {
      return messages[i];
    }
  }
  return undefined;
}

function pickModel() {
  const preferredModel = process.env.AI_MODEL;
  const providerPreference = (process.env.AI_PROVIDER || '').toLowerCase();

  if (providerPreference === 'openai' && process.env.OPENAI_API_KEY) {
    return {
      provider: 'openai',
      modelName: preferredModel || 'gpt-4o-mini',
      model: openai(preferredModel || 'gpt-4o-mini'),
    };
  }

  if (providerPreference === 'google' && process.env.GOOGLE_GENERATIVE_AI_API_KEY) {
    return {
      provider: 'google',
      modelName: preferredModel || 'gemini-2.5-flash',
      model: google(preferredModel || 'gemini-2.5-flash'),
    };
  }

  if (process.env.OPENAI_API_KEY) {
    return {
      provider: 'openai',
      modelName: preferredModel || 'gpt-4o-mini',
      model: openai(preferredModel || 'gpt-4o-mini'),
    };
  }

  if (process.env.GOOGLE_GENERATIVE_AI_API_KEY) {
    return {
      provider: 'google',
      modelName: preferredModel || 'gemini-2.5-flash',
      model: google(preferredModel || 'gemini-2.5-flash'),
    };
  }

  throw new Error('No model provider configured. Set OPENAI_API_KEY or GOOGLE_GENERATIVE_AI_API_KEY.');
}

function getNeo4jDriver() {
  const uri = process.env.NEO4J_URI || 'neo4j+s://demo.neo4jlabs.com:7687';
  const username = process.env.NEO4J_USERNAME || 'companies';
  const password = process.env.NEO4J_PASSWORD || 'companies';
  const database = process.env.NEO4J_DATABASE || 'companies';

  return {
    driver: neo4j.driver(uri, neo4j.auth.basic(username, password), {
      disableLosslessIntegers: true,
    }),
    database,
  };
}

export async function GET() {
  let modelProvider = 'unavailable';
  let modelName = 'unavailable';
  try {
    const selectedModel = pickModel();
    modelProvider = selectedModel.provider;
    modelName = selectedModel.modelName;
  } catch {
    // Handled by status payload
  }

  return NextResponse.json({
    ok: true,
    modelProvider,
    modelName,
    agentId: DEMO_AGENT_ID,
    memoryEnabled: isMemoryConfigured(),
    memoryConfigSource: getMemoryConfigSourceLabel(),
  });
}

export async function POST(request: NextRequest) {
  const { driver, database } = getNeo4jDriver();

  try {
    const body = await request.json();
    const messages = (body?.messages || []) as UIMessage[];

    if (!Array.isArray(messages) || messages.length === 0) {
      return NextResponse.json({ error: 'messages[] is required' }, { status: 400 });
    }

    const selectedModel = pickModel();
    const memoryService = await getMemoryService();

    const latestUserMessage = getLatestUserMessage(messages);
    const latestUserText = getMessageText(latestUserMessage);

    let memoryContext = 'No prior context found.';
    if (memoryService && latestUserText) {
      try {
        const contextBundle = await memoryService.retrieveContextBundle({
          agentId: DEMO_AGENT_ID,
          prompt: latestUserText,
          tags: extractTags(latestUserText),
          fallback: {
            enabled: true,
            useFulltext: true,
            useTags: true,
            useVector: false,
          },
        });

        const parts = [contextBundle.injection.fixBlock, contextBundle.injection.doNotDoBlock].filter(
          Boolean
        );
        if (parts.length > 0) {
          memoryContext = parts.join('\n\n');
        }
      } catch (error) {
        console.warn('[chat] Failed to retrieve memory context:', error);
      }
    }

    const result = streamText({
      model: selectedModel.model,
      system: [
        'You are a helpful Neo4j research assistant built with Vercel AI SDK.',
        'Use the query_neo4j tool to search the companies knowledge graph.',
        'Provide insightful analysis and remember key findings for future queries.',
        '',
        memoryService ? `Recent context from memory:\n${memoryContext}` : '',
      ]
        .filter(Boolean)
        .join('\n'),
      messages: convertToModelMessages(messages),
      maxSteps: 6,
      tools: {
        query_neo4j: tool({
          description:
            'Search organizations in the Neo4j companies knowledge graph by keyword or property. Returns organizations with details like industry, location, and article mentions.',
          inputSchema: z.object({
            query: z
              .string()
              .min(2)
              .describe(
                'A natural language query like "tech companies in california" or "organizations in finance industry"'
              ),
          }),
          execute: async ({ query }) => {
            const session = driver.session({ database });
            try {
              const result = await session.run(
                `MATCH (org:Organization) WHERE org.name CONTAINS $query OR org.summary CONTAINS $query
                 RETURN org.name AS name, org.summary AS summary, org.industry AS industry LIMIT 5`,
                { query: query.toUpperCase() }
              );

              const records = result.records.map((record: any) => ({
                name: record.get('name'),
                summary: record.get('summary'),
                industry: record.get('industry'),
              }));

              return {
                count: records.length,
                results: records,
              };
            } finally {
              await session.close();
            }
          },
        }),
        save_learning: tool({
          description:
            'Save important findings to Neo4j Agent Memory for future queries. Use this to store research insights, patterns, or best practices.',
          inputSchema: z.object({
            title: z.string().min(4),
            content: z.string().min(8),
            kind: z.enum(['semantic', 'procedural', 'episodic']).default('semantic'),
          }),
          execute: async ({ title, content, kind }) => {
            if (!memoryService) {
              return {
                success: false,
                message: 'Memory service not configured',
              };
            }

            try {
              const saveResult = await memoryService.captureUsefulLearning({
                agentId: DEMO_AGENT_ID,
                useful: true,
                learning: {
                  title,
                  content,
                  kind,
                  tags: extractTags(`${title} ${content}`),
                },
              });

              return {
                success: true,
                saved: saveResult.saved,
              };
            } catch (error) {
              console.error('[chat] Memory save failed:', error);
              return {
                success: false,
                message: error instanceof Error ? error.message : 'Failed to save learning',
              };
            }
          },
        }),
      },
    });

    return result.toUIMessageStreamResponse({
      headers: {
        'x-model-provider': selectedModel.provider,
        'x-model-name': selectedModel.modelName,
        'x-memory-enabled': String(Boolean(memoryService)),
      },
    });
  } catch (error) {
    console.error('[chat] Failed:', error);
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : 'Failed to process chat request',
      },
      { status: 500 }
    );
  } finally {
    await driver.close();
  }
}

export async function PUT(request: NextRequest) {
  try {
    const memoryService = await getMemoryService();
    if (!memoryService) {
      return NextResponse.json(
        {
          ok: false,
          error: 'Memory service not configured',
        },
        { status: 400 }
      );
    }

    const body = await request.json();
    const parsed = memorySavePayloadSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        {
          ok: false,
          error: 'Invalid payload',
          details: parsed.error.flatten(),
        },
        { status: 400 }
      );
    }

    const { title, content, kind, polarity, confidence, utility, tags = [] } = parsed.data;

    const result = await memoryService.captureUsefulLearning({
      agentId: DEMO_AGENT_ID,
      useful: true,
      learning: {
        title,
        content,
        kind,
        polarity,
        confidence,
        utility,
        tags: tags.length > 0 ? tags : extractTags(`${title} ${content}`),
      },
    });

    return NextResponse.json({
      ok: true,
      result,
    });
  } catch (error) {
    console.error('[chat] Memory save failed:', error);
    return NextResponse.json(
      {
        ok: false,
        error: error instanceof Error ? error.message : 'Failed to save memory',
      },
      { status: 500 }
    );
  }
}
