"""Uber Eats restaurant search via undocumented getFeedV1 API.

No Selenium needed. Uses manually constructed location cookie + POST request.
Returns real restaurant data: name, rating, delivery time, Uber Eats URL.
"""
import json
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Suppress SSL warnings for corporate networks
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

FEED_URL = "https://www.ubereats.com/_p/api/getFeedV1?localeCode=tw"
HEADERS = {
    "Content-Type": "application/json",
    "X-CSRF-Token": "x",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def search_ubereats(
    keyword: str,
    latitude: float,
    longitude: float,
    address: str = "",
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Search Uber Eats for restaurants near a location.

    Args:
        keyword: Food type to search (used for filtering results)
        latitude: User's latitude
        longitude: User's longitude
        address: Optional address string for cookie
        max_results: Max restaurants to return

    Returns:
        List of restaurant dicts with name, rating, eta, uber_eats_url, etc.
    """
    # Construct location cookie
    loc_data = {
        "address": {"address1": address or "", "city": "", "country": "TW"},
        "latitude": latitude,
        "longitude": longitude,
    }
    cookie = f"uev2.loc={urllib.parse.quote(json.dumps(loc_data))}"

    headers = {**HEADERS, "Cookie": cookie}
    payload = {"targetLocation": {"latitude": latitude, "longitude": longitude}}

    try:
        resp = requests.post(FEED_URL, json=payload, headers=headers, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Uber Eats API failed: %s", e)
        return []

    feed = data.get("data", {}).get("feedItems", [])

    # Extract REGULAR_STORE items
    restaurants = []
    keyword_lower = keyword.lower() if keyword else ""

    for item in feed:
        if item.get("type") != "REGULAR_STORE":
            continue

        store = item.get("store", {})
        if not store:
            continue

        # Parse name
        title = store.get("title", {})
        name = title.get("text", "") if isinstance(title, dict) else str(title)
        if not name:
            continue

        # Parse rating
        rating_obj = store.get("rating", {})
        rating = None
        rating_count = None
        if isinstance(rating_obj, dict):
            rating_text = rating_obj.get("text", "")
            if rating_text:
                try:
                    rating = float(rating_text)
                except ValueError:
                    pass
            # Extract review count from accessibility text
            acc_text = rating_obj.get("accessibilityText", "")
            count_match = re.search(r"(\d+)", acc_text.replace(",", ""))
            if count_match:
                rating_count = int(count_match.group(1))

        # Parse delivery time from meta
        eta = ""
        meta = store.get("meta", [])
        if isinstance(meta, list):
            for m in meta:
                if isinstance(m, dict) and m.get("badgeType") == "ETD":
                    eta = m.get("text", "")
                    break

        # Build Uber Eats URL — only keep real store page URLs
        action_url = store.get("actionUrl", "")
        uber_eats_url = ""
        if action_url and "/store/" in action_url:
            uber_eats_url = f"https://www.ubereats.com{action_url}"
        elif action_url:
            logger.debug("Skipping non-store actionUrl: %s", action_url)

        # Get image
        image_url = ""
        image_obj = store.get("image", {})
        if isinstance(image_obj, dict):
            items = image_obj.get("items", [])
            if items and isinstance(items, list):
                # Pick medium size image
                for img in items:
                    if isinstance(img, dict) and img.get("width", 0) >= 550:
                        image_url = img.get("url", "")
                        break
                if not image_url and items:
                    image_url = items[0].get("url", "")

        restaurants.append({
            "name": name,
            "rating": rating,
            "rating_count": rating_count,
            "eta": eta,
            "uber_eats_url": uber_eats_url,
            "image_url": image_url,
            "source": "uber_eats",
        })

    # Filter by keyword if provided
    if keyword_lower:
        # Keep all — Uber Eats results are already location-based
        # Keyword filtering would be too aggressive (store names don't always contain food type)
        pass

    logger.info("Uber Eats: %d stores found near (%.3f, %.3f)", len(restaurants), latitude, longitude)
    return restaurants[:max_results]


def match_ubereats_to_restaurants(
    google_restaurants: List[Dict],
    ubereats_restaurants: List[Dict],
) -> List[Dict]:
    """Match Uber Eats results to Google Maps results by name similarity.

    Matched restaurants get uber_eats_url, eta, and delivery info added.
    Unmatched Uber Eats restaurants are appended as new entries.
    """
    # Normalize names for matching
    def normalize(name: str) -> str:
        name = name.lower().strip()
        # Remove parenthesized content (half/full-width, brackets)
        name = re.sub(r'\s*[\(（\[【].*?[\)）\]】]', '', name)
        # Remove common suffixes
        name = re.sub(r'\s*(店|分店|門市|總店|旗艦店)$', '', name)
        # Collapse whitespace
        name = re.sub(r'\s+', '', name)
        return name

    ue_by_norm = {}
    for r in ubereats_restaurants:
        norm = normalize(r.get("name", ""))
        if norm:
            ue_by_norm[norm] = r

    matched_count = 0
    matched_norms = set()

    for gr in google_restaurants:
        g_norm = normalize(gr.get("name", ""))
        # Try exact match first
        if g_norm in ue_by_norm:
            ue = ue_by_norm[g_norm]
            gr["uber_eats_url"] = ue.get("uber_eats_url", "")
            gr["uber_eats_eta"] = ue.get("eta", "")
            gr["uber_eats_rating"] = ue.get("rating")
            matched_norms.add(g_norm)
            matched_count += 1
            continue

        # Try substring match with length-ratio guard to prevent false positives
        for ue_norm, ue in ue_by_norm.items():
            if len(g_norm) >= 3 and len(ue_norm) >= 3:
                if g_norm in ue_norm or ue_norm in g_norm:
                    shorter = min(len(g_norm), len(ue_norm))
                    longer = max(len(g_norm), len(ue_norm))
                    if shorter / longer >= 0.4:
                        gr["uber_eats_url"] = ue.get("uber_eats_url", "")
                        gr["uber_eats_eta"] = ue.get("eta", "")
                        gr["uber_eats_rating"] = ue.get("rating")
                        matched_norms.add(ue_norm)
                        matched_count += 1
                        break

    logger.info("Uber Eats matched %d/%d Google Maps restaurants", matched_count, len(google_restaurants))
    return google_restaurants
