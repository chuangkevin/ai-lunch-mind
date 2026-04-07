/**
 * SQLite-based cache with TTL expiration.
 * Replicates the behavior of the Python sqlite_cache_manager.py module.
 */
import Database from 'better-sqlite3';
import { createHash } from 'crypto';
import path from 'path';
import fs from 'fs';

const DB_PATH = process.env.CACHE_DB_PATH
  ? path.resolve(process.env.CACHE_DB_PATH)
  : path.join(process.cwd(), 'data', 'cache.db');

// TTL constants (seconds)
export const TTL = {
  restaurant: 30 * 60,   // 30 minutes
  weather: 3 * 60 * 60,  // 3 hours
  intent: 60 * 60,       // 60 minutes
  geocoding: 24 * 60 * 60, // 24 hours
} as const;

type CacheType = keyof typeof TTL;

let _db: Database.Database | null = null;

function getDb(): Database.Database {
  if (!_db) {
    const dir = path.dirname(DB_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    _db = new Database(DB_PATH);
    _db.pragma('journal_mode = WAL');
    _db.pragma('synchronous = NORMAL');
    _db.exec(`
      CREATE TABLE IF NOT EXISTS cache_items (
        cache_key  TEXT    NOT NULL,
        cache_type TEXT    NOT NULL,
        value      TEXT    NOT NULL,
        expires_at REAL    NOT NULL,
        PRIMARY KEY (cache_key, cache_type)
      );
      CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache_items(expires_at);
    `);
  }
  return _db;
}

export function cacheKey(...parts: string[]): string {
  return createHash('sha256').update(parts.join('|')).digest('hex');
}

export function cacheGet<T>(key: string, type: CacheType): T | null {
  try {
    const db = getDb();
    const now = Date.now() / 1000;
    const row = db.prepare(
      'SELECT value FROM cache_items WHERE cache_key=? AND cache_type=? AND expires_at>?'
    ).get(key, type, now) as { value: string } | undefined;
    if (!row) return null;
    return JSON.parse(row.value) as T;
  } catch {
    return null;
  }
}

export function cacheSet<T>(key: string, type: CacheType, value: T): void {
  try {
    const db = getDb();
    const ttl = TTL[type];
    const expiresAt = Date.now() / 1000 + ttl;
    db.prepare(`
      INSERT OR REPLACE INTO cache_items (cache_key, cache_type, value, expires_at)
      VALUES (?, ?, ?, ?)
    `).run(key, type, JSON.stringify(value), expiresAt);
  } catch {
    // Cache write failure is non-fatal
  }
}

export function cacheCleanExpired(): void {
  try {
    const db = getDb();
    const now = Date.now() / 1000;
    db.prepare('DELETE FROM cache_items WHERE expires_at<=?').run(now);
  } catch {
    // ignore
  }
}
