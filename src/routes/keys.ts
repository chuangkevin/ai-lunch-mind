/**
 * Gemini API key management endpoints.
 * Uses @kevinsisi/ai-core KeyPool + SqliteAdapter.
 */
import { Router, Request, Response } from 'express';
import { keyPool, sqliteDb } from '../lib/gemini.js';

const router = Router();

// Only accept Google API keys (AIza prefix, min 20 chars)
const KEY_PREFIX = 'AIza';
const KEY_MIN_LENGTH = 20;

function isValidKey(k: string): boolean {
  return k.startsWith(KEY_PREFIX) && k.length >= KEY_MIN_LENGTH;
}

/** POST /api/keys/import — bulk import keys from textarea text */
router.post('/api/keys/import', async (req: Request, res: Response) => {
  try {
    const { keys = '' } = req.body as { keys?: string; validate?: boolean };

    // Parse keys: one per line, or comma/space separated
    const lines = (keys as string)
      .split(/[\n\r,\s]+/)
      .map((l) => l.trim())
      .filter(Boolean);
    const validKeys = lines.filter(isValidKey);
    const invalidCount = lines.length - validKeys.length;

    let added = 0;
    let skipped = 0;

    const insert = sqliteDb.prepare('INSERT OR IGNORE INTO api_keys (key) VALUES (?)');
    for (const key of validKeys) {
      try {
        const info = insert.run(key) as { changes: number };
        if (info.changes > 0) {
          added++;
        } else {
          skipped++; // Already exists
        }
      } catch {
        skipped++;
      }
    }

    // Invalidate pool cache so new keys are picked up
    keyPool.invalidate();

    res.json({
      added,
      skipped,
      invalid: invalidCount,
      total: validKeys.length,
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

/** GET /api/keys/status — list all keys (suffix only, never full key) */
router.get('/api/keys/status', async (_req: Request, res: Response) => {
  try {
    const keys = await keyPool.status();
    const now = Date.now();
    res.json({
      keys: keys.map((k) => ({
        suffix: k.key.slice(-4),
        is_active: k.isActive,
        in_cooldown: k.cooldownUntil > now,
        cooldown_until: k.cooldownUntil || null,
        usage_count: k.usageCount,
      })),
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

/** DELETE /api/keys/:suffix — permanently block a key by its last 4 chars */
router.delete('/api/keys/:suffix', async (req: Request, res: Response) => {
  try {
    const { suffix } = req.params;
    const keys = await keyPool.status();
    const match = keys.find((k) => k.key.endsWith(suffix));
    if (!match) {
      res.status(404).json({ error: `找不到後綴為 ${suffix} 的金鑰` });
      return;
    }
    await keyPool.block(match.key);
    res.json({ status: 'ok', detail: `已刪除後綴為 ${suffix} 的金鑰` });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

/** GET /api/keys/usage — usage statistics */
router.get('/api/keys/usage', async (_req: Request, res: Response) => {
  try {
    const keys = await keyPool.status();
    const now = Date.now();
    res.json({
      total: keys.length,
      active: keys.filter((k) => k.isActive && k.cooldownUntil <= now).length,
      in_cooldown: keys.filter((k) => k.isActive && k.cooldownUntil > now).length,
      blocked: keys.filter((k) => !k.isActive).length,
      total_usage: keys.reduce((sum, k) => sum + k.usageCount, 0),
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

export default router;
