import { NextRequest, NextResponse } from 'next/server';
import { convertToModelMessages, stepCountIs, streamText, tool, type UIMessage } from 'ai';
import { google } from '@ai-sdk/google';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';
import neo4j from 'neo4j-driver';
import {
  getMemoryClient,
  getDemoConversationId,
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

// NAMS accepts: person, organization, location, concept, tool, custom
function toNamsEntityType(kind: string): string {
  const map: Record<string, string> = {
    semantic: 'concept',
    procedural: 'custom',
    episodic: 'custom',
    concept: 'concept',
    person: 'person',
    organization: 'organization',
    location: 'location',
    tool: 'tool',
    custom: 'custom',
  };
  return map[kind] ?? 'custom';
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
    const memoryClient = getMemoryClient();
    const conversationId = await getDemoConversationId();

    const latestUserMessage = getLatestUserMessage(messages);
    const latestUserText = getMessageText(latestUserMessage);

    // Persist the user message to short-term memory
    if (memoryClient && conversationId && latestUserText) {
      try {
        await memoryClient.shortTerm.addMessage(conversationId, 'user', latestUserText);
      } catch (error) {
        console.warn('[chat] Failed to persist user message:', error);
      }
    }

    // Retrieve memory context: short-term (reflections/observations) + long-term (entities)
    let memoryContext = 'No prior context found.';
    if (memoryClient && conversationId && latestUserText) {
      try {
        const contextParts: string[] = [];

        const ctx = await memoryClient.shortTerm.getContext(conversationId);
        if (ctx.reflections.length > 0) {
          contextParts.push(
            'Key insights:\n' + ctx.reflections.map((r) => `- ${r.content}`).join('\n'),
          );
        }
        if (ctx.observations.length > 0) {
          contextParts.push(
            'Recent observations:\n' + ctx.observations.map((o) => `- ${o.content}`).join('\n'),
          );
        }
        if (ctx.recentMessages.length > 0) {
          contextParts.push(
            'Recent messages:\n' +
              ctx.recentMessages.map((m) => `${m.role}: ${m.content}`).join('\n'),
          );
        }

        // Search long-term entity memory for relevant knowledge
        const entities = await memoryClient.longTerm.searchEntities(latestUserText, { limit: 5 });
        if (entities.length > 0) {
          contextParts.push(
            'Related knowledge from memory:\n' +
              entities
                .map((e) => `- ${e.name}${e.description ? ': ' + e.description : ''}`)
                .join('\n'),
          );
        }

        if (contextParts.length > 0) {
          memoryContext = contextParts.join('\n\n');
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
        memoryClient ? `Recent context from memory:\n${memoryContext}` : '',
      ]
        .filter(Boolean)
        .join('\n'),
      messages: convertToModelMessages(messages),
      stopWhen: stepCountIs(6),
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
            if (!memoryClient) {
              return {
                success: false,
                message: 'Memory service not configured',
              };
            }

            try {
              const entity = await memoryClient.longTerm.addEntity(title, toNamsEntityType(kind), {
                description: content,
              });

              return {
                success: true,
                saved: true,
                id: entity.id,
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
      onFinish: async ({ text }) => {
        // Persist the assistant response to short-term memory
        if (memoryClient && conversationId && text) {
          try {
            await memoryClient.shortTerm.addMessage(conversationId, 'assistant', text);
          } catch (error) {
            console.warn('[chat] Failed to persist assistant response:', error);
          }
        }
      },
    });

    return result.toUIMessageStreamResponse({
      headers: {
        'x-model-provider': selectedModel.provider,
        'x-model-name': selectedModel.modelName,
        'x-memory-enabled': String(Boolean(memoryClient)),
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
    const memoryClient = getMemoryClient();
    if (!memoryClient) {
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

    const { title, content, kind } = parsed.data;

    const entity = await memoryClient.longTerm.addEntity(title, toNamsEntityType(kind), {
      description: content,
    });

    // Also persist as a short-term message so it appears in conversation context
    const conversationId = await getDemoConversationId();
    if (conversationId) {
      try {
        await memoryClient.shortTerm.addMessage(
          conversationId,
          'assistant',
          `Saved research finding — ${title}: ${content}`,
        );
      } catch {
        // Non-fatal
      }
    }

    return NextResponse.json({
      ok: true,
      result: { id: entity.id, name: entity.name },
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
