/**
 * OpenCode settings endpoints.
 *
 * GET    /api/settings/opencode           → current settings + sources
 * POST   /api/settings/opencode           → save servers/text_model
 * DELETE /api/settings/opencode           → clear all opencode settings
 * GET    /api/settings/opencode/models    → model list from first configured server
 */
import { Router, Request, Response } from 'express';
import { getSetting, setSetting, getOpenCodeServers } from '../lib/opencode-settings.js';

type FetchResponse = Awaited<ReturnType<typeof fetch>>;

const router = Router();

const SHOW_PROVIDERS = new Set(['opencode', 'openai', 'github-copilot', 'google', 'anthropic']);
const MODELS_TIMEOUT_MS = 10_000;
const OPENCODE_SERVER_PASSWORD = process.env.OPENCODE_SERVER_PASSWORD;

function buildAuthHeader(): Record<string, string> {
  if (OPENCODE_SERVER_PASSWORD) {
    const encoded = Buffer.from(`:${OPENCODE_SERVER_PASSWORD}`).toString('base64');
    return { Authorization: `Basic ${encoded}` };
  }
  return {};
}

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<FetchResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/** GET /api/settings/opencode — read current settings */
router.get('/api/settings/opencode', (_req: Request, res: Response) => {
  try {
    const serversRaw = getSetting('opencode_servers');
    const textModelRaw = getSetting('opencode_text_model');

    res.json({
      servers: serversRaw ?? '',
      servers_source: serversRaw !== null ? 'db' : 'none',
      text_model: textModelRaw ?? process.env.OPENCODE_MODEL ?? 'opencode/deepseek-v4-flash-free',
      text_model_source:
        textModelRaw !== null
          ? 'db'
          : process.env.OPENCODE_MODEL
            ? 'env'
            : 'default',
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

/** POST /api/settings/opencode — save settings */
router.post('/api/settings/opencode', (req: Request, res: Response) => {
  try {
    const body = req.body as { servers?: string; text_model?: string };

    if (typeof body.servers === 'string') {
      const trimmed = body.servers.trim();
      setSetting('opencode_servers', trimmed.length > 0 ? trimmed : null);
    }

    if (typeof body.text_model === 'string') {
      const trimmed = body.text_model.trim();
      setSetting('opencode_text_model', trimmed.length > 0 ? trimmed : null);
    }

    // Return updated settings
    const serversRaw = getSetting('opencode_servers');
    const textModelRaw = getSetting('opencode_text_model');

    res.json({
      ok: true,
      servers: serversRaw ?? '',
      servers_source: serversRaw !== null ? 'db' : 'none',
      text_model: textModelRaw ?? process.env.OPENCODE_MODEL ?? 'opencode/deepseek-v4-flash-free',
      text_model_source:
        textModelRaw !== null
          ? 'db'
          : process.env.OPENCODE_MODEL
            ? 'env'
            : 'default',
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

/** DELETE /api/settings/opencode — clear all opencode settings */
router.delete('/api/settings/opencode', (_req: Request, res: Response) => {
  try {
    setSetting('opencode_servers', null);
    setSetting('opencode_text_model', null);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

interface ProviderInfo {
  id: string;
  name?: string;
  models?: Array<{
    id: string;
    name?: string;
    cost?: { input?: number; output?: number };
  }>;
}

/** GET /api/settings/opencode/models — fetch model list from first server */
router.get('/api/settings/opencode/models', async (_req: Request, res: Response) => {
  try {
    const servers = getOpenCodeServers();
    if (servers.length === 0) {
      res.json({ groups: [], server: null });
      return;
    }

    const serverUrl = servers[0].replace(/\/+$/, '');
    const authHeader = buildAuthHeader();

    // Fetch providers and auth info in parallel
    let providers: ProviderInfo[] = [];
    // /provider/auth returns a dict of providers that NEED auth; absent = already authed
    let needsAuthIds = new Set<string>();

    try {
      const [providerRes, authRes] = await Promise.all([
        fetchWithTimeout(`${serverUrl}/provider`, { headers: authHeader }, MODELS_TIMEOUT_MS),
        fetchWithTimeout(`${serverUrl}/provider/auth`, { headers: authHeader }, MODELS_TIMEOUT_MS).catch(() => null),
      ]);

      if (providerRes.ok) {
        const data = (await providerRes.json()) as { all?: ProviderInfo[]; providers?: ProviderInfo[] } | ProviderInfo[];
        if (Array.isArray(data)) {
          providers = data;
        } else {
          providers = data.all ?? data.providers ?? [];
        }
      }

      if (authRes?.ok) {
        const authData = (await authRes.json()) as Record<string, unknown>;
        needsAuthIds = new Set(Object.keys(authData));
      }
    } catch {
      // If server is unreachable, return empty
      res.json({ groups: [], server: null });
      return;
    }

    const groups = providers
      .filter((p) => SHOW_PROVIDERS.has(p.id))
      .map((p) => ({
        provider: p.id,
        name: p.name ?? p.id,
        authed: !needsAuthIds.has(p.id),
        models: (p.models ?? []).map((m) => ({
          id: `${p.id}/${m.id}`,
          name: m.name ?? m.id,
          free: m.cost?.input === 0,
        })),
      }))
      .filter((g) => g.models.length > 0);

    res.json({
      groups,
      server: { id: 'server-1', label: 'Server 1', base_url: serverUrl },
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

export default router;
