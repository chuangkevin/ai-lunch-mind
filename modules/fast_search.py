"""Fast restaurant search using Selenium Google Maps (optimized for speed).

Uses shared browser pool for all web access to avoid SSL issues.
Target: < 8 seconds for the entire search pipeline.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


def calculate_real_distances(
    restaurants: List[Dict],
    user_location: str,
) -> List[Dict]:
    """Calculate real distances using ArcGIS geocoding + geodesic formula.

    No AI needed. ArcGIS supports Chinese addresses natively.
    """
    try:
        from geopy.geocoders import ArcGIS
        from geopy.distance import geodesic

        geolocator = ArcGIS(timeout=5)

        # Geocode user location — try multiple formats
        user_geo = None
        for variant in [
            user_location,
            user_location + " 台灣",
            user_location.replace("科大", "科技大學").replace("大學", "大學 台灣"),
            user_location + " Taiwan",
        ]:
            user_geo = geolocator.geocode(variant)
            if user_geo:
                break
        if not user_geo:
            logger.warning("Cannot geocode user location: %s", user_location)
            return restaurants

        user_coords = (user_geo.latitude, user_geo.longitude)
        logger.info("User: %s -> (%.4f, %.4f)", user_location, *user_coords)

        for r in restaurants:
            addr = r.get("address", "")

            # Skip if address is just "附近"
            if not addr or addr.endswith("附近"):
                addr = r.get("name", "") + " " + user_location

            # If address is short (just road name, no city/district), prepend user location for context
            if addr and not re.search(r'[市縣區鎮鄉]', addr):
                addr = user_location + " " + addr

            try:
                rest_geo = geolocator.geocode(addr)
                if rest_geo:
                    rest_coords = (rest_geo.latitude, rest_geo.longitude)
                    dist_km = geodesic(user_coords, rest_coords).kilometers

                    # Sanity check: if distance < 30m, geocode probably hit the same point
                    if dist_km < 0.03:
                        continue  # Skip, don't show fake 0m distance

                    walking_km = dist_km * 1.3
                    walking_minutes = round(walking_km / 5 * 60)

                    r["distance_km"] = round(dist_km, 2)
                    r["walking_distance"] = f"{round(walking_km * 1000)}m" if walking_km < 1 else f"{walking_km:.1f}km"
                    r["walking_minutes"] = walking_minutes
            except Exception as e:
                logger.warning("  Geocode error for %s: %s", r.get("name"), e)

    except ImportError:
        logger.warning("geopy not available")
    except Exception as e:
        logger.warning("Distance calculation failed: %s", e)

    return restaurants


def search_restaurants_fast(
    keyword: str,
    location: str,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Search Google Maps for real restaurants using a shared Selenium browser.

    Uses a single pre-warmed Chrome instance for speed.
    Target: < 5 seconds per keyword search.
    """
    restaurants = []

    try:
        from modules.scraper.browser_pool import browser_pool
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        search_query = f"{location} {keyword} 餐廳"
        encoded = quote(search_query)
        maps_url = f"https://www.google.com/maps/search/{encoded}"

        with browser_pool.get_browser() as driver:
            driver.set_page_load_timeout(8)

            try:
                driver.get(maps_url)
            except Exception:
                pass  # Timeout is OK, we parse what loaded

            time.sleep(3)  # Wait for results to render

            # Parse restaurant results from Google Maps
            # Google Maps results are in divs with role="feed" > div elements
            try:
                results_divs = driver.find_elements(By.CSS_SELECTOR,
                    'div[role="feed"] > div > div > a[href*="/maps/place/"]')

                if not results_divs:
                    # Alternative selector
                    results_divs = driver.find_elements(By.CSS_SELECTOR,
                        'a[href*="/maps/place/"]')

                for div in results_divs[:max_results]:
                    try:
                        href = div.get_attribute('href') or ''
                        aria_label = div.get_attribute('aria-label') or ''

                        # Extract name from aria-label or href
                        name = aria_label
                        if not name:
                            match = re.search(r'/place/([^/]+)/', href)
                            if match:
                                name = match.group(1).replace('+', ' ')

                        if not name or len(name) < 2:
                            continue

                        # Parse all info from parent text
                        # Format: "Name\n4.6\n餐廳 ·  · 明志路一段13號\n營業中 · 打烊時間：20:50"
                        rating = None
                        address = f"{location}附近"
                        price_level = None
                        food_category = ""

                        try:
                            parent = div.find_element(By.XPATH, './..')
                            lines = parent.text.split('\n')

                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue

                                # Rating: standalone number like "4.6"
                                if not rating and re.match(r'^\d\.\d$', line):
                                    rating = float(line)
                                    continue

                                # Category + address line: "餐廳 ·  · 明志路一段13號"
                                if '·' in line and re.search(r'[路街巷號]', line):
                                    parts = line.split('·')
                                    for part in parts:
                                        part = part.strip()
                                        if re.search(r'[路街巷號]', part):
                                            address = part
                                        elif part and not re.search(r'[$＄]', part):
                                            food_category = part
                                    continue

                                # Pure address line (no ·): "明志路一段13號"
                                if re.search(r'[路街巷號]\S{0,5}$', line) and '·' not in line and '營業' not in line:
                                    address = line
                                    continue

                                # Price: "$" or "$$"
                                price_match = re.search(r'(\$+|＄+)', line)
                                if price_match and not price_level:
                                    dollars = len(price_match.group(1))
                                    price_map = {1: '$50-150', 2: '$150-400', 3: '$400-800', 4: '$800+'}
                                    price_level = price_map.get(dollars)

                        except Exception as e:
                            logger.warning("Failed to parse parent text: %s", e)

                        restaurants.append({
                            'name': name,
                            'address': address,
                            'rating': rating,
                            'price_level': price_level,
                            'maps_url': href,
                            'food_type': keyword,
                            'source': 'google_maps',
                        })

                    except Exception as e:
                        logger.warning("Failed to parse restaurant element: %s", e)
                        continue

            except Exception as e:
                logger.warning("Failed to find results on Maps page: %s", e)

    except Exception as e:
        logger.warning("Selenium search failed for '%s': %s", keyword, e)

    logger.info("Found %d restaurants for '%s' in '%s'", len(restaurants), keyword, location)
    return restaurants


