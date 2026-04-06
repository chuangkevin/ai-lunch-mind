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

  const prompt = `你是台灣餐廳專家。使用者在 ${location} 想吃 ${keywords.join(', ')}。${budgetHint}${weatherHint}

我已搜尋到以下餐廳：
${JSON.stringify(existingNames, null, 2)}

請做兩件事：
1. 移除明顯不是餐廳/食物場所的項目（辦公大樓、公園、捷運站、便利商店等），標記 "remove": true
2. 為保留的餐廳補充資訊（地址、評分、價格、推薦理由）

重要原則：
- 只有「完全不是食物/餐飲場所」才設 remove: true
- 餐廳、小吃店、咖啡廳、任何有提供食物的地方一律保留（remove: false）
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
  const filtered = restaurants.filter((r) => !removeNames.has(r.name));

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
