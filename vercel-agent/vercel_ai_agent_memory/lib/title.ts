import { openai } from '@ai-sdk/openai';
import { generateText } from 'ai';

export async function generateTitle(firstMessage: string): Promise<string> {
  const prompt = `Generate a concise and meaningful descriptive title (4 to 8 words maximum) for the following chat conversation,
based primarily on the initial message. The title should capture the specific topic or request in the conversation.
Do not include any introductory phrases or extra text; just the title itself.

Example:
Question: What are the open issues with xyz customer
Title: Open issues with XYZ

Here is the first message:
${firstMessage}`;

  const result = await generateText({
    model: openai('gpt-4o-mini'),
    prompt,
    maxOutputTokens: 30,
  });

  return result.text.trim().replace(/["']/g, '');
}
