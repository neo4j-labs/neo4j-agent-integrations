import { z } from 'zod';

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

describe('memorySavePayloadSchema', () => {
  it('accepts a minimal valid payload', () => {
    const result = memorySavePayloadSchema.safeParse({
      title: 'Test',
      content: 'Test content',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.kind).toBe('episodic');
      expect(result.data.polarity).toBe('positive');
    }
  });

  it('rejects missing title', () => {
    const result = memorySavePayloadSchema.safeParse({
      content: 'Test content',
    });
    expect(result.success).toBe(false);
  });

  it('rejects missing content', () => {
    const result = memorySavePayloadSchema.safeParse({
      title: 'Test',
    });
    expect(result.success).toBe(false);
  });

  it('trims whitespace from title and content', () => {
    const result = memorySavePayloadSchema.safeParse({
      title: '  Test  ',
      content: '  Test content  ',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.title).toBe('Test');
      expect(result.data.content).toBe('Test content');
    }
  });

  it('validates confidence bounds', () => {
    const tooHigh = memorySavePayloadSchema.safeParse({
      title: 'Test',
      content: 'Content',
      confidence: 1.5,
    });
    expect(tooHigh.success).toBe(false);

    const valid = memorySavePayloadSchema.safeParse({
      title: 'Test',
      content: 'Content',
      confidence: 0.5,
    });
    expect(valid.success).toBe(true);
  });

  it('validates tags', () => {
    const result = memorySavePayloadSchema.safeParse({
      title: 'Test',
      content: 'Content',
      tags: ['demo', 'test', 'valid'],
    });
    expect(result.success).toBe(true);

    const tooMany = memorySavePayloadSchema.safeParse({
      title: 'Test',
      content: 'Content',
      tags: Array.from({ length: 11 }, (_, i) => `tag${i}`),
    });
    expect(tooMany.success).toBe(false);
  });
});
