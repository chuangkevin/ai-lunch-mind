/**
 * Uber Eats restaurant search via undocumented getFeedV1 API.
 * No browser automation needed — pure HTTP POST with location cookie.
 */
import axios from 'axios';
import https from 'https';
import type { Restaurant } from '../types/index.js';

const FEED_URL = 'https://www.ubereats.com/_p/api/getFeedV1?localeCode=tw';

const HTTP_HEADERS = {
  'Content-Type': 'application/json',
  'X-CSRF-Token': 'x',
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
};

// Shared axios instance with SSL verification disabled (required for Uber Eats)
const axiosInstance = axios.create({
  httpsAgent: new https.Agent({ rejectUnauthorized: false }),
  timeout: 15000,
});

interface UberEatsStore {
  title?: { text?: string } | string;
  rating?: { text?: string; accessibilityText?: string };
  meta?: Array<{ badgeType?: string; text?: string }>;
  actionUrl?: string;
  image?: { items?: Array<{ url?: string; width?: number }> };
}

interface UberEatsFeedItem {
  type?: string;
  store?: UberEatsStore;
}

function normalizeName(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/\s*[\(（\[【].*?[\)）\]】]/g, '')
    .replace(/\s*(店|分店|門市|總店|旗艦店)$/, '')
    .replace(/\s+/g, '');
}

/**
 * Search Uber Eats for restaurants near a lat/lng.
 */
export async function searchUberEats(
  keyword: string,
  lat: number,
  lng: number,
  address = '',
  maxResults = 10,
): Promise<Restaurant[]> {
  const locData = {
    address: { address1: address, city: '', country: 'TW' },
    latitude: lat,
    longitude: lng,
  };
  const cookie = `uev2.loc=${encodeURIComponent(JSON.stringify(locData))}`;

  try {
    const resp = await axiosInstance.post(
      FEED_URL,
      { targetLocation: { latitude: lat, longitude: lng } },
      { headers: { ...HTTP_HEADERS, Cookie: cookie } },
    );

    const feed: UberEatsFeedItem[] = resp.data?.data?.feedItems ?? [];
    const restaurants: Restaurant[] = [];

    for (const item of feed) {
      if (item.type !== 'REGULAR_STORE') continue;
      const store = item.store;
      if (!store) continue;

      // Parse name
      const titleObj = store.title;
      const name =
        typeof titleObj === 'object' ? titleObj?.text ?? '' : String(titleObj ?? '');
      if (!name) continue;

      // Parse rating
      let rating: number | null = null;
      let ratingCount: number | null = null;
      if (store.rating) {
        const rt = parseFloat(store.rating.text ?? '');
        if (!isNaN(rt)) rating = rt;
        const countMatch = (store.rating.accessibilityText ?? '').replace(/,/g, '').match(/(\d+)/);
        if (countMatch) ratingCount = parseInt(countMatch[1], 10);
      }

      // Parse ETA
      let eta = '';
      for (const m of store.meta ?? []) {
        if (m.badgeType === 'ETD') { eta = m.text ?? ''; break; }
      }

      // Build Uber Eats URL — only /store/ URLs are valid
      const actionUrl = store.actionUrl ?? '';
      const uberEatsUrl = actionUrl.includes('/store/')
        ? `https://www.ubereats.com${actionUrl}`
        : '';

      // Pick image
      let imageUrl = '';
      const imgItems = store.image?.items ?? [];
      for (const img of imgItems) {
        if ((img.width ?? 0) >= 550) { imageUrl = img.url ?? ''; break; }
      }
      if (!imageUrl && imgItems.length > 0) imageUrl = imgItems[0].url ?? '';

      restaurants.push({
        name,
        address: '',
        rating,
        rating_count: ratingCount,
        price_level: null,
        estimated_price: null,
        maps_url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name)}`,
        food_type: keyword,
        source: 'uber_eats',
        open_now: null,
        hours_status: '',
        distance_km: null,
        walking_distance: '',
        walking_minutes: null,
        uber_eats_url: uberEatsUrl,
        uber_eats_eta: eta,
      });
    }

    console.log(`[uber-eats] Found ${restaurants.length} stores near (${lat.toFixed(3)}, ${lng.toFixed(3)})`);
    return restaurants.slice(0, maxResults);
  } catch (e) {
    console.warn('[uber-eats] API failed:', (e as Error).message);
    return [];
  }
}

/**
 * Non-restaurant entity names to filter out when using Uber Eats as fallback.
 * Kept as a small exclusion list (NOT an intent-analysis pattern).
 */
const NON_RESTAURANT_KEYWORDS = [
  '百貨', '超市', '便利', '7-ELEVEN', '全家', '萊爾富', 'OK超商',
  '家樂福', '全聯', '小北', '寶雅', '屈臣氏', '康是美', '大潤發',
  '好市多', 'Costco', '美廉社',
];

export function filterNonRestaurants(restaurants: Restaurant[]): Restaurant[] {
  const filtered = restaurants.filter(
    (r) => !NON_RESTAURANT_KEYWORDS.some((kw) => r.name.includes(kw)),
  );
  return filtered.length > 0 ? filtered : restaurants;
}

/**
 * Merge Uber Eats results into Google Maps results by name similarity.
 * Matched restaurants gain uber_eats_url, uber_eats_eta, uber_eats_rating.
 */
export function mergeUberEats(
  googleResults: Restaurant[],
  uberEatsResults: Restaurant[],
): Restaurant[] {
  const ueByNorm = new Map<string, Restaurant>();
  for (const r of uberEatsResults) {
    const norm = normalizeName(r.name);
    if (norm) ueByNorm.set(norm, r);
  }

  for (const gr of googleResults) {
    const gNorm = normalizeName(gr.name);

    // Exact match
    if (ueByNorm.has(gNorm)) {
      const ue = ueByNorm.get(gNorm)!;
      gr.uber_eats_url = ue.uber_eats_url ?? '';
      gr.uber_eats_eta = ue.uber_eats_eta ?? '';
      gr.uber_eats_rating = ue.rating;
      continue;
    }

    // Substring match with length-ratio guard
    for (const [ueNorm, ue] of ueByNorm) {
      if (gNorm.length >= 3 && ueNorm.length >= 3) {
        if (gNorm.includes(ueNorm) || ueNorm.includes(gNorm)) {
          const shorter = Math.min(gNorm.length, ueNorm.length);
          const longer = Math.max(gNorm.length, ueNorm.length);
          if (shorter / longer >= 0.4) {
            gr.uber_eats_url = ue.uber_eats_url ?? '';
            gr.uber_eats_eta = ue.uber_eats_eta ?? '';
            gr.uber_eats_rating = ue.rating;
            break;
          }
        }
      }
    }
  }

  return googleResults;
}
