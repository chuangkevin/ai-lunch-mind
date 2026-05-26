/**
 * OpenCode HTTP client for text generation.
 *
 * Uses the OpenCode session API directly:
 *   POST   {server}/session                  → create session, get { id }
 *   POST   {server}/session/{id}/message     → send message, get response parts
 *   DELETE {server}/session/{id}             → cleanup (fire-and-forget)
 *
 * Model format: "{providerID}/{modelID}" e.g. "opencode/deepseek-v4-flash-free"
 */
import { getOpenCodeServers, getOpenCodeModel } from './opencode-settings.js';

const OPENCODE_SERVER_PASSWORD = process.env.OPENCODE_SERVER_PASSWORD;
const REQUEST_TIMEOUT_MS = 60_000;

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (OPENCODE_SERVER_PASSWORD) {
    const encoded = Buffer.from(`opencode:${OPENCODE_SERVER_PASSWORD}`).toString('base64');
    headers['Authorization'] = `Basic ${encoded}`;
  }
  return headers;
}

function parseModel(model: string): { providerID: string; id: string } {
  const sep = model.indexOf('/');
  if (sep > 0 && sep < model.length - 1) {
    return { providerID: model.slice(0, sep), id: model.slice(sep + 1) };
  }
  return { providerID: 'opencode', id: model };
}

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

interface SessionResponse {
  id?: string;
}

interface TextPart {
  type: 'text';
  text: string;
  synthetic?: boolean;
}

interface MessageResponse {
  parts?: Array<{ type: string; text?: string; synthetic?: boolean }>;
}

async function callOpenCode(
  serverUrl: string,
  model: string,
  prompt: string,
  systemInstruction?: string,
): Promise<string> {
  const trimmedUrl = serverUrl.replace(/\/+$/, '');
  const modelRef = parseModel(model);
  const headers = buildHeaders();

  // 1. Create session
  const sessionRes = await fetchWithTimeout(
    `${trimmedUrl}/session`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({
        title: 'ai-lunch-mind session',
        agent: 'general',
        model: { id: modelRef.id, providerID: modelRef.providerID, variant: 'default' },
      }),
    },
    REQUEST_TIMEOUT_MS,
  );

  if (!sessionRes.ok) {
    const text = await sessionRes.text();
    throw new Error(`OpenCode create session failed (${sessionRes.status}): ${text}`);
  }

  const sessionJson = (await sessionRes.json()) as SessionResponse;
  if (!sessionJson.id) {
    throw new Error('OpenCode create session: missing id in response');
  }
  const sessionId = sessionJson.id;

  try {
    // 2. Send message
    const msgRes = await fetchWithTimeout(
      `${trimmedUrl}/session/${encodeURIComponent(sessionId)}/message`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({
          agent: 'general',
          model: { modelID: modelRef.id, providerID: modelRef.providerID },
          ...(systemInstruction ? { system: systemInstruction } : {}),
          parts: [{ type: 'text', text: prompt }],
        }),
      },
      REQUEST_TIMEOUT_MS,
    );

    if (!msgRes.ok) {
      const text = await msgRes.text();
      throw new Error(`OpenCode send message failed (${msgRes.status}): ${text}`);
    }

    const msgJson = (await msgRes.json()) as MessageResponse;
    const text = (msgJson.parts ?? [])
      .filter((p): p is TextPart => p.type === 'text' && !p.synthetic)
      .map((p) => p.text)
      .join('');

    return text;
  } finally {
    // 3. Cleanup session (fire and forget)
    fetch(`${trimmedUrl}/session/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
      headers,
    }).catch((err: unknown) => {
      console.warn('[opencode] deleteSession failed:', err);
    });
  }
}

/**
 * Try to call OpenCode for text generation.
 * Returns null if no servers are configured or if the call fails.
 */
export async function tryOpenCodeText(
  prompt: string,
  systemInstruction?: string,
): Promise<string | null> {
  const servers = getOpenCodeServers();
  if (servers.length === 0) return null;

  const model = getOpenCodeModel();

  for (const server of servers) {
    try {
      const result = await callOpenCode(server, model, prompt, systemInstruction);
      if (result) return result;
    } catch (err) {
      console.warn(`[opencode] server ${server} failed:`, err);
      // Try next server
    }
  }

  return null;
}
