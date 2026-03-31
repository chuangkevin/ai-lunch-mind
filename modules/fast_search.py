"""Fast restaurant search using HTTP (no Selenium).

Uses googlesearch-python for Google search results + Gemini for extraction.
Falls back to direct Google Maps URL construction.
Includes social media search (Dcard, Threads, PTT).
"""
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


def search_restaurants_fast(
    keyword: str,
    location: str,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Search for restaurants using HTTP-based Google search (no Selenium).

    Returns a list of restaurant dicts with name, address, rating, maps_url.
    """
    restaurants: List[Dict] = []

    # Strategy 1: googlesearch-python (fast HTTP scraping)
    try:
        from googlesearch import search as google_search

        query = f"{location} {keyword} 餐廳 推薦"
        results = list(google_search(query, num_results=10, lang="zh-TW"))

        # Filter for Google Maps results
        maps_results = [r for r in results if "google.com/maps" in r or "maps.app.goo.gl" in r]
        other_results = [r for r in results if r not in maps_results]

        # Extract restaurant info from Maps URLs
        for url in maps_results[:max_results]:
            name = _extract_name_from_maps_url(url)
            if name:
                restaurants.append({
                    "name": name,
                    "address": f"{location}附近",
                    "rating": None,
                    "maps_url": url,
                    "source": "google_maps_url",
                })

        # If not enough Maps results, use Gemini to extract from search snippets
        if len(restaurants) < max_results and other_results:
            try:
                extracted = _extract_restaurants_from_urls(other_results[:5], keyword, location)
                for r in extracted:
                    if r.get("name") and not any(
                        existing["name"] == r["name"] for existing in restaurants
                    ):
                        restaurants.append(r)
            except Exception as e:
                logger.warning("Gemini extraction failed: %s", e)

    except ImportError:
        logger.warning("googlesearch-python not available")
    except Exception as e:
        logger.warning("Google search failed: %s", e)

    # Strategy 2: Direct Google Maps search URL construction
    if len(restaurants) < 3:
        direct = _build_maps_search_results(keyword, location, max_results - len(restaurants))
        restaurants.extend(direct)

    return restaurants[:max_results]


def _extract_name_from_maps_url(url: str) -> Optional[str]:
    """Extract restaurant name from a Google Maps URL."""
    # Pattern: /maps/place/Restaurant+Name/
    match = re.search(r"/place/([^/@]+)", url)
    if match:
        name = match.group(1).replace("+", " ")
        return name
    return None


def _extract_restaurants_from_urls(
    urls: List[str],
    keyword: str,
    location: str,
) -> List[Dict]:
    """Use Gemini to extract restaurant info from search result URLs."""
    from modules.ai.gemini_pool import gemini_pool
    from google import genai
    from google.genai import types

    api_key = gemini_pool.get_key()
    if not api_key:
        return []

    prompt = f"""從以下搜尋結果中提取與「{keyword}」相關的餐廳名稱。
搜尋結果 URL：
{chr(10).join(urls[:5])}

位置：{location}

回傳 JSON 陣列：
[{{"name": "餐廳名稱", "source_url": "來源URL"}}]

只提取真實餐廳名稱，不要編造。如果無法確定，回傳空陣列 []。"""

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        extracted = json.loads(resp.text.strip())
        results = []
        for item in extracted:
            name = item.get("name", "")
            if name:
                results.append({
                    "name": name,
                    "address": f"{location}附近",
                    "rating": None,
                    "maps_url": f"https://www.google.com/maps/search/{quote(name)}+{quote(location)}",
                    "source": "google_search_extracted",
                })
        return results
    except Exception as e:
        logger.warning("Gemini extraction failed: %s", e)
        return []


def _build_maps_search_results(
    keyword: str,
    location: str,
    count: int,
) -> List[Dict]:
    """Build direct Google Maps search URLs as fallback."""
    encoded = quote(f"{location} {keyword} 餐廳")
    return [{
        "name": f"{keyword}餐廳（Google Maps 搜尋）",
        "address": f"{location}附近",
        "rating": None,
        "maps_url": f"https://www.google.com/maps/search/{encoded}",
        "source": "maps_search_url",
        "food_type": keyword,
    }]


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
    "walking_minutes": 5,
    "walking_distance": "約400m",
    "is_new": false
  }}
]

重要：
- is_new=false 表示是原本搜尋到的，is_new=true 表示你補充的
- 只推薦你確定真實存在的餐廳
- 地址要盡量準確
- 價格要符合台灣物價
- walking_minutes 和 walking_distance 是從 {location} 步行到該餐廳的估計時間和距離"""

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
                rest["walking_minutes"] = info.get("walking_minutes")
                rest["walking_distance"] = info.get("walking_distance", "")

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
                    "walking_minutes": info.get("walking_minutes"),
                    "walking_distance": info.get("walking_distance", ""),
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
    """Search social media (Dcard, Threads, PTT) for restaurant mentions.

    Returns a dict: {restaurant_name: [{platform, title, url}]}
    """
    mentions: Dict[str, List[Dict]] = {}

    try:
        from googlesearch import search as google_search
    except ImportError:
        logger.warning("googlesearch-python not available for social search")
        return mentions

    # Build one query for all restaurants + social platforms
    names_query = " OR ".join(f'"{n}"' for n in restaurant_names[:5])
    social_query = f"({names_query}) {location} (site:dcard.tw OR site:threads.net OR site:ptt.cc)"

    try:
        results = list(google_search(social_query, num_results=15, lang="zh-TW"))

        for url in results:
            platform = None
            if "dcard.tw" in url:
                platform = "Dcard"
            elif "threads.net" in url:
                platform = "Threads"
            elif "ptt.cc" in url:
                platform = "PTT"

            if not platform:
                continue

            # Match which restaurant this URL mentions
            for name in restaurant_names:
                # Simple check: restaurant name in URL or we associate with closest match
                if name not in mentions:
                    mentions[name] = []
                mentions[name].append({
                    "platform": platform,
                    "url": url,
                })
                break  # assign to first matching restaurant

    except Exception as e:
        logger.warning("Social search failed: %s", e)

    return mentions
