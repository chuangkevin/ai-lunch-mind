/**
 * Gemini AI wrapper using @kevinsisi/ai-core
 *
 * API (from @kevinsisi/ai-core v1.1.0):
 *   - KeyPool(adapter, options?) — manages key allocation/rotation
 *   - SqliteAdapter(db)         — SQLite StorageAdapter implementation
 *   - GeminiClient(pool, opts?) — generates content via Gemini API
 *   - withRetry(fn, initialKey, opts?) — standalone retry utility
 */
import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';
import { KeyPool, GeminiClient, SqliteAdapter } from '@kevinsisi/ai-core';

const DB_PATH = process.env.CACHE_DB_PATH
  ? path.resolve(process.env.CACHE_DB_PATH)
  : path.join(process.cwd(), 'data', 'cache.db');

// Ensure data directory exists
const dbDir = path.dirname(DB_PATH);
if (!fs.existsSync(dbDir)) fs.mkdirSync(dbDir, { recursive: true });

// Shared SQLite connection (WAL mode for concurrent reads)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const sqliteDb: any = new Database(DB_PATH);
sqliteDb.pragma('journal_mode = WAL');
sqliteDb.pragma('synchronous = NORMAL');

// Initialize api_keys table schema
SqliteAdapter.createTable(sqliteDb);

// Build the pool and client
const adapter = new SqliteAdapter(sqliteDb);
export const keyPool = new KeyPool(adapter);
export const geminiClient = new GeminiClient(keyPool);

const MODEL = 'gemini-2.5-flash';

/**
 * Call Gemini and parse the response as JSON of type T.
 * System instruction includes a reminder to return plain JSON.
 */
export async function generateJSON<T>(
  prompt: string,
  systemInstruction: string,
): Promise<T> {
  const resp = await geminiClient.generateContent({
    model: MODEL,
    systemInstruction:
      systemInstruction +
      '\n\n回應必須是有效的 JSON，不要有任何 Markdown 格式（不要 ```json）或額外文字。',
    prompt,
  });
  // Strip markdown fences if model still adds them
  const cleaned = resp.text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  return JSON.parse(cleaned) as T;
}

/**
 * Call Gemini and return plain text response.
 */
export async function generateText(
  prompt: string,
  systemInstruction?: string,
): Promise<string> {
  const resp = await geminiClient.generateContent({
    model: MODEL,
    systemInstruction,
    prompt,
  });
  return resp.text;
}
