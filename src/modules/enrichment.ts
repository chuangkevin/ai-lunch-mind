/**
 * Gemini enrichment — adds recommendation reasons and fills missing fields.
 * NEVER adds new restaurants (anti-hallucination).
 * Only enriches existing Google Maps / Uber Eats results.
 */
import type { Restaurant, WeatherData, Budget } from '../types/index.js';
import { generateJSON } from '../lib/gemini.js';

interface EnrichedEntry {
  name: string;
  address?: string;
  rating?: number | null;
  price_level?: string | null;
  food_type?: string;
  reason?: string;
  remove?: boolean;
  is_new?: boolean;
}

export async function enrichWithGemini(
  restaurants: Restaurant[],
  userInput: string,
  location: string,
  keywords: string[],
  budget?: Budget | null,
  weather?: WeatherData | null,
): Promise<Restaurant[]> {
  if (restaurants.length === 0) return restaurants;

  const existingNames = restaurants.map((r) => r.name);

  const budgetHint = budget?.max ? `\n使用者預算：${budget.max}元以內` : '';
  const weatherHint =
    weather?.temperature != null
      ? `\n天氣：${weather.temperature}°C，流汗指數 ${weather.sweat_index ?? 'N/A'}`
      : '';

  const prompt = `你是台灣餐廳專家。使用者在 ${location} 想吃【${keywords.join('、')}】。${budgetHint}${weatherHint}

我已搜尋到以下餐廳：
${JSON.stringify(existingNames, null, 2)}

請做兩件事：
1. 移除不符合的項目，設 "remove": true，條件如下（符合任一即移除）：
   a. 完全不是餐廳/食物場所（辦公大樓、公園、捷運站、便利商店等）
   b. 與使用者要求的食物類型【${keywords.join('、')}】明顯無關（例如使用者要拉麵，卻出現韓式烤肉、漢堡、麵包店）
2. 為保留的餐廳補充資訊（地址、評分、價格、推薦理由）

判斷食物相關性的原則：
- 使用者指定的食物關鍵字是最高優先——相同或相似料理類型才保留
- 「相似」例子：搜拉麵 → 保留拉麵店、日式麵食；搜便當 → 保留便當店、快餐
- 「明顯無關」例子：搜拉麵 → 移除韓式烤肉、印度料理、早餐店、麥當勞、海南雞飯
- 若餐廳名稱無法判斷食物類型（如「幸福小館」），保留（remove: false）

其他原則：
- 不要新增任何餐廳（is_new 必須是 false）
- 價格要符合台灣物價
- 地址盡量具體到路名門牌

回傳 JSON 陣列（格式範例）：
[
  {
    "name": "餐廳名稱",
    "address": "完整地址",
    "rating": 4.5,
    "price_level": "$150-250",
    "food_type": "日式拉麵",
    "reason": "推薦理由（一句話）",
    "remove": false,
    "is_new": false
  }
]`;

  let enriched: EnrichedEntry[];
  try {
    enriched = await generateJSON<EnrichedEntry[]>(prompt, '你是台灣餐廳資料庫。只回傳有效 JSON 陣列，不要有任何其他文字。');
    if (!Array.isArray(enriched)) return restaurants;
  } catch (e) {
    console.warn('[enrichment] Gemini enrichment failed:', e);
    return restaurants;
  }

  // Build lookup by name
  const enrichedMap = new Map<string, EnrichedEntry>();
  for (const entry of enriched) {
    if (entry.name) enrichedMap.set(entry.name, entry);
  }

  // Filter out non-restaurants
  const removeNames = new Set(
    enriched.filter((e) => e.remove).map((e) => e.name),
  );
  if (removeNames.size > 0) {
    console.log('[enrichment] Removing non-restaurants:', [...removeNames]);
  }
  let filtered = restaurants.filter((r) => !removeNames.has(r.name));

  // Safety: if Gemini removed everything (over-aggressive), fall back to pre-enrichment list
  if (filtered.length === 0 && restaurants.length > 0) {
    console.warn('[enrichment] Gemini removed all restaurants — falling back to pre-enrichment list');
    filtered = restaurants;
  }

  // Merge enriched data — only fill missing fields, never overwrite real data
  for (const r of filtered) {
    const info = enrichedMap.get(r.name);
    if (!info || info.remove) continue;

    if ((!r.address || r.address.endsWith('附近')) && info.address) {
      r.address = info.address;
    }
    if (!r.rating && info.rating != null) r.rating = info.rating;
    if (!r.price_level && info.price_level) {
      r.price_level = info.price_level;
      r.estimated_price = info.price_level;
    }
    if (!r.food_type && info.food_type) r.food_type = info.food_type;
    if (info.reason) r.ai_reason = info.reason;
  }

  return filtered;
}
