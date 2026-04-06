/**
 * SSE streaming recommendation endpoint.
 * Replicates the Python FastAPI /chat-recommendation-stream endpoint.
 * Events: thinking, weather, intent, analysis, restaurant, done, error
 */
import { Router, Request, Response } from 'express';
import type { Restaurant } from '../types/index.js';

const router = Router();

function sendEvent(res: Response, event: string, data: unknown): void {
  res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

router.get('/chat-recommendation-stream', async (req: Request, res: Response) => {
  const message = req.query.message as string | undefined;
  const latParam = req.query.lat as string | undefined;
  const lngParam = req.query.lng as string | undefined;

  if (!message) {
    res.status(400).json({ error: 'Missing message' });
    return;
  }

  const userCoords =
    latParam && lngParam
      ? { lat: parseFloat(latParam), lng: parseFloat(lngParam) }
      : null;

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('X-Accel-Buffering', 'no');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  try {
    const { analyzeIntent } = await import('../modules/intent-analyzer.js');
    const { getWeather } = await import('../modules/weather.js');
    const { getMaxDistanceKm } = await import('../modules/sweat-index.js');
    const { searchGoogleMaps, searchSocialMentions } = await import('../modules/google-maps.js');
    const { geocode } = await import('../modules/geocoding.js');
    const {
      searchUberEats,
      mergeUberEats,
      filterNonRestaurants,
    } = await import('../modules/uber-eats.js');
    const { enrichWithGemini } = await import('../modules/enrichment.js');
    const { calculateDistances } = await import('../modules/distance.js');

    const currentHour = new Date().getHours();

    // ─── Step 1: Weather ──────────────────────────────────────────────────
    sendEvent(res, 'thinking', { step: 'weather', message: '查詢天氣資料...' });

    let weatherData = null;
    let sweatIndex: number | null = null;
    let rainProb: number | null = null;

    try {
      // Extract location hint from message for weather lookup
      const locHint = message.match(/我在([^\s，。！？,]{2,20})/)?.[1] ?? message;
      weatherData = await Promise.race([
        getWeather(locHint, userCoords),
        new Promise<null>((r) => setTimeout(() => r(null), 8000)),
      ]);

      if (weatherData) {
        sweatIndex = weatherData.sweat_index ?? null;
        rainProb = weatherData.rain_probability ?? null;
        sendEvent(res, 'weather', {
          temperature: weatherData.temperature,
          humidity: weatherData.humidity,
          sweat_index: sweatIndex,
          rain_probability: rainProb,
        });
      } else {
        sendEvent(res, 'thinking', { step: 'weather', message: '天氣查詢無資料，跳過' });
      }
    } catch {
      sendEvent(res, 'thinking', { step: 'weather', message: '天氣查詢跳過' });
    }

    // ─── Step 2: Intent Analysis ───────────────────────────────────────────
    sendEvent(res, 'thinking', { step: 'intent', message: '分析您的需求...' });

    const intent = await Promise.race([
      analyzeIntent(message, weatherData, currentHour),
      new Promise<null>((r) => setTimeout(() => r(null), 20000)),
    ]);

    if (!intent) {
      sendEvent(res, 'error', { message: '意圖分析超時，請稍後再試' });
      res.end();
      return;
    }

    const location = intent.location ?? '台北';
    const keywords = intent.primary_keywords;
    const budget = intent.budget;

    sendEvent(res, 'intent', {
      location: intent.location,
      keywords,
      secondary_keywords: intent.secondary_keywords,
      budget,
      source: intent._source,
    });

    // ─── Step 3: Distance calculation setup ────────────────────────────────
    const { maxKm, reason: distanceReason } = getMaxDistanceKm(sweatIndex, rainProb);
    sendEvent(res, 'analysis', {
      distance_reason: distanceReason,
      max_distance_km: maxKm,
    });

    // ─── Step 4: Restaurant search ─────────────────────────────────────────
    const searchKws = keywords.slice(0, 3);
    sendEvent(res, 'thinking', {
      step: 'search',
      message: `Google Maps + Uber Eats 搜尋中（${searchKws.length} 個關鍵字並行）...`,
    });

    // Geocode location for Uber Eats
    let ueCoords: { lat: number; lng: number } | null = userCoords;
    if (!ueCoords) {
      try {
        const pt = await Promise.race([
          geocode(location),
          new Promise<null>((r) => setTimeout(() => r(null), 5000)),
        ]);
        if (pt) ueCoords = pt;
      } catch { /* non-fatal */ }
    }

    // Parallel: Google Maps searches + Uber Eats
    const gmPromises = searchKws.map((kw) =>
      searchGoogleMaps(kw, location, 8).then((results) => ({ kw, results })),
    );
    const uePromise = ueCoords
      ? searchUberEats(keywords[0] ?? '', ueCoords.lat, ueCoords.lng, location, 20)
      : Promise.resolve([]);

    const allGmResults = await Promise.allSettled(gmPromises);
    const ueResults = await Promise.race([
      uePromise,
      new Promise<Restaurant[]>((r) => setTimeout(() => r([]), 20000)),
    ]);

    const seen = new Set<string>();
    let allRestaurants: Restaurant[] = [];

    for (const settled of allGmResults) {
      if (settled.status !== 'fulfilled') continue;
      const { kw, results } = settled.value;
      for (const r of results) {
        if (!r.name || seen.has(r.name)) continue;
        seen.add(r.name);
        r.food_type = kw;
        allRestaurants.push(r);
      }
      sendEvent(res, 'thinking', {
        step: 'search_progress',
        message: `「${kw}」找到 ${results.length} 間（累計 ${allRestaurants.length} 間）`,
      });
    }

    // Merge Uber Eats into Google Maps results
    if (ueResults.length > 0) {
      sendEvent(res, 'thinking', {
        step: 'ubereats_done',
        message: `Uber Eats 找到 ${ueResults.length} 間外送餐廳`,
      });

      if (allRestaurants.length > 0) {
        allRestaurants = mergeUberEats(allRestaurants, ueResults);
        const matched = allRestaurants.filter((r) => r.uber_eats_url).length;
        if (matched > 0) {
          sendEvent(res, 'thinking', {
            step: 'ubereats_merged',
            message: `${matched} 間餐廳支援 Uber Eats 外送`,
          });
        }
      } else {
        // Fallback: use Uber Eats only — but Uber Eats API ignores keyword,
        // so filter by name keyword match first before enrichment handles the rest.
        const nonRestaurantsFiltered = filterNonRestaurants(ueResults);
        // Simple keyword pre-filter: keep if name contains any search keyword,
        // OR if name is ambiguous (short / Chinese-only with no clear food type).
        const kwLower = keywords.map((k) => k.toLowerCase());
        const keywordFiltered = nonRestaurantsFiltered.filter((r) => {
          const nameLower = r.name.toLowerCase();
          // Keep if name matches any keyword
          if (kwLower.some((k) => nameLower.includes(k))) return true;
          // Keep if name is short/ambiguous (can't determine food type from name)
          if (r.name.length <= 6) return true;
          // Keep if name doesn't contain common non-matching food words
          const clearMismatch = ['麥當勞', 'McDonald', 'KFC', '肯德基', 'Pizza', '披薩',
            '漢堡', '早餐', '燒肉', '烤肉', '壽司', '泰式', '韓式', '越南', '印度',
            '海南', '咖哩', '義式', '意大利', '牛排', '火鍋'].some((m) =>
            r.name.includes(m) && !kwLower.some((k) => r.name.includes(k)));
          return !clearMismatch;
        });
        sendEvent(res, 'thinking', {
          step: 'ubereats_fallback',
          message: `Google Maps 無結果，改用 Uber Eats（${keywordFiltered.length}/${nonRestaurantsFiltered.length} 間符合「${keywords[0]}」）`,
        });
        for (const ue of keywordFiltered) {
          ue.food_type = keywords[0] ?? '';
          ue.maps_url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(ue.name + ' ' + location)}`;
          ue.relevance_score = 7.0;
        }
        allRestaurants = keywordFiltered;
      }
    }

    sendEvent(res, 'thinking', {
      step: 'search_done',
      message: `共找到 ${allRestaurants.length} 間餐廳`,
    });

    if (allRestaurants.length === 0) {
      sendEvent(res, 'error', { message: '沒有找到餐廳，請換個說法試試' });
      res.end();
      return;
    }

    // ─── Step 5: Gemini Enrichment ─────────────────────────────────────────
    sendEvent(res, 'thinking', { step: 'enrich', message: 'AI 補充推薦理由...' });
    try {
      allRestaurants = await Promise.race([
        enrichWithGemini(allRestaurants, message, location, keywords, budget, weatherData),
        new Promise<Restaurant[]>((r) => setTimeout(() => r(allRestaurants), 15000)),
      ]);
    } catch (e) {
      console.warn('[chat] Enrichment failed:', e);
    }

    // ─── Step 6: Distance calculation ─────────────────────────────────────
    sendEvent(res, 'thinking', { step: 'distance', message: '計算步行距離...' });

    // Ensure Maps URLs exist
    for (const r of allRestaurants) {
      if (!r.maps_url) {
        r.maps_url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(r.name + ' ' + location)}`;
      }
      if (!r.estimated_price) r.estimated_price = r.price_level ?? null;
    }

    try {
      allRestaurants = await Promise.race([
        calculateDistances(allRestaurants, location, userCoords),
        new Promise<Restaurant[]>((r) => setTimeout(() => r(allRestaurants), 20000)),
      ]);
    } catch (e) {
      console.warn('[chat] Distance calc failed:', e);
    }

    // Filter by distance (prefer within maxKm, expand if nothing found)
    const within = allRestaurants.filter(
      (r) => r.distance_km != null && r.distance_km <= maxKm,
    );
    const unknown = allRestaurants.filter((r) => r.distance_km == null);

    if (within.length > 0) {
      allRestaurants = [...within, ...unknown];
    } else {
      const known = allRestaurants
        .filter((r) => r.distance_km != null)
        .sort((a, b) => (a.distance_km ?? 999) - (b.distance_km ?? 999));
      if (known.length > 0) {
        sendEvent(res, 'thinking', {
          step: 'distance_expanded',
          message: `${maxKm * 1000}m 內沒有結果，顯示最近的 ${Math.min(known.length, 5)} 間`,
        });
        allRestaurants = [...known.slice(0, 5), ...unknown];
      }
    }

    // ─── Step 7: Social mentions ──────────────────────────────────────────
    sendEvent(res, 'thinking', { step: 'social', message: '搜尋 Dcard/PTT 討論...' });
    try {
      const names = allRestaurants.map((r) => r.name).filter(Boolean);
      const mentions = await Promise.race([
        searchSocialMentions(names, location),
        new Promise<Record<string, Array<{ platform: string; url: string }>>>((r) =>
          setTimeout(() => r({}), 8000),
        ),
      ]);
      let socialCount = 0;
      for (const r of allRestaurants) {
        const m = mentions[r.name];
        if (m && m.length > 0) {
          const platforms = [...new Set(m.map((x) => x.platform))];
          r.social_proof = { platforms, mentions: m.slice(0, 3), count: m.length };
          socialCount++;
        }
      }
      if (socialCount > 0) {
        sendEvent(res, 'thinking', {
          step: 'social_done',
          message: `找到 ${socialCount} 間有社群討論`,
        });
      }
    } catch { /* non-fatal */ }

    // ─── Step 8: Sort & stream results ─────────────────────────────────────
    sendEvent(res, 'thinking', {
      step: 'scoring',
      message: `共 ${allRestaurants.length} 間餐廳，排序中...`,
    });

    allRestaurants.sort((a, b) => {
      // open first, then distance, then social proof, then rating
      const openA = a.open_now === true ? 0 : a.open_now === null ? 1 : 2;
      const openB = b.open_now === true ? 0 : b.open_now === null ? 1 : 2;
      if (openA !== openB) return openA - openB;

      const distA = a.distance_km ?? 999;
      const distB = b.distance_km ?? 999;
      if (distA !== distB) return distA - distB;

      const socA = a.social_proof ? 0 : 1;
      const socB = b.social_proof ? 0 : 1;
      if (socA !== socB) return socA - socB;

      return (b.rating ?? 0) - (a.rating ?? 0);
    });

    for (let i = 0; i < allRestaurants.length; i++) {
      sendEvent(res, 'restaurant', { index: i, restaurant: allRestaurants[i] });
      // Small delay for perceived streaming
      await new Promise((r) => setTimeout(r, 50));
    }

    sendEvent(res, 'done', { total: allRestaurants.length });
  } catch (err) {
    console.error('[chat] Unhandled error:', err);
    sendEvent(res, 'error', { message: `推薦失敗: ${(err as Error).message}` });
  } finally {
    res.end();
  }
});

export default router;
