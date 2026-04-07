/**
 * Intent analyzer — pure Gemini AI, no regex or hardcode patterns.
 *
 * Analyzes user natural language input to extract:
 * - location, food keywords, budget, intent type
 *
 * No FOOD_PATTERNS, no location_patterns, no chain store lists.
 * All understanding is delegated to Gemini.
 */
import type { Intent, WeatherData } from '../types/index.js';
import { generateJSON } from '../lib/gemini.js';
import { cacheKey, cacheGet, cacheSet } from './cache.js';

const SYSTEM_PROMPT = `你是一個台灣餐廳推薦系統的意圖分析引擎。你的任務是分析使用者的自然語言輸入，並結合天氣與時間資訊，產出結構化的搜尋意圖。

## 核心原則

**使用者明確指定的食物類型永遠是最高優先級。** 天氣只是次要參考因素，絕對不能產生與使用者需求相衝突的搜尋關鍵字。例如，使用者說「想吃拉麵」，即使天氣炎熱，primary_keywords 和 secondary_keywords 仍應是拉麵相關詞彙，不可改成冰品或涼食。

## 你必須提取的欄位

1. **location** — 使用者提到的地點、地標、地址或區域名稱。若沒有提到地點，回傳 null。

2. **primary_keywords** — 使用者明確想吃的食物，2-4 個具體詞彙。若無指定食物，根據時段推薦 2-3 個合適的食物。

3. **secondary_keywords** — 與使用者需求相關的相似菜系或替代選項，2-3 個。不要因天氣而加入不相關的食物。

4. **budget** — 預算資訊。解析「200元以內」→ {"max": 200, "currency": "TWD"}。若未提到 → null。

5. **estimated_price_range** — 依據預算或食物類型推估：平價 / 中等 / 高價。

6. **search_radius_hint** — 搜尋半徑建議：近距離 / 中距離 / 遠距離可。

7. **intent** — 只能是以下四種之一：
   - "search_food_type" — 搜尋特定食物類型（最常見）
   - "location_query" — 詢問某地標附近有什麼吃的（沒有指定食物）
   - "search_specific_store" — 搜尋特定店名
   - "search_restaurants" — 泛用搜尋

8. **weather_hints** — 天氣對食物的輕微建議（僅供評分參考，不作為搜尋關鍵字），0-2 個。

## 回應格式

只能回傳一個有效的 JSON 物件，不要有任何多餘的文字、Markdown 或解釋：

{
  "location": "地點名稱或null",
  "primary_keywords": ["關鍵字1", "關鍵字2"],
  "secondary_keywords": ["替代1", "替代2"],
  "budget": {"min": null, "max": 200, "currency": "TWD"} 或 null,
  "estimated_price_range": "平價|中等|高價",
  "search_radius_hint": "近距離|中距離|遠距離可",
  "intent": "search_food_type|location_query|search_specific_store|search_restaurants",
  "weather_hints": []
}`;

function getTimePeriod(hour: number): string {
  if (hour >= 5 && hour < 10) return '早上';
  if (hour >= 10 && hour < 14) return '中午';
  if (hour >= 14 && hour < 17) return '下午';
  if (hour >= 17 && hour < 21) return '傍晚/晚上';
  return '深夜/宵夜時段';
}

function buildPrompt(userInput: string, weather: WeatherData | null, hour: number): string {
  const parts = [`使用者輸入：${userInput}`];
  parts.push(`目前時間：${hour}:00（${getTimePeriod(hour)}）`);

  if (weather) {
    const wParts: string[] = [];
    if (weather.temperature != null) wParts.push(`氣溫 ${weather.temperature}°C`);
    if (weather.humidity != null) wParts.push(`濕度 ${weather.humidity}%`);
    if (weather.sweat_index != null) wParts.push(`流汗指數 ${weather.sweat_index}`);
    if (weather.rain_probability != null) wParts.push(`降雨機率 ${weather.rain_probability}%`);
    if (wParts.length) parts.push(`天氣狀況：${wParts.join(', ')}`);
  } else {
    parts.push('天氣狀況：無資料');
  }

  return parts.join('\n');
}

