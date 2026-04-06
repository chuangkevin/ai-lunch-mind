/**
 * AI Lunch Mind — Node.js/TypeScript Express server
 * Replaces the Python FastAPI main.py
 */
import express from 'express';
import cors from 'cors';
import path from 'path';

import chatRouter from './routes/chat.js';
import keysRouter from './routes/keys.js';
import { keyPool } from './lib/gemini.js';

const app = express();
const PORT = parseInt(process.env.PORT ?? '9113', 10);

// ── Middleware ───────────────────────────────────────────────────────────────
app.use(cors());
app.use(express.json());

// ── Static frontend files ────────────────────────────────────────────────────
const FRONTEND_DIR = path.join(__dirname, '..', 'frontend');
app.use('/static', express.static(FRONTEND_DIR));

// ── HTML page routes ─────────────────────────────────────────────────────────
app.get('/', (_req, res) => {
  res.sendFile(path.join(FRONTEND_DIR, 'ai_lunch_v2.html'));
});

app.get('/ai_lunch', (_req, res) => {
  res.sendFile(path.join(FRONTEND_DIR, 'ai_lunch_v2.html'));
});

app.get('/settings', (_req, res) => {
  res.sendFile(path.join(FRONTEND_DIR, 'settings.html'));
});

// ── API routes ───────────────────────────────────────────────────────────────
app.use('/', chatRouter);
app.use('/', keysRouter);

// ── Health check ─────────────────────────────────────────────────────────────
app.get('/health', async (_req, res) => {
  try {
    let geminiKeys = 0;
    try {
      const status = await keyPool.status();
      geminiKeys = Array.isArray(status) ? status.length : 0;
    } catch { /* key pool not yet initialised */ }

    res.json({
      status: 'healthy',
      service: 'AI Lunch Mind',
      version: '6.0.0',
      runtime: 'Node.js/TypeScript',
      cwb_api_key: process.env.CWB_API_KEY ? '已設置' : '未設置',
      gemini_keys: geminiKeys,
      endpoints: [
        '/chat-recommendation-stream?message=訊息 - SSE 串流推薦',
        '/api/keys/* - Gemini 金鑰管理',
        '/health',
      ],
      pages: ['/ - AI 午餐推薦', '/settings - 設定（金鑰管理）'],
    });
  } catch (e) {
    res.status(500).json({ error: (e as Error).message });
  }
});

// ── Start server ──────────────────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  console.log(`AI Lunch Mind (Node.js) 啟動中...`);
  console.log(`   • http://localhost:${PORT}/ - AI 午餐推薦`);
  console.log(`   • http://localhost:${PORT}/settings - 設定（金鑰管理）`);
  console.log(`   • http://localhost:${PORT}/health - 健康檢查`);
  if (!process.env.CWB_API_KEY) {
    console.warn('警告：CWB_API_KEY 未設置，天氣資料將無法取得');
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  const { closeBrowser } = await import('./modules/google-maps.js');
  await closeBrowser();
  process.exit(0);
});

process.on('SIGINT', async () => {
  const { closeBrowser } = await import('./modules/google-maps.js');
  await closeBrowser();
  process.exit(0);
});