def enrich_with_gemini(
    restaurants: List[Dict],
    user_input: str,
    location: str,
    keywords: List[str],
    budget: Optional[Dict] = None,
    weather_data: Optional[Dict] = None,
) -> List[Dict]:
    """Use Gemini to enrich restaurant results with ratings, prices, and reasons.
    Also add any additional recommendations Gemini knows about.
    """
    from modules.ai.gemini_pool import gemini_pool
    from google import genai
    from google.genai import types

    api_key = gemini_pool.get_key()
    if not api_key:
        return restaurants

    existing_names = [r.get("name", "") for r in restaurants]

    budget_hint = ""
    if budget and budget.get("max"):
        budget_hint = f"\n使用者預算：{budget['max']}元以內"

    weather_hint = ""
    if weather_data and weather_data.get("temperature"):
        temp = weather_data["temperature"]
        sweat = weather_data.get("sweat_index", "N/A")
        weather_hint = f"\n天氣：{temp}°C, 流汗指數 {sweat}"

    prompt = f"""你是台灣餐廳專家。使用者在 {location} 想吃 {', '.join(keywords)}。{budget_hint}{weather_hint}

我已搜尋到以下餐廳：
{json.dumps(existing_names, ensure_ascii=False)}

請做兩件事：
1. 移除不是餐廳的項目（如大樓、公司、公園等），標記 "remove": true
2. 為每間已知餐廳補充資訊（如果你知道的話），特別是完整地址

重要：不要新增任何餐廳，只處理上面列出的這些。

回傳 JSON 陣列：
[
  {{
    "name": "餐廳名稱",
    "address": "完整地址（盡量具體到路名門牌）",
    "rating": 4.5,
    "price_level": "$150-250",
    "food_type": "日式拉麵",
    "reason": "推薦理由（一句話）",
    "is_new": false
  }}
]

重要：
- is_new=false 表示是原本搜尋到的，is_new=true 表示你補充的
- 只推薦你確定真實存在的餐廳
- 地址要盡量準確
- 價格要符合台灣物價
- 不要估算步行距離或時間，距離由系統計算
- 如果項目不是餐廳（如大樓、辦公室、公園），設 "remove": true"""

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        enriched = json.loads(resp.text.strip())
        if not isinstance(enriched, list):
            return restaurants

        # Merge enriched data back
        enriched_by_name = {r["name"]: r for r in enriched if "name" in r}

        # Filter out non-restaurants marked by Gemini
        remove_names = {r["name"] for r in enriched if r.get("remove")}
        if remove_names:
            logger.info("Removing non-restaurants: %s", remove_names)
            restaurants = [r for r in restaurants if r.get("name") not in remove_names]

        for rest in restaurants:
            name = rest.get("name", "")
            if name in enriched_by_name:
                info = enriched_by_name.pop(name)
                if info.get("remove"):
                    continue
                rest["address"] = info.get("address", rest.get("address", ""))
                rest["rating"] = info.get("rating", rest.get("rating"))
                rest["price_level"] = info.get("price_level", rest.get("price_level"))
                rest["estimated_price"] = info.get("price_level")
                rest["food_type"] = info.get("food_type", rest.get("food_type", ""))
                rest["ai_reason"] = info.get("reason", "")

        # DO NOT add Gemini-generated restaurants — they are hallucinated.
        # Gemini is only allowed to enrich existing Google Maps results.

        return restaurants

    except Exception as e:
        logger.warning("Gemini enrichment failed: %s", e)
        return restaurants


def search_social_mentions(
    restaurant_names: List[str],
    location: str,
) -> Dict[str, List[Dict]]:
    """Search for social media mentions using Selenium Google search.

    Uses Selenium instead of googlesearch-python to avoid SSL issues.
    Returns a dict: {restaurant_name: [{platform, url}]}
    """
    mentions: Dict[str, List[Dict]] = {}

    try:
        from modules.scraper.browser_pool import browser_pool
        from selenium.webdriver.common.by import By

        names_part = ' OR '.join(f'"{n}"' for n in restaurant_names[:3])
        query = f"{names_part} {location} (site:dcard.tw OR site:ptt.cc)"

        with browser_pool.get_browser() as driver:
            driver.set_page_load_timeout(5)
            try:
                driver.get(f"https://www.google.com/search?q={quote(query)}&hl=zh-TW")
            except Exception:
                pass  # Timeout is OK, we parse what loaded
            time.sleep(1)

            links = driver.find_elements(By.CSS_SELECTOR,
                'a[href*="dcard.tw"], a[href*="ptt.cc"], a[href*="threads.net"]')

            for link in links[:10]:
                url = link.get_attribute('href') or ''
                platform = None
                if 'dcard.tw' in url:
                    platform = 'Dcard'
                elif 'ptt.cc' in url:
                    platform = 'PTT'
                elif 'threads.net' in url:
                    platform = 'Threads'

                if platform:
                    for name in restaurant_names:
                        if name not in mentions:
                            mentions[name] = []
                        mentions[name].append({'platform': platform, 'url': url})
                        break

    except Exception as e:
        logger.warning("Social search failed: %s", e)

    return mentions