function buildCacheKey(userInput: string, weather: WeatherData | null, hour: number): string {
  const period = hour >= 5 && hour < 10 ? 'morning'
    : hour >= 10 && hour < 14 ? 'lunch'
    : hour >= 14 && hour < 17 ? 'afternoon'
    : hour >= 17 && hour < 21 ? 'dinner'
    : 'late_night';
  const tempBucket = weather?.temperature != null ? Math.round(weather.temperature / 2) * 2 : 'x';
  const rainBucket = weather?.rain_probability != null ? Math.round(weather.rain_probability / 10) * 10 : 'x';
  return cacheKey('intent', userInput, period, String(tempBucket), String(rainBucket));
}

interface GeminiIntentResponse {
  location?: string | null;
  primary_keywords?: string[];
  secondary_keywords?: string[];
  budget?: { min?: number | null; max?: number | null; currency?: string } | null;
  estimated_price_range?: string;
  search_radius_hint?: string;
  intent?: string;
  weather_hints?: string[];
}

/**
 * Analyze user intent using Gemini AI.
 * Returns structured intent — no regex, no hardcode fallback.
 */
export async function analyzeIntent(
  userInput: string,
  weather: WeatherData | null = null,
  currentHour?: number,
): Promise<Intent> {
  const hour = currentHour ?? new Date().getHours();
  const ck = buildCacheKey(userInput, weather, hour);

  // Check cache
  const cached = cacheGet<Intent>(ck, 'intent');
  if (cached) {
    console.log('[intent] Cache hit:', userInput.slice(0, 40));
    return cached;
  }

  const prompt = buildPrompt(userInput, weather, hour);

  let parsed: GeminiIntentResponse;
  try {
    parsed = await generateJSON<GeminiIntentResponse>(prompt, SYSTEM_PROMPT);
  } catch (e) {
    console.error('[intent] Gemini failed:', e);
    // Fallback: preserve the user's raw input as the search keyword
    const fallback: Intent = {
      location: null,
      primary_keywords: [userInput],
      secondary_keywords: ['餐廳'],
      budget: null,
      estimated_price_range: '中等',
      search_radius_hint: '中距離',
      intent: 'search_food_type',
      weather_hints: [],
      raw_input: userInput,
      _source: 'fallback',
    };
    return fallback;
  }

  const primaryKeywords = (parsed.primary_keywords ?? []).slice(0, 4);

  // Ensure keywords explicitly mentioned in user input come first.
  // Prevents time-based keywords like "宵夜" from displacing user-specified foods.
  const userInputLower = userInput.toLowerCase();
  primaryKeywords.sort((a, b) => {
    const aInInput = userInputLower.includes(a.toLowerCase()) ? 0 : 1;
    const bInInput = userInputLower.includes(b.toLowerCase()) ? 0 : 1;
    return aInInput - bInInput;
  });

  const secondaryKeywords = (parsed.secondary_keywords ?? [])
    .filter((kw) => !primaryKeywords.includes(kw))
    .slice(0, 3);

  // Only pad with time-based defaults when Gemini returned NO keywords at all
  // (i.e. user gave no food hint). Never overwrite user-specified food keywords.
  if (primaryKeywords.length === 0) {
    const defaultsByHour = hour >= 5 && hour < 10
      ? ['早餐', '蛋餅']
      : hour >= 17
      ? ['熱炒', '便當']
      : ['便當', '小吃'];
    primaryKeywords.push(...defaultsByHour.slice(0, 2));
  }

  const result: Intent = {
    location: parsed.location ?? null,
    primary_keywords: primaryKeywords,
    secondary_keywords: secondaryKeywords,
    budget: parsed.budget ? {
      min: parsed.budget.min ?? null,
      max: parsed.budget.max ?? null,
      currency: parsed.budget.currency ?? 'TWD',
    } : null,
    estimated_price_range: parsed.estimated_price_range ?? '中等',
    search_radius_hint: parsed.search_radius_hint ?? '中距離',
    intent: parsed.intent ?? 'search_restaurants',
    weather_hints: parsed.weather_hints ?? [],
    raw_input: userInput,
    _source: 'gemini',
  };

  cacheSet(ck, 'intent', result);
  console.log(`[intent] location=${result.location} keywords=${result.primary_keywords.join(',')}`);
  return result;
}
