"""
Google Maps restaurant search & data extraction.

This is the refactored core of the original modules/google_maps.py.
Browser pool, selectors, geocoding, and distance logic have been moved to
their respective modules; this file focuses on:

- search_restaurants() -- main entry point
- search_restaurants_parallel() / search_google_maps_restaurants()
- search_restaurants_selenium() -- legacy Selenium pipeline
- extract_restaurant_info_minimal() / extract_restaurant_info_display_only()
- find_search_results()
- is_restaurant_relevant() / remove_duplicate_restaurants() / sort_restaurants_by_distance()
- search_google_maps_web() / search_duckduckgo() / search_google_maps_web_fallback()
- get_restaurant_details()
- test helpers
"""

from typing import List, Dict, Optional, Any, Tuple
import re
import time
import random
import logging
import atexit
from urllib.parse import quote, unquote, parse_qs, urlparse

from bs4 import BeautifulSoup
from geopy.distance import geodesic
from selenium.webdriver.common.by import By

# Intra-package imports
from modules.scraper.browser_pool import (
    USER_AGENTS,
    create_chrome_driver,
    create_chrome_driver_fast,
    browser_pool,
    search_cache,
    BrowserPool,
    SearchCache,
)
from modules.scraper.selectors import (
    SEARCH_RESULT_SELECTORS,
    NAME_SELECTORS,
    ADDRESS_SELECTORS,
    ADDRESS_SELECTORS_DISPLAY_ONLY,
    RATING_SELECTORS,
    RATING_SELECTORS_DISPLAY_ONLY,
    RATING_TEXT_PATTERNS,
    RATING_ARIA_PATTERNS,
    REVIEW_SELECTORS,
    REVIEW_TEXT_PATTERNS,
    PRICE_PATTERNS,
    ADDRESS_REGEX_PATTERNS,
    CLOSED_KEYWORDS,
    OPEN_KEYWORDS,
)
from modules.geo.geocoding import (
    create_session,
    geocode_address,
    smart_address_completion,
    extract_location_from_url,
    parse_google_maps_url,
    generate_fallback_maps_url,
    get_reliable_maps_url,
)
from modules.geo.distance import (
    calculate_distance,
    calculate_walking_distance_from_google_maps,
    calculate_walking_distances_parallel,
    estimate_distance_by_address,
)

logger = logging.getLogger(__name__)


# ===================================================================
# Web / fallback searches (requests-based, no Selenium)
# ===================================================================

