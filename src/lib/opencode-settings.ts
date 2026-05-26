/**
 * OpenCode settings helpers backed by the shared SQLite DB.
 * Stores settings in app_settings table (key TEXT PRIMARY KEY, value TEXT).
 */
import { sqliteDb } from './gemini.js';

// Ensure the settings table exists
sqliteDb.exec(`
  CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
  )
`);

/**
 * Read a setting value. Returns null if not set.
 */
export function getSetting(key: string): string | null {
  const row = sqliteDb.prepare('SELECT value FROM app_settings WHERE key = ?').get(key) as
    | { value: string }
    | undefined;
  return row?.value ?? null;
}

/**
 * Write a setting value. Pass null to delete.
 */
export function setSetting(key: string, value: string | null): void {
  if (value === null) {
    sqliteDb.prepare('DELETE FROM app_settings WHERE key = ?').run(key);
  } else {
    sqliteDb.prepare('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)').run(key, value);
  }
}

/**
 * Get configured OpenCode server URLs.
 * Stored as newline-separated URLs in `opencode_servers`.
 */
export function getOpenCodeServers(): string[] {
  const raw = getSetting('opencode_servers');
  if (!raw) return [];
  return raw
    .split('\n')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

/**
 * Get the configured OpenCode text model.
 * Falls back to env OPENCODE_MODEL, then 'opencode/deepseek-v4-flash-free'.
 */
export function getOpenCodeModel(): string {
  return (
    getSetting('opencode_text_model') ??
    process.env.OPENCODE_MODEL ??
    'opencode/deepseek-v4-flash-free'
  );
}
