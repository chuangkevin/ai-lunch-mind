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

        # Geocode user location
        user_geo = geolocator.geocode(user_location)
        if not user_geo:
            logger.warning("Cannot geocode user location: %s", user_location)
            return restaurants

        user_coords = (user_geo.latitude, user_geo.longitude)
        logger.info("User: %s -> (%.4f, %.4f)", user_location, *user_coords)

        for r in restaurants:
            addr = r.get("address", "")
            if not addr or addr.endswith("附近"):
                addr = r.get("name", "") + " " + user_location

            try:
                rest_geo = geolocator.geocode(addr)
                if rest_geo:
                    rest_coords = (rest_geo.latitude, rest_geo.longitude)
                    dist_km = geodesic(user_coords, rest_coords).kilometers
                    walking_km = dist_km * 1.3  # Walking route factor
                    walking_minutes = round(walking_km / 5 * 60)  # 5 km/h

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
            driver.set_page_load_timeout(5)

            try:
                driver.get(maps_url)
            except Exception:
                pass  # Timeout is OK, we parse what loaded

            time.sleep(1.5)  # Wait for results to render

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

                        # Extract rating from nearby elements
                        rating = None
                        try:
                            parent = div.find_element(By.XPATH, './..')
                            rating_text = parent.text
                            rating_match = re.search(r'(\d\.\d)', rating_text)
                            if rating_match:
                                rating = float(rating_match.group(1))
                        except Exception:
                            pass

                        # Extract address - look for text that looks like an address
                        address = f"{location}附近"
                        try:
                            parent = div.find_element(By.XPATH, './..')
                            text = parent.text
                            # Look for address patterns (contains 路/街/巷/號)
                            for line in text.split('\n'):
                                if re.search(r'[路街巷號]', line) and '·' not in line:
                                    address = line.strip()
                                    break
                        except Exception:
                            pass

                        # Extract price level
                        price_level = None
                        try:
                            parent_text = div.find_element(By.XPATH, './..').text
                            price_match = re.search(r'(\$+)', parent_text)
                            if price_match:
                                dollars = len(price_match.group(1))
                                price_map = {1: '$50-150', 2: '$150-400', 3: '$400-800', 4: '$800+'}
                                price_level = price_map.get(dollars, '')
                        except Exception:
                            pass

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
1. 為每間已知餐廳補充資訊（如果你知道的話）
2. 再補充 3-5 間你確定在 {location} 附近真實存在的相關餐廳

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
- 不要估算步行距離或時間，距離由系統計算"""

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

        for rest in restaurants:
            name = rest.get("name", "")
            if name in enriched_by_name:
                info = enriched_by_name.pop(name)
                rest["address"] = info.get("address", rest.get("address", ""))
                rest["rating"] = info.get("rating", rest.get("rating"))
                rest["price_level"] = info.get("price_level", rest.get("price_level"))
                rest["estimated_price"] = info.get("price_level")
                rest["food_type"] = info.get("food_type", rest.get("food_type", ""))
                rest["ai_reason"] = info.get("reason", "")
                # walking_minutes/walking_distance set by calculate_real_distances, not Gemini

        # Add new restaurants from Gemini
        for name, info in enriched_by_name.items():
            if info.get("is_new", True):
                restaurants.append({
                    "name": name,
                    "address": info.get("address", f"{location}附近"),
                    "rating": info.get("rating"),
                    "price_level": info.get("price_level"),
                    "estimated_price": info.get("price_level"),
                    "food_type": info.get("food_type", ""),
                    "ai_reason": info.get("reason", ""),
                    # walking data filled by calculate_real_distances
                    "maps_url": f"https://www.google.com/maps/search/{quote(name)}+{quote(location)}",
                    "source": "gemini_supplement",
                })

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