def search_google_maps_web(keyword: str, location: str = "\u53f0\u7063") -> List[Dict[str, Any]]:
    """Search Google for Maps restaurant links using plain HTTP requests."""
    try:
        session = create_session()
        search_query = f"{keyword} \u9910\u5ef3 {location}"
        encoded_query = quote(search_query)
        search_url = f"https://www.google.com/search?q={encoded_query}"

        print(f"[WebSearch] Searching: {search_query}")
        response = session.get(search_url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        restaurants: list = []

        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href')
            if href and ('maps.google' in href or 'maps.app.goo.gl' in href):
                if href.startswith('/url?'):
                    url_param = parse_qs(urlparse(href).query).get('url', [None])[0]
                    if url_param:
                        href = url_param
                restaurant_info = parse_google_maps_url(href)
                if restaurant_info and restaurant_info.get('name'):
                    if not any(r['name'] == restaurant_info['name'] for r in restaurants):
                        restaurants.append(restaurant_info)
                        if len(restaurants) >= 10:
                            break
        return restaurants
    except Exception as e:
        print(f"[WebSearch] Failed: {e}")
        return []


def search_duckduckgo(keyword: str, location: str = "\u53f0\u7063") -> List[Dict[str, Any]]:
    """Search DuckDuckGo for Maps restaurant links (backup)."""
    try:
        session = create_session()
        search_query = f"{keyword} \u9910\u5ef3 {location} site:maps.google.com"
        encoded_query = quote(search_query)
        search_url = f"https://duckduckgo.com/html/?q={encoded_query}"

        print(f"[DuckDuckGo] Searching: {search_query}")
        response = session.get(search_url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        restaurants: list = []

        results = soup.find_all('a', class_='result__a')
        for result in results:
            href = result.get('href')
            if href and 'maps.google' in href:
                restaurant_info = parse_google_maps_url(href)
                if restaurant_info and restaurant_info.get('name'):
                    restaurants.append(restaurant_info)
                    if len(restaurants) >= 5:
                        break
        return restaurants
    except Exception as e:
        print(f"[DuckDuckGo] Failed: {e}")
        return []


def search_google_maps_web_fallback(keyword: str, location_info: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """Fallback search using plain HTTP requests."""
    try:
        location_str = "\u53f0\u7063"
        if location_info and location_info.get('address'):
            location_str = location_info['address']
        return search_google_maps_web(keyword, location_str)
    except Exception as e:
        logger.error(f"Fallback search failed: {e}")
        return []


# ===================================================================
# Selenium search-result finders
# ===================================================================

def find_search_results(driver) -> list:
    """Locate search-result elements on the current page using multiple selector strategies."""
    result_elements: list = []
    for selector in SEARCH_RESULT_SELECTORS:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                logger.info(f"Selector {selector} found {len(elements)} elements")
                result_elements = elements
                break
        except Exception:
            continue
    return result_elements


# ===================================================================
# Restaurant info extraction
# ===================================================================

def _extract_name(element) -> Optional[str]:
    """Extract restaurant name from a search-result element."""
    for selector in NAME_SELECTORS:
        try:
            name_element = element.find_element(By.CSS_SELECTOR, selector)
            name = name_element.text.strip()
            if name and len(name) > 1:
                return name
        except Exception:
            continue
    return None


def _extract_address_from_selectors(element, selectors, location_info, search_keyword):
    """Try to extract a Taiwan address using the given CSS selectors."""
    for selector in selectors:
        try:
            address_elements = element.find_elements(By.CSS_SELECTOR, selector)
            for addr_elem in address_elements:
                addr_text = addr_elem.text.strip()
                addr_text = re.sub(r'^[\u00b7\u2022\-\s\u00b7]+', '', addr_text)
                addr_text = re.sub(r'^[^\u4e00-\u9fff\d]+', '', addr_text)
                addr_text = addr_text.strip()

                # Try to complete incomplete addresses
                if addr_text and not any(
                    city in addr_text
                    for city in ['\u53f0\u5317\u5e02', '\u65b0\u5317\u5e02', '\u6843\u5712\u5e02',
                                 '\u53f0\u4e2d\u5e02', '\u53f0\u5357\u5e02', '\u9ad8\u96c4\u5e02']
                ):
                    if location_info and location_info.get('address'):
                        base_location = location_info['address']
                        city_match = re.search(
                            r'(\u53f0\u5317\u5e02|\u65b0\u5317\u5e02|\u6843\u5712\u5e02|\u53f0\u4e2d\u5e02|\u53f0\u5357\u5e02|\u9ad8\u96c4\u5e02)',
                            base_location,
                        )
                        district_match = re.search(r'([^\u5e02]+\u5340)', base_location)
                        if city_match:
                            city = city_match.group(1)
                            district = district_match.group(1) if district_match else ''
                            addr_text = f"{city}{district}{addr_text}"

                if (
                    addr_text
                    and len(addr_text) > 3
                    and any(kw in addr_text for kw in ['\u8def', '\u8857', '\u5df7', '\u865f', '\u5e02', '\u5340', '\u7e23', '\u9109'])
                    and not any(avoid in addr_text for avoid in ['\u8a55\u8ad6', '\u5247\u8a55\u8ad6', '\u661f\u7d1a', '\u516c\u91cc', '\u5c0f\u6642', '\u71df\u696d', 'Google', '\u5206\u9418'])
                    and not re.search(r'\d+\.\d+\s*\(\d+(?:,\d+)?\)', addr_text)
                ):
                    is_complete = any(
                        city in addr_text
                        for city in ['\u53f0\u5317\u5e02', '\u65b0\u5317\u5e02', '\u6843\u5712\u5e02',
                                     '\u53f0\u4e2d\u5e02', '\u53f0\u5357\u5e02', '\u9ad8\u96c4\u5e02']
                    )
                    if is_complete:
                        return addr_text, True
                    else:
                        if search_keyword:
                            completed_addr = smart_address_completion(addr_text, search_keyword)
                            if completed_addr != addr_text:
                                return completed_addr, True
                        return addr_text, False
        except Exception:
            continue
    return None, False


def _extract_address_from_text(element):
    """Fallback: extract a Taiwan address from the element's full text."""
    try:
        full_text = element.text
        for pattern in ADDRESS_REGEX_PATTERNS:
            matches = re.findall(pattern, full_text)
            if matches:
                for match in matches:
                    if len(match.strip()) > 3:
                        return match.strip()
    except Exception:
        pass
    return None


def _extract_address_from_spans(element):
    """Last resort: scan all <span> children for address-like text."""
    try:
        spans = element.find_elements(By.TAG_NAME, "span")
        for span in spans:
            span_text = span.text.strip()
            if (
                span_text
                and len(span_text) > 3
                and any(kw in span_text for kw in [
                    '\u5e02', '\u7e23', '\u5340', '\u9109', '\u93ae', '\u8def', '\u8857',
                    '\u5927\u9053', '\u5df7', '\u865f',
                    '\u53f0\u5317', '\u65b0\u5317', '\u6843\u5712', '\u53f0\u4e2d', '\u53f0\u5357', '\u9ad8\u96c4',
                ])
                and not any(avoid in span_text for avoid in [
                    '\u8a55\u8ad6', '\u661f\u7d1a', '\u516c\u91cc', 'Google', 'Maps',
                    '\u5c0f\u6642\u524d', '\u71df\u696d\u4e2d', '\u5df2\u6253\u70ca',
                    'rating', 'review',
                ])
            ):
                return span_text
    except Exception:
        pass
    return None


def _extract_rating(element, selectors, patterns):
    """Extract a 0-5 rating from the element."""
    for selector in selectors:
        try:
            rating_elements = element.find_elements(By.CSS_SELECTOR, selector)
            for rating_element in rating_elements:
                rating_text = rating_element.text.strip()
                for pattern in patterns:
                    rating_match = re.search(pattern, rating_text, re.IGNORECASE)
                    if rating_match:
                        rating_value = float(rating_match.group(1))
                        if 0 <= rating_value <= 5:
                            return rating_value
        except Exception:
            continue
    return None


def _extract_rating_from_aria(element):
    """Fallback: extract rating from aria-label or short text of any child element."""
    try:
        all_elements = element.find_elements(By.XPATH, ".//*")
        for elem in all_elements:
            aria_label = elem.get_attribute('aria-label') or ''
            elem_text = elem.text.strip()
            for text in [aria_label, elem_text]:
                if text and len(text) < 50:
                    for pattern in RATING_ARIA_PATTERNS:
                        rating_match = re.search(pattern, text, re.IGNORECASE)
                        if rating_match:
                            rating_value = float(rating_match.group(1))
                            if 0 <= rating_value <= 5:
                                return rating_value
    except Exception:
        pass
    return None


def _extract_review_count(element):
    """Extract review count from the element."""
    for selector in REVIEW_SELECTORS:
        try:
            review_element = element.find_element(By.CSS_SELECTOR, selector)
            review_text = review_element.text.strip()
            for pattern in REVIEW_TEXT_PATTERNS:
                review_match = re.search(pattern, review_text, re.IGNORECASE)
                if review_match:
                    return int(review_match.group(1))
        except Exception:
            continue

    # Fallback: full text
    try:
        full_text = element.text
        for pattern in REVIEW_TEXT_PATTERNS:
            review_match = re.search(pattern, full_text, re.IGNORECASE)
            if review_match:
                count = int(review_match.group(1))
                if 0 < count < 100000:
                    return count
    except Exception:
        pass
    return None


def _extract_price(element):
    """Extract price level from the element's text."""
    try:
        full_text = element.text
        for pattern in PRICE_PATTERNS:
            price_match = re.search(pattern, full_text)
            if price_match:
                groups = price_match.groups()
                if len(groups) == 2:
                    try:
                        low_price = int(groups[0].replace(',', ''))
                        high_price = int(groups[1].replace(',', ''))
                        if 1 <= low_price <= 10000 and 1 <= high_price <= 10000 and low_price < high_price:
                            return f"${groups[0]}-{groups[1]}"
                    except ValueError:
                        continue
                elif len(groups) == 1:
                    try:
                        price = int(groups[0].replace(',', ''))
                        if 1 <= price <= 10000:
                            if '+' in price_match.group(0):
                                return f"${groups[0]}+"
                            else:
                                return f"${groups[0]}"
                    except ValueError:
                        continue
    except Exception:
        pass
    return None


def _parse_hours_status(text: str) -> Tuple[Optional[bool], Optional[str], Optional[str], Optional[str]]:
    """Parse business hours / open-now status from a text snippet."""
    if not text:
        return None, None, None, None

    t = re.sub(r"\s+", " ", text)
    open_now = None
    hours_status = None
    next_open_time = None
    close_time = None

    if re.search(r"(\u5df2\u6b47\u696d|\u6c38\u4e45\u6b47\u696d|\u66ab\u505c\u71df\u696d)", t):
        return False, "\u5df2\u6b47\u696d/\u66ab\u505c\u71df\u696d", None, None

    if re.search(r"24\s*\u5c0f\u6642\s*\u71df\u696d", t):
        return True, "24 \u5c0f\u6642\u71df\u696d", None, None

    if "\u71df\u696d\u4e2d" in t or "\u5373\u5c07\u6253\u70ca" in t:
        open_now = True
    if "\u4f11\u606f\u4e2d" in t or "\u5df2\u6253\u70ca" in t or ("\u6253\u70ca" in t and "\u5373\u5c07\u6253\u70ca" not in t):
        open_now = False if open_now is None else open_now

    m_open = re.search(r"\u5c07\u65bc\s*(\u4e0a\u5348|\u4e0b\u5348)?\s*(\d{1,2})[:：](\d{2})\s*(\u958b\u9580|\u958b\u59cb\u71df\u696d)", t)
    if m_open:
        next_open_time = f"{m_open.group(1) or ''} {m_open.group(2)}:{m_open.group(3)}".strip()
        open_now = False

    m_close = re.search(r"\u5c07\u65bc\s*(\u4e0a\u5348|\u4e0b\u5348)?\s*(\d{1,2})[:：](\d{2})\s*(?:\u7d50\u675f\u71df\u696d|\u95dc\u9580|\u6253\u70ca)", t)
    if m_close:
        close_time = f"{m_close.group(1) or ''} {m_close.group(2)}:{m_close.group(3)}".strip()
        if open_now is None:
            open_now = True

    status_snippets: list[str] = []
    for seg in re.split(r"[\u00B7\u00b7\u2022\|\\/\n]", t):
        seg = seg.strip()
        if any(k in seg for k in ["\u71df\u696d", "\u6253\u70ca", "\u4f11\u606f", "\u958b\u9580"]):
            if 0 < len(seg) <= 40:
                status_snippets.append(seg)
    if status_snippets:
        hours_status = " \u00b7 ".join(dict.fromkeys(status_snippets))

    return open_now, hours_status, next_open_time, close_time


def _extract_hours(element):
    """Extract open/closed status and hours info from the element."""
    hours_open_now, hours_status, next_open, closes_at = _parse_hours_status(element.text)

    if hours_open_now is None and not hours_status:
        try:
            child_nodes = element.find_elements(By.XPATH, ".//*")
            collected: list[str] = []
            for node in child_nodes[:40]:
                al = node.get_attribute('aria-label') or ''
                tx = node.text or ''
                if any(k in al for k in ["\u71df\u696d", "\u6253\u70ca", "\u4f11\u606f", "\u958b\u9580"]) or \
                   any(k in tx for k in ["\u71df\u696d", "\u6253\u70ca", "\u4f11\u606f", "\u958b\u9580"]):
                    collected.append(al or tx)
            if collected:
                hours_open_now, hours_status, next_open, closes_at = _parse_hours_status(" | ".join(collected))
        except Exception:
            pass

    return hours_open_now, hours_status, next_open, closes_at


# ---------------------------------------------------------------------------
# Main extraction functions
# ---------------------------------------------------------------------------

def extract_restaurant_info_display_only(
    element,
    location_info: Optional[Dict] = None,
    search_keyword: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Ultra-compact extraction -- only fields needed for the frontend display.
    ~30-40 % faster than extract_restaurant_info_minimal.
    """
    restaurant_info: Dict[str, Any] = {
        'name': '',
        'address': '',
        'rating': None,
        'price_level': None,
        'distance_km': None,
        'distance': '\u8ddd\u96e2\u672a\u77e5',
        'maps_url': '',
        'google_maps_url': '',
        'walking_minutes': None,
        'open_now': None,
    }

    try:
        name = _extract_name(element)
        if not name:
            return None
        restaurant_info['name'] = name

        # Address (display-only selectors)
        for selector in ADDRESS_SELECTORS_DISPLAY_ONLY:
            try:
                address_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for addr_elem in address_elements:
                    addr_text = addr_elem.text.strip()
                    addr_text = re.sub(r'^[\u00b7\u2022\-\s\u00b7]+', '', addr_text)
                    if (
                        addr_text and len(addr_text) > 3
                        and any(kw in addr_text for kw in ['\u8def', '\u8857', '\u5df7', '\u865f', '\u5e02', '\u5340'])
                        and not any(avoid in addr_text for avoid in ['\u8a55\u8ad6', '\u5247\u8a55\u8ad6', '\u661f\u7d1a', '\u516c\u91cc'])
                    ):
                        restaurant_info['address'] = addr_text
                        break
                if restaurant_info['address']:
                    break
            except Exception:
                continue

        # Fallback address from full text
        if not restaurant_info['address']:
            try:
                full_text = element.text
                pattern = ADDRESS_REGEX_PATTERNS[0]  # most complete pattern
                match = re.search(pattern, full_text)
                if match:
                    restaurant_info['address'] = match.group(0).strip()
            except Exception:
                pass

        # Rating
        restaurant_info['rating'] = _extract_rating(element, RATING_SELECTORS_DISPLAY_ONLY, RATING_TEXT_PATTERNS)

        # Price
        restaurant_info['price_level'] = _extract_price(element)

        # Open/closed (simple)
        try:
            full_text = element.text
            if any(kw in full_text for kw in CLOSED_KEYWORDS[:5]):  # first 5 closed keywords
                restaurant_info['open_now'] = False
            elif any(kw in full_text for kw in OPEN_KEYWORDS):
                restaurant_info['open_now'] = True
        except Exception:
            pass

        # Maps URL
        try:
            links = element.find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute('href') or ''
                if 'google.com/maps' in href:
                    restaurant_info['maps_url'] = href
                    break
        except Exception:
            pass

        # Distance (straight line only)
        if location_info and location_info.get('coords'):
            try:
                if restaurant_info.get('address'):
                    restaurant_coords = geocode_address(restaurant_info['address'], search_keyword)
                    if restaurant_coords:
                        user_coords = location_info['coords']
                        distance_km = geodesic(user_coords, restaurant_coords).kilometers
                        restaurant_info['distance_km'] = round(distance_km, 2)
                        restaurant_info['distance'] = f"{restaurant_info['distance_km']}km"
            except Exception:
                pass

        return restaurant_info
    except Exception as e:
        logger.debug(f"display_only extraction failed: {e}")
        return None


def extract_restaurant_info_minimal(
    element,
    location_info: Optional[Dict] = None,
    search_keyword: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extract restaurant info from a search result element.
    Returns name, address, rating, price, review count, hours, and distance placeholders.
    """
    restaurant_info: Dict[str, Any] = {
        'name': '',
        'address': '',
        'rating': None,
        'price_level': None,
        'distance_km': None,
        'distance': '\u8ddd\u96e2\u672a\u77e5',
        'maps_url': '',
        'phone': '',
        'review_count': None,
        'open_now': None,
        'hours_status': None,
        'next_open_time': None,
        'close_time': None,
    }

    try:
        # Name
        name = _extract_name(element)
        if not name:
            return None
        restaurant_info['name'] = name

        # Address
        addr_text, address_found = _extract_address_from_selectors(
            element, ADDRESS_SELECTORS, location_info, search_keyword,
        )
        if addr_text:
            restaurant_info['address'] = addr_text
        if not address_found:
            fallback_addr = _extract_address_from_text(element)
            if fallback_addr:
                restaurant_info['address'] = fallback_addr
                address_found = True
        if not address_found and not restaurant_info['address']:
            span_addr = _extract_address_from_spans(element)
            if span_addr:
                restaurant_info['address'] = span_addr

        # Rating (full selectors)
        rating = _extract_rating(element, RATING_SELECTORS, RATING_TEXT_PATTERNS)
        if rating is None:
            rating = _extract_rating_from_aria(element)
        restaurant_info['rating'] = rating

        # Review count
        restaurant_info['review_count'] = _extract_review_count(element)

        # Price
        restaurant_info['price_level'] = _extract_price(element)

        # Hours / open status
        try:
            open_now, hours_status, next_open, closes_at = _extract_hours(element)
            restaurant_info['open_now'] = open_now
            restaurant_info['hours_status'] = hours_status
            restaurant_info['next_open_time'] = next_open
            restaurant_info['close_time'] = closes_at
        except Exception:
            pass

        # Distance placeholders (actual values computed in parallel later)
        restaurant_info['distance_km'] = None
        restaurant_info['distance'] = "\u8ddd\u96e2\u8a08\u7b97\u4e2d..."
        restaurant_info['walking_minutes'] = None
        restaurant_info['google_maps_url'] = ''

        # Post-process address
        if restaurant_info.get('address'):
            address = restaurant_info['address']
            address = re.sub(r'(\d+)\u865f\u865f(\d+)', r'\1\u865f\2\u6a13', address)
            if re.search(r'\d+\u865f\d+$', address) and not re.search(r'[\u6a13\u5c64F]', address):
                address = re.sub(r'(\d+\u865f)(\d+)$', r'\1\2\u6a13', address)
            restaurant_info['address'] = address

        return restaurant_info

    except Exception as e:
        logger.debug(f"extract_restaurant_info_minimal failed: {e}")
        return None


def extract_restaurant_info_from_element_improved(
    element,
    location_info: Optional[Dict] = None,
    driver=None,
    keyword: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Legacy wrapper -- delegates to extract_restaurant_info_minimal."""
    return extract_restaurant_info_minimal(element, location_info, keyword)


# ===================================================================
# Relevance / deduplication / sorting
# ===================================================================

def is_restaurant_relevant(restaurant_name: str, keyword: str) -> bool:
    """Check whether a restaurant name is relevant to the search keyword."""
    if not restaurant_name or len(restaurant_name) < 2:
        return True

    restaurant_keywords = [
        '\u9910\u5ef3', '\u98ef\u5e97', '\u98df\u5802', '\u5c0f\u5403', '\u7f8e\u98df', '\u6599\u7406',
        '\u706b\u934b', '\u71d2\u70e4', '\u62c9\u9eb5', '\u7fa9\u5927\u5229\u9eb5', '\u725b\u6392', '\u58fd\u53f8',
        '\u7f8a\u8089', '\u725b\u8089', '\u8c6c\u8089', '\u96de\u8089', '\u6d77\u9bae', '\u7d20\u98df',
        '\u65e9\u9910', '\u5348\u9910', '\u665a\u9910', '\u5bb5\u591c', '\u5496\u5561', '\u8336',
        '\u4e2d\u5f0f', '\u897f\u5f0f', '\u65e5\u5f0f', '\u97d3\u5f0f', '\u6cf0\u5f0f', '\u7fa9\u5f0f',
        '\u5e97', '\u9928', '\u574a', '\u8ed2', '\u95a3', '\u6a13', '\u5c4b',
    ]

    name_lower = restaurant_name.lower()
    keyword_lower = keyword.lower()

    if keyword_lower in name_lower:
        return True
    if any(kw in restaurant_name for kw in restaurant_keywords):
        return True

    exclude_keywords = [
        '\u9280\u884c', '\u91ab\u9662', '\u5b78\u6821', '\u516c\u53f8', '\u653f\u5e9c',
        '\u6a5f\u95dc', '\u505c\u8eca\u5834', '\u52a0\u6cb9\u7ad9', '\u4fbf\u5229\u5546\u5e97', '\u8d85\u5e02',
    ]
    if any(kw in restaurant_name for kw in exclude_keywords):
        return False

    return True


def remove_duplicate_restaurants(restaurants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicates by restaurant name."""
    seen_names: set = set()
    unique: list = []
    for restaurant in restaurants:
        name = restaurant.get('name', '').strip()
        if name and name not in seen_names:
            seen_names.add(name)
            unique.append(restaurant)
    return unique


def sort_restaurants_by_distance(restaurants: List[Dict[str, Any]], user_coords: Tuple[float, float]) -> List[Dict[str, Any]]:
    """Sort restaurants by distance_km (ascending, None last)."""
    def get_distance_key(restaurant):
        distance = restaurant.get('distance_km')
        return distance if distance is not None else float('inf')
    return sorted(restaurants, key=get_distance_key)


# ===================================================================
# Open/closed filter helper
# ===================================================================

def _is_open(r: Dict[str, Any]) -> bool:
    on = r.get('open_now')
    if on is False:
        return False
    status = (r.get('hours_status') or '').strip()
    if status:
        if any(k in status for k in CLOSED_KEYWORDS):
            return False
    return True


# ===================================================================
# Search pipelines
# ===================================================================

def search_google_maps_restaurants(
    keyword: str,
    location_info: Optional[Dict] = None,
    max_results: int = 12,
) -> List[Dict[str, Any]]:
    """Fast Google Maps search using the browser pool (single page load)."""
    restaurants: List[Dict[str, Any]] = []
    try:
        with browser_pool.get_browser() as driver:
            if location_info and (location_info.get('display_address') or location_info.get('address')):
                display_anchor = location_info.get('display_address') or location_info.get('address')
                query = f"{display_anchor} {keyword} \u9910\u5ef3"
            else:
                query = f"{keyword} \u9910\u5ef3 \u53f0\u7063"
            encoded_query = quote(query)

            if location_info and location_info.get('coords'):
                lat, lng = location_info['coords']
                center = f"@{lat},{lng},14z"
            else:
                center = ""

            url = (
                f"https://www.google.com/maps/search/{encoded_query}/{center}"
                if center
                else f"https://www.google.com/maps/search/{encoded_query}"
            )
            logger.info(f"Maps fast search: {url}")
            driver.get(url)
            time.sleep(1.0)

            result_elements = find_search_results(driver)
            if not result_elements:
                logger.debug("Maps fast search found no result elements")
                return []

            for el in result_elements[:max_results]:
                try:
                    info = extract_restaurant_info_minimal(el, location_info, keyword)
                    if info and info.get('name'):
                        restaurants.append(info)
                except Exception as ie:
                    logger.debug(f"Failed to parse restaurant element: {ie}")

        return restaurants
    except Exception as e:
        logger.debug(f"Maps fast search exception: {e}")
        return restaurants


def search_restaurants_parallel(
    keyword: str,
    location_info: Optional[Dict] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    Parallel restaurant search -- browser pool + in-memory cache.
    """
    cached_results = search_cache.get(keyword, location_info)
    if cached_results:
        logger.info(f"Using cached results for keyword: {keyword}")
        return cached_results[:max_results]

    logger.info(f"Starting parallel restaurant search: {keyword}")
    start_time = time.time()

    all_restaurants: List[Dict[str, Any]] = []
    try:
        maps_results = search_google_maps_restaurants(keyword, location_info)
        if maps_results:
            all_restaurants.extend(maps_results)
    except Exception as e:
        logger.error(f"Parallel search pipeline failed: {e}")

    if not all_restaurants:
        logger.warning("No restaurant results (fallback empty list)")
        return []

    unique_restaurants = remove_duplicate_restaurants(all_restaurants)
    unique_restaurants = [r for r in unique_restaurants if _is_open(r)]

    if location_info and location_info.get('coords'):
        unique_restaurants = sort_restaurants_by_distance(unique_restaurants, location_info['coords'])

    final_results = unique_restaurants[:max_results]
    if final_results:
        search_cache.set(keyword, location_info, final_results)

    elapsed = time.time() - start_time
    logger.info(f"[COMPLETE] Search done, {len(final_results)} restaurants, {elapsed:.2f}s")
    return final_results


def execute_search_strategy_with_pool(
    strategy: Dict,
    location_info: Optional[Dict] = None,
    keyword: str = "",
) -> List[Dict[str, Any]]:
    """Execute a single search strategy using the browser pool."""
    restaurants: list = []
    try:
        with browser_pool.get_browser() as driver:
            logger.info(f"Executing {strategy['name']}: {strategy['url']}")
            driver.get(strategy['url'])
            time.sleep(0.5)

            if "sorry" in driver.current_url.lower() or "captcha" in driver.page_source.lower():
                logger.warning(f"[ERROR] {strategy['name']} blocked by Google")
                return restaurants

            result_elements = find_search_results(driver)
            if not result_elements:
                logger.warning(f"[ERROR] {strategy['name']} found no results")
                return restaurants

            for element in result_elements[:8]:
                try:
                    restaurant_info = extract_restaurant_info_minimal(element, location_info, keyword)
                    if restaurant_info and restaurant_info.get('name'):
                        if is_restaurant_relevant(restaurant_info['name'], keyword):
                            restaurants.append(restaurant_info)
                except Exception as e:
                    logger.debug(f"Restaurant info extraction failed: {e}")
                    continue

            logger.info(f"{strategy['name']} extracted {len(restaurants)} restaurants")
    except Exception as e:
        logger.error(f"[ERROR] {strategy['name']} execution failed: {e}")
    return restaurants


def search_restaurants_selenium(
    keyword: str,
    location_info: Optional[Dict] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Legacy Selenium search pipeline with multiple strategy fallbacks."""
    driver = None
    try:
        logger.info(f"Starting Selenium restaurant search: {keyword}")

        try:
            from modules.browser_pool import get_browser, release_browser
            driver = get_browser()
            logger.info("Using legacy browser pool")
        except Exception as e:
            logger.warning(f"Legacy browser pool unavailable, creating driver: {e}")
            driver = create_chrome_driver(headless=True)

        if location_info and (location_info.get('display_address') or location_info.get('address')):
            display_anchor = location_info.get('display_address') or location_info.get('address')
            search_query = f"{display_anchor} {keyword} \u9910\u5ef3"
        else:
            search_query = f"{keyword} \u9910\u5ef3 \u53f0\u7063"

        encoded_query = quote(search_query)

        search_coords = "25.0478,121.5318"
        if location_info and location_info.get('coordinates'):
            lat, lng = location_info['coordinates']
            search_coords = f"{lat},{lng}"

        search_strategies = [
            f"https://www.google.com/maps/search/{encoded_query}/@{search_coords},12z",
            f"https://www.google.com/search?tbm=lcl&q={encoded_query}&hl=zh-TW",
            f"https://www.google.com/search?q={encoded_query}+\u5730\u5740&hl=zh-TW",
        ]

        result_elements: list = []
        for strategy_index, search_url in enumerate(search_strategies):
            logger.info(f"Trying search strategy {strategy_index + 1}: {search_url}")
            try:
                driver.get(search_url)
                time.sleep(random.uniform(1.0, 1.8))

                if "sorry" in driver.current_url.lower() or "captcha" in driver.page_source.lower():
                    logger.warning(f"Strategy {strategy_index + 1} blocked by Google")
                    continue

                result_elements = find_search_results(driver)
                if result_elements:
                    logger.info(f"Strategy {strategy_index + 1} found {len(result_elements)} results")
                    break
                else:
                    logger.warning(f"Strategy {strategy_index + 1} found no results")
            except Exception as e:
                logger.warning(f"Strategy {strategy_index + 1} failed: {e}")
                continue

        if not result_elements:
            logger.warning("All search strategies failed")
            return []

        restaurants: list = []
        for i, element in enumerate(result_elements[:max_results]):
            try:
                restaurant_info = extract_restaurant_info_minimal(element, location_info, keyword)
                if restaurant_info and restaurant_info.get('name'):
                    if is_restaurant_relevant(restaurant_info['name'], keyword):
                        restaurants.append(restaurant_info)
                        logger.info(f"Found restaurant: {restaurant_info['name']}")
            except Exception as e:
                logger.error(f"Extraction of result {i + 1} failed: {e}")
                continue

        logger.info(f"Total restaurants found: {len(restaurants)}")
        return restaurants

    except Exception as e:
        logger.error(f"Selenium search failed: {e}")
        return []
    finally:
        if driver:
            try:
                from modules.browser_pool import release_browser
                release_browser(driver)
                logger.info("Browser returned to legacy pool")
            except Exception as e:
                logger.warning(f"Legacy pool return failed, closing directly: {e}")
                try:
                    driver.quit()
                except Exception:
                    pass


# ===================================================================
# Main entry point
# ===================================================================

def search_restaurants(
    keyword: str,
    user_address: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """
    Primary restaurant search function (supports multiple input formats).

    :param keyword: search keyword
    :param user_address: user address or Google Maps short URL
    :param max_results: maximum number of results
    :return: list of restaurant info dicts
    """
    # Check SQLite cache
    try:
        from modules.sqlite_cache_manager import get_restaurant_cache, set_restaurant_cache
        cache_location = user_address or "unknown"
        cached_results = get_restaurant_cache(keyword, cache_location, max_results)
        if cached_results:
            return cached_results
    except Exception as e:
        logger.warning(f"Cache system unavailable: {e}")

    location_info = None

    # Process user location
    if user_address:
        if user_address.startswith('http') and any(
            s in user_address
            for s in ['maps.app.goo.gl', 'maps.google', 'g.co/kgs/', 'goo.gl']
        ):
            logger.info(f"Processing Google Maps URL: {user_address}")
            location_data = extract_location_from_url(user_address)
            if location_data:
                lat, lng, place_name = location_data
                coord_str = f"{lat},{lng}"
                location_info = {
                    'coords': (lat, lng),
                    'coordinates': (lat, lng),
                    'address': coord_str,
                    'display_address': place_name or coord_str,
                }
                logger.info(f"Extracted location from URL: {place_name} ({lat}, {lng})")
        else:
            logger.info(f"Processing address: {user_address}")
            coords = geocode_address(user_address, user_address)
            if coords:
                location_info = {
                    'coords': coords,
                    'coordinates': coords,
                    'address': user_address,
                    'display_address': user_address,
                }
                logger.info(f"Address coordinates: {coords}")
            else:
                location_info = {
                    'coords': None,
                    'coordinates': None,
                    'address': user_address,
                    'display_address': user_address,
                }
                logger.warning(f"Cannot geocode address, using for search only: {user_address}")

    # Parallel search (preferred) -> Selenium fallback -> web fallback
    try:
        results = search_restaurants_parallel(keyword, location_info, max_results)
        if results:
            logger.info(f"Parallel search found {len(results)} results")
        else:
            logger.info("Parallel search returned nothing, trying Selenium")
            results = search_restaurants_selenium(keyword, location_info, max_results)
    except Exception as e:
        logger.warning(f"Parallel search failed: {e}, falling back to Selenium")
        results = search_restaurants_selenium(keyword, location_info, max_results)

    if not results:
        logger.info("Selenium search returned nothing, trying web fallback")
        results = search_google_maps_web_fallback(keyword, location_info)

    # Filter closed restaurants
    results = [r for r in results if _is_open(r)]

    # Optimise Maps URLs
    for restaurant in results:
        if restaurant.get('name'):
            reliable_url = get_reliable_maps_url(restaurant)
            restaurant['maps_url'] = reliable_url
            logger.debug(f"Optimised URL for {restaurant['name']}: {reliable_url[:50]}...")

    # Store in SQLite cache
    try:
        from modules.sqlite_cache_manager import set_restaurant_cache
        cache_location = user_address or "unknown"
        set_restaurant_cache(keyword, cache_location, max_results, results)
    except Exception as e:
        logger.warning(f"Cache save failed: {e}")

    return results


# ===================================================================
# Restaurant details
# ===================================================================

def get_restaurant_details(maps_url: str) -> Optional[Dict[str, Any]]:
    """Fetch detailed restaurant info from a Maps URL (placeholder)."""
    try:
        session = create_session()
        response = session.get(maps_url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        details: Dict[str, Any] = {
            'name': None,
            'rating': None,
            'review_count': None,
            'price_level': None,
            'phone': None,
            'website': None,
            'hours': None,
            'address': None,
        }
        return details
    except Exception as e:
        print(f"[Details] Failed: {e}")
        return None


# ===================================================================
# Test helpers
# ===================================================================

def test_search_cases():
    """Run a set of test search cases."""
    test_cases = [
        ("https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6", "\u7f8a\u8089", "\u77ed\u7db2\u5740+\u7f8a\u8089"),
        ("243\u65b0\u5317\u5e02\u6cf0\u5c71\u5340\u660e\u5fd7\u8def\u4e8c\u6bb5210\u865f", "\u706b\u934b", "\u6cf0\u5c71\u706b\u934b"),
        ("\u5f70\u5316\u5927\u4f5b", "\u71d2\u70e4", "\u5f70\u5316\u5927\u4f5b\u71d2\u70e4"),
        ("\u53f0\u5317\u4e2d\u5c71\u5340", "\u7fa9\u5927\u5229\u9eb5", "\u4e2d\u5c71\u5340\u7fa9\u5927\u5229\u9eb5(\u7121\u8a73\u7d30\u5730\u5740)"),
    ]

    for idx, (addr, kw, desc) in enumerate(test_cases, 1):
        print(f"\n=== Test case {idx}: {desc} ===")
        print(f"Location: {addr}")
        print(f"Keyword: {kw}")
        print("-" * 50)
        try:
            results = search_restaurants(keyword=kw, user_address=addr, max_results=5)
            if not results:
                print("[ERROR] No restaurants found!")
            else:
                print(f"Found {len(results)} restaurants:")
                for i, restaurant in enumerate(results, 1):
                    print(f"\n{i}. {restaurant['name']}")
                    print(f"   Address: {restaurant.get('address', 'N/A')}")
                    if restaurant.get('distance_km') is not None:
                        print(f"   Distance: {restaurant['distance_km']} km")
                    if restaurant.get('rating'):
                        print(f"   Rating: {restaurant['rating']}")
                    if restaurant.get('price_level'):
                        print(f"   Price: {restaurant['price_level']}")
                    if restaurant.get('maps_url'):
                        print(f"   Maps: {restaurant['maps_url']}")
        except Exception as e:
            print(f"[ERROR] Search failed: {e}")
        print("\n" + "=" * 80)
        time.sleep(0.5)


def test_search():
    """Run test suite."""
    print("Starting Google Maps restaurant search tests")
    print("=" * 80)
    test_search_cases()


# ===================================================================
# Cleanup
# ===================================================================

def cleanup_resources():
    """Clean up browser pool resources."""
    try:
        browser_pool.close_all()
        logger.info("Resources cleaned up")
    except Exception as e:
        logger.error(f"[ERROR] Resource cleanup failed: {e}")


atexit.register(cleanup_resources)


if __name__ == "__main__":
    test_search()
