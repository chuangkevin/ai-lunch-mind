/**
 * Google Maps restaurant scraper using Playwright.
 * Replaces Python's Selenium-based google_maps.py + fast_search.py.
 *
 * Browser pool: a single shared Chromium instance with concurrent pages.
 */
import { chromium, Browser, BrowserContext } from 'playwright';
import type { Restaurant } from '../types/index.js';

const CHROMIUM_PATH = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined;

// Singleton browser instance
let _browser: Browser | null = null;
let _context: BrowserContext | null = null;
let _initPromise: Promise<void> | null = null;

async function initBrowser(): Promise<void> {
  if (_browser) return;
  _browser = await chromium.launch({
    executablePath: CHROMIUM_PATH,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--disable-images',
      '--blink-settings=imagesEnabled=false',
    ],
  });
  _context = await _browser.newContext({
    userAgent:
      'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    locale: 'zh-TW',
    viewport: { width: 1280, height: 720 },
  });
  console.log('[google-maps] Playwright browser initialized');
}

async function getBrowser(): Promise<BrowserContext> {
  if (!_initPromise) {
    _initPromise = initBrowser();
  }
  await _initPromise;
  return _context!;
}

export async function closeBrowser(): Promise<void> {
  if (_browser) {
    await _browser.close();
    _browser = null;
    _context = null;
    _initPromise = null;
  }
}

/** Parse text lines from a Google Maps result card */
function parseCardLines(
  lines: string[],
): Pick<Restaurant, 'rating' | 'address' | 'price_level' | 'open_now' | 'hours_status'> {
  let rating: number | null = null;
  let address = '';
  let price_level: string | null = null;
  let open_now: boolean | null = null;
  let hours_status = '';

  for (const line of lines) {
    const l = line.trim();
    if (!l) continue;

    // Rating: standalone "4.6"
    if (!rating && /^\d\.\d$/.test(l)) {
      rating = parseFloat(l);
      continue;
    }

    // Business hours
    if (/營業中|休息中|已打烊|打烊時間|開始營業|24 小時|已歇業|暫停營業/.test(l)) {
      hours_status = l;
      if (/營業中|24 小時/.test(l)) open_now = true;
      else if (/休息中|已打烊|已歇業|暫停營業/.test(l)) open_now = false;
      continue;
    }

    // Category + address: "餐廳 · 信義路五段7號"
    if (l.includes('·') && /[路街巷號]/.test(l)) {
      const parts = l.split('·').map((p) => p.trim());
      for (const part of parts) {
        if (/[路街巷號]/.test(part) && part.length > 2) {
          address = part;
        }
      }
      continue;
    }

    // Pure address line
    if (/[路街巷號]\S{0,5}$/.test(l) && !l.includes('·') && !/營業/.test(l)) {
      address = l;
      continue;
    }

    // Price
    if (!price_level) {
      const priceMatch = l.match(/(\$+|＄+)/);
      if (priceMatch) {
        const dollars = priceMatch[1].length;
        const priceMap: Record<number, string> = {
          1: '$50-150', 2: '$150-400', 3: '$400-800', 4: '$800+',
        };
        price_level = priceMap[dollars] ?? null;
      }
    }
  }

  return { rating, address, price_level, open_now, hours_status };
}

/**
 * Search Google Maps for restaurants matching keyword near location.
 * Returns up to maxResults restaurants.
 */
export async function searchGoogleMaps(
  keyword: string,
  location: string,
  maxResults = 5,
): Promise<Restaurant[]> {
  const restaurants: Restaurant[] = [];

  let ctx: BrowserContext;
  try {
    ctx = await getBrowser();
  } catch (e) {
    console.warn('[google-maps] Browser init failed:', e);
    return restaurants;
  }

  const query = encodeURIComponent(`${location} ${keyword} 餐廳`);
  const url = `https://www.google.com/maps/search/${query}`;

  const page = await ctx.newPage();
  try {
    page.setDefaultTimeout(8000);
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 10000 });
    } catch {
      // Partial load is OK
    }
    // Wait for feed or any place links to appear (up to 6s)
    try {
      await page.waitForSelector('a[href*="/maps/place/"]', { timeout: 6000 });
    } catch {
      // Feed didn't appear — will return empty
    }

    // Get all restaurant links (use broad selector; deduplicate by href in loop)
    const links = await page.$$('a[href*="/maps/place/"]');
    const seenHrefs = new Set<string>();

    for (const link of links) {
      if (restaurants.length >= maxResults) break;
      try {
        const href = (await link.getAttribute('href')) ?? '';
        if (!href || seenHrefs.has(href)) continue;
        seenHrefs.add(href);

        const ariaLabel = (await link.getAttribute('aria-label')) ?? '';

        let name = ariaLabel;
        if (!name) {
          const m = href.match(/\/place\/([^/]+)\//);
          if (m) name = decodeURIComponent(m[1].replace(/\+/g, ' '));
        }
        if (!name || name.length < 2) continue;

        // Get parent text for parsing
        const parentText = await link.evaluate((el: Element) => {
          const parent = el.parentElement;
          return parent ? parent.innerText : '';
        });
        const lines = parentText.split('\n');
        const parsed = parseCardLines(lines);

        // Skip permanently closed
        if (/已歇業|永久歇業|暫停營業/.test(parsed.hours_status)) {
          continue;
        }

        restaurants.push({
          name: name.trim(),
          address: parsed.address || `${location}附近`,
          rating: parsed.rating,
          rating_count: null,
          price_level: parsed.price_level,
          estimated_price: null,
          maps_url: href,
          food_type: keyword,
          source: 'google_maps',
          open_now: parsed.open_now,
          hours_status: parsed.hours_status,
          distance_km: null,
          walking_distance: '',
          walking_minutes: null,
        });

        // maxResults break is at top of loop
      } catch {
        // Skip malformed results
      }
    }
  } finally {
    await page.close();
  }

  console.log(`[google-maps] "${keyword}" in "${location}" → ${restaurants.length} results`);
  return restaurants;
}

/**
 * Search Google for Dcard/PTT social mentions of restaurant names.
 * Returns map of restaurant name → [{platform, url}].
 */
export async function searchSocialMentions(
  restaurantNames: string[],
  location: string,
): Promise<Record<string, Array<{ platform: string; url: string }>>> {
  const mentions: Record<string, Array<{ platform: string; url: string }>> = {};

  let ctx: BrowserContext;
  try {
    ctx = await getBrowser();
  } catch {
    return mentions;
  }

  const namesPart = restaurantNames
    .slice(0, 3)
    .map((n) => `"${n}"`)
    .join(' OR ');
  const query = encodeURIComponent(
    `${namesPart} ${location} (site:dcard.tw OR site:ptt.cc)`,
  );

  const page = await ctx.newPage();
  try {
    page.setDefaultTimeout(5000);
    try {
      await page.goto(`https://www.google.com/search?q=${query}&hl=zh-TW`, {
        waitUntil: 'domcontentloaded',
        timeout: 5000,
      });
    } catch { /* Timeout OK */ }
    await page.waitForTimeout(1000);

    const links = await page.$$('a[href*="dcard.tw"], a[href*="ptt.cc"], a[href*="threads.net"]');
    for (const link of links.slice(0, 10)) {
      const href = (await link.getAttribute('href')) ?? '';
      let platform: string | null = null;
      if (href.includes('dcard.tw')) platform = 'Dcard';
      else if (href.includes('ptt.cc')) platform = 'PTT';
      else if (href.includes('threads.net')) platform = 'Threads';

      if (platform) {
        for (const name of restaurantNames) {
          if (!mentions[name]) mentions[name] = [];
          mentions[name].push({ platform, url: href });
          break;
        }
      }
    }
  } finally {
    await page.close();
  }

  return mentions;
}
