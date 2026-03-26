"""
Geocoding, address normalisation, URL extraction and parsing for Taiwan.

Contains all address-related logic originally in modules/google_maps.py:
- expand_short_url / extract_location_from_url
- normalize_taiwan_address / smart_address_completion
- geocode_address / geocode_address_with_options
- validate_and_select_best_address / is_valid_taiwan_address
- clean_address / is_complete_address
- extract_address_from_maps_url / parse_google_maps_url
- generate_fallback_maps_url / validate_maps_url / get_reliable_maps_url
- get_location_candidates
"""

from typing import List, Dict, Optional, Any, Tuple
import re
import time
import random
import logging
import requests
import urllib3
from urllib.parse import quote, unquote, parse_qs, urlparse
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

# Selenium -- only needed for extract_address_from_maps_url
from selenium.webdriver.common.by import By

# ---------------------------------------------------------------------------
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger(__name__)

# Re-use the User-Agent pool from the browser pool module
from modules.scraper.browser_pool import USER_AGENTS

# CSS selectors used in extract_address_from_maps_url
from modules.scraper.selectors import MAPS_PAGE_ADDRESS_SELECTORS

# ---------------------------------------------------------------------------
# Helper: requests Session
# ---------------------------------------------------------------------------

def create_session() -> requests.Session:
    """Build a browser-like requests.Session (backup approach)."""
    session = requests.Session()
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    session.headers.update(headers)
    session.verify = False
    return session


# ---------------------------------------------------------------------------
# Short-URL expansion
# ---------------------------------------------------------------------------

def expand_short_url(short_url: str, max_redirects: int = 10) -> str:
    """
    Expand a Google Maps short URL by following redirects step-by-step.

    :param short_url: short URL (maps.app.goo.gl, g.co/kgs, etc.)
    :param max_redirects: maximum redirect hops
    :return: expanded full URL (or original if expansion fails)
    """
    try:
        session = create_session()
        session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })

        current_url = short_url
        redirect_count = 0

        while redirect_count < max_redirects:
            try:
                response = session.get(current_url, allow_redirects=False, timeout=15)
                if response.status_code in [301, 302, 303, 307, 308]:
                    location = response.headers.get('Location')
                    if location:
                        if location.startswith('/'):
                            from urllib.parse import urljoin
                            current_url = urljoin(current_url, location)
                        else:
                            current_url = location
                        redirect_count += 1
                        logger.info(f"Redirect {redirect_count}: {current_url}")
                        continue

                if response.status_code == 200:
                    final_url = current_url
                    logger.info(f"Short URL expanded: {short_url} -> {final_url}")
                    return final_url

                break
            except requests.RequestException as e:
                logger.warning(f"Redirect tracking failed: {e}")
                break

        # Fallback: follow all redirects at once
        try:
            response = session.get(short_url, allow_redirects=True, timeout=15)
            final_url = response.url
            logger.info(f"Direct expansion succeeded: {short_url} -> {final_url}")
            return final_url
        except Exception as e:
            logger.error(f"Short URL expansion completely failed: {e}")
            return short_url

    except Exception as e:
        logger.error(f"expand_short_url error: {e}")
        return short_url


# ---------------------------------------------------------------------------
# Extract location from Google Maps URL
# ---------------------------------------------------------------------------

def extract_location_from_url(url: str) -> Optional[Tuple[float, float, str]]:
    """
    Extract (latitude, longitude, place_name) from a Google Maps URL.

    Supports short URLs (maps.app.goo.gl, g.co/kgs), place pins (!3d/!4d),
    /@lat,lng viewport centres, and query parameters.
    """
    try:
        original_url = url

        # Expand short URLs
        if 'maps.app.goo.gl' in url or 'goo.gl' in url or 'g.co/kgs/' in url or len(url) < 50:
            logger.info(f"Expanding short URL: {url}")
            url = expand_short_url(url)
            if url == original_url:
                logger.warning("Short URL expansion failed, using original URL")
                try:
                    session = create_session()
                    resp = session.get(original_url, allow_redirects=True, timeout=15)
                    if resp and resp.url:
                        url = resp.url
                        logger.info(f"Second direct expansion succeeded: {original_url} -> {url}")
                except Exception:
                    pass

        logger.info(f"Processing URL: {url}")

        # Prefer place pin coordinates (!3d lat !4d lng), fall back to /@lat,lng
        lat, lng = None, None
        best = None

        place_pair = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
        if place_pair:
            try:
                plat = float(place_pair.group(1))
                plng = float(place_pair.group(2))
                if 21.0 <= plat <= 26.0 and 119.0 <= plng <= 122.5:
                    best = (plat, plng, 'place')
            except ValueError:
                pass

        at_pair = None
        for pat in [r'/@(-?\d+\.\d+),(-?\d+\.\d+)', r'/place/[^/]*/@(-?\d+\.\d+),(-?\d+\.\d+)']:
            m = re.search(pat, url)
            if m:
                at_pair = m
                break
        if at_pair and best is None:
            try:
                alat = float(at_pair.group(1))
                alng = float(at_pair.group(2))
                if 21.0 <= alat <= 26.0 and 119.0 <= alng <= 122.5:
                    best = (alat, alng, '@')
            except ValueError:
                pass

        # Other parameters as last resort
        if best is None:
            for pattern in [
                r'center=(-?\d+\.\d+),(-?\d+\.\d+)',
                r'll=(-?\d+\.\d+),(-?\d+\.\d+)',
                r'q=(-?\d+\.\d+),(-?\d+\.\d+)',
            ]:
                coord_match = re.search(pattern, url)
                if coord_match:
                    try:
                        clat = float(coord_match.group(1))
                        clng = float(coord_match.group(2))
                        if 21.0 <= clat <= 26.0 and 119.0 <= clng <= 122.5:
                            best = (clat, clng, 'param')
                            break
                    except ValueError:
                        continue

        if best:
            lat, lng, source = best
            logger.info(f"Coordinates extracted: ({lat}, {lng}) source: {source}")

        # Extract place name -- multiple patterns
        place_name = None
        place_patterns = [
            r'/place/([^/@]+)',
            r'search/([^/@]+)',
            r'q=([^&@]+)',
            r'query=([^&@]+)',
        ]
        for pattern in place_patterns:
            place_match = re.search(pattern, url)
            if place_match:
                try:
                    raw_name = place_match.group(1)
                    place_name = unquote(raw_name)
                    place_name = place_name.replace('+', ' ').replace('%20', ' ').strip()
                    if len(place_name) > 1 and not place_name.isdigit():
                        logger.info(f"Place name extracted: {place_name}")
                        break
                    else:
                        place_name = None
                except Exception:
                    continue

        # If we have coordinates, return them
        if lat is not None and lng is not None:
            if not place_name:
                try:
                    geolocator = Nominatim(user_agent="lunch-recommendation-system")
                    location = geolocator.reverse(f"{lat}, {lng}", language='zh-TW')
                    if location and location.address:
                        place_name = location.address.split(',')[0]
                        logger.info(f"Reverse geocoded place name: {place_name}")
                except Exception as e:
                    logger.warning(f"Reverse geocoding failed: {e}")
                    place_name = f"\u4f4d\u7f6e ({lat:.4f}, {lng:.4f})"
            return (lat, lng, place_name)

        # If no coordinates but have a place name, try geocoding
        if place_name:
            logger.info(f"URL has no coordinates, trying to geocode: {place_name}")
            coords = geocode_address(place_name)
            if coords:
                lat, lng = coords
                logger.info(f"Geocoding succeeded: {place_name} -> ({lat:.4f}, {lng:.4f})")
                return (lat, lng, place_name)
            else:
                logger.warning(f"Geocoding failed: {place_name}")

        logger.warning("Unable to extract valid location from URL")
        return None

    except Exception as e:
        logger.error(f"URL location extraction failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Taiwan address normalisation
# ---------------------------------------------------------------------------

def normalize_taiwan_address(address: str) -> str:
    """Normalise a Taiwan address string (expand abbreviations, add districts)."""
    if not address:
        return ""

    address = re.sub(r'\s+', '', address)

    address_replacements = {
        '\u5317\u5e02': '\u53f0\u5317\u5e02',   # 北市 -> 台北市
        '\u6843\u5e02': '\u6843\u5712\u5e02',   # 桃市 -> 桃園市
        '\u9ad8\u5e02': '\u9ad8\u96c4\u5e02',   # 高市 -> 高雄市
    }
    for old, new in address_replacements.items():
        if old in address and new not in address:
            address = address.replace(old, new)

    if '\u53f0\u5317\u5e02' in address and '\u5340' not in address and '\u9109' not in address and '\u93ae' not in address:
        district_mapping = {
            '\u4e2d\u5c71': '\u4e2d\u5c71\u5340',
            '\u4fe1\u7fa9': '\u4fe1\u7fa9\u5340',
            '\u5927\u5b89': '\u5927\u5b89\u5340',
            '\u677e\u5c71': '\u677e\u5c71\u5340',
            '\u4e2d\u6b63': '\u4e2d\u6b63\u5340',
            '\u842c\u83ef': '\u842c\u83ef\u5340',
            '\u5927\u540c': '\u5927\u540c\u5340',
            '\u58eb\u6797': '\u58eb\u6797\u5340',
            '\u5317\u6295': '\u5317\u6295\u5340',
            '\u5167\u6e56': '\u5167\u6e56\u5340',
            '\u5357\u6e2f': '\u5357\u6e2f\u5340',
            '\u6587\u5c71': '\u6587\u5c71\u5340',
        }
        for district, full_district in district_mapping.items():
            if district in address and full_district not in address:
                address = address.replace(f'\u53f0\u5317\u5e02{district}', f'\u53f0\u5317\u5e02{full_district}')
                break

    return address


def smart_address_completion(address: str, search_location: Optional[str] = None) -> str:
    """
    Simplified address cleaning -- let Nominatim handle the heavy lifting.
    """
    if not address:
        return address
    return address.strip()


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode_address_with_options(address: str, search_location: Optional[str] = None) -> Dict:
    """
    Geocode with disambiguation: return multiple options if the address is ambiguous.

    :return: {'type': 'single'|'multiple'|'error', ...}
    """
    if not address or len(address.strip()) < 3:
        return {'type': 'error', 'message': '\u5730\u5740\u592a\u77ed'}

    if address.endswith('\u7ad9') and not any(kw in address for kw in ['\u5e02', '\u7e23', '\u8def', '\u8857']):
        options = []
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
        search_variants = [
            (f"\u53f0\u5317\u6377\u904b{address}", "\u53f0\u5317\u6377\u904b\u7ad9"),
            (f"\u6377\u904b{address}", "\u6377\u904b\u7ad9"),
            (address, "\u4e00\u822c\u5730\u9ede"),
        ]
        for query, desc in search_variants:
            try:
                locations = geolocator.geocode(query, exactly_one=False, limit=3)
                if locations:
                    for loc in locations:
                        if 21.0 <= loc.latitude <= 26.0 and 119.0 <= loc.longitude <= 122.5:
                            options.append({
                                'coords': (loc.latitude, loc.longitude),
                                'address': loc.address,
                                'description': desc,
                                'query': query,
                            })
            except Exception:
                continue

        if len(options) > 1:
            unique_options = []
            for option in options:
                is_duplicate = False
                for unique in unique_options:
                    if geodesic(option['coords'], unique['coords']).meters < 100:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_options.append(option)

            if len(unique_options) > 1:
                logger.info(f"Ambiguous place name '{address}', offering {len(unique_options)} options")
                return {'type': 'multiple', 'options': unique_options, 'original_query': address}

    coords = geocode_address(address, search_location)
    if coords:
        return {'type': 'single', 'coords': coords}
    else:
        return {'type': 'error', 'message': f'\u7121\u6cd5\u627e\u5230\u5730\u5740: {address}'}


def geocode_address(address: str, search_location: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """
    Convert an address string to (lat, lng) coordinates using Nominatim.

    Implements a multi-query strategy with scoring to find the best match.
    """
    if not address or len(address.strip()) < 3:
        return None

    completed_address = smart_address_completion(address, search_location)
    logger.info(f"Address completion: {address} -> {completed_address}")

    normalized_address = normalize_taiwan_address(completed_address)
    logger.info(f"Normalised address: {completed_address} -> {normalized_address}")

    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)

        search_queries: list[str] = []

        has_city_or_county = any(city in address for city in ['\u5e02', '\u7e23'])
        district_to_city_map = {
            '\u4e2d\u6b63\u5340': '\u53f0\u5317\u5e02', '\u5927\u540c\u5340': '\u53f0\u5317\u5e02',
            '\u4e2d\u5c71\u5340': '\u53f0\u5317\u5e02', '\u677e\u5c71\u5340': '\u53f0\u5317\u5e02',
            '\u5927\u5b89\u5340': '\u53f0\u5317\u5e02', '\u842c\u83ef\u5340': '\u53f0\u5317\u5e02',
            '\u4fe1\u7fa9\u5340': '\u53f0\u5317\u5e02', '\u58eb\u6797\u5340': '\u53f0\u5317\u5e02',
            '\u5317\u6295\u5340': '\u53f0\u5317\u5e02', '\u5167\u6e56\u5340': '\u53f0\u5317\u5e02',
            '\u5357\u6e2f\u5340': '\u53f0\u5317\u5e02', '\u6587\u5c71\u5340': '\u53f0\u5317\u5e02',
            '\u677f\u6a4b\u5340': '\u65b0\u5317\u5e02', '\u65b0\u838a\u5340': '\u65b0\u5317\u5e02',
            '\u4e2d\u548c\u5340': '\u65b0\u5317\u5e02', '\u6c38\u548c\u5340': '\u65b0\u5317\u5e02',
            '\u4e09\u91cd\u5340': '\u65b0\u5317\u5e02', '\u8606\u6d32\u5340': '\u65b0\u5317\u5e02',
            '\u6c50\u6b62\u5340': '\u65b0\u5317\u5e02', '\u65b0\u5e97\u5340': '\u65b0\u5317\u5e02',
            '\u571f\u57ce\u5340': '\u65b0\u5317\u5e02', '\u9daf\u6b4c\u5340': '\u65b0\u5317\u5e02',
            '\u4e09\u5cfd\u5340': '\u65b0\u5317\u5e02', '\u6cf0\u5c71\u5340': '\u65b0\u5317\u5e02',
            '\u6797\u53e3\u5340': '\u65b0\u5317\u5e02', '\u6de1\u6c34\u5340': '\u65b0\u5317\u5e02',
            '\u4e94\u80a1\u5340': '\u65b0\u5317\u5e02', '\u516b\u91cc\u5340': '\u65b0\u5317\u5e02',
        }
        mapped_city_prefix = None
        if not has_city_or_county:
            for district, city in district_to_city_map.items():
                if district in normalized_address or district in completed_address or district in address:
                    mapped_city_prefix = city
                    break

        if mapped_city_prefix:
            search_queries.extend([
                f"{mapped_city_prefix}{normalized_address}, Taiwan",
                f"{mapped_city_prefix}{normalized_address}",
                f"{mapped_city_prefix}{completed_address}, Taiwan",
                f"{mapped_city_prefix}{completed_address}",
            ])

        search_queries.extend([
            normalized_address + ", Taiwan",
            normalized_address,
            completed_address + ", Taiwan",
            completed_address,
            address + ", Taiwan",
            address,
        ])

        # MRT station handling
        if address.endswith('\u7ad9') and not any(kw in address for kw in ['\u5e02', '\u7e23', '\u8def', '\u8857']):
            mrt_queries = [
                f"\u53f0\u5317\u6377\u904b{address}, Taiwan",
                f"\u6377\u904b{address}, Taiwan",
                f"\u53f0\u5317\u6377\u904b{address}",
                f"\u6377\u904b{address}",
            ]
            search_queries = mrt_queries + search_queries
            logger.debug(f"Detected possible MRT station, added MRT queries: {address}")

        # Address with road name but no city -> prepend Taipei
        if not any(city in address for city in ['\u5e02', '\u7e23']) and any(road in address for road in ['\u8def', '\u8857', '\u5927\u9053']):
            search_queries.insert(0, f"\u53f0\u5317\u5e02{address}, Taiwan")
            search_queries.insert(1, f"\u53f0\u5317\u5e02{address}")

        logger.debug(f"Full query list: {search_queries}")

        best_result = None
        best_query_score = 0
        best_query = ""

        for i, query in enumerate(search_queries):
            try:
                logger.debug(f"Trying query: {query}")
                location = geolocator.geocode(query, limit=1)
                if location and location.latitude and location.longitude:
                    if 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                        query_score = 100 - i
                        if '\u5df7' in query and '\u865f' in query:
                            query_score += 50
                        elif '\u5df7' in query or '\u865f' in query:
                            query_score += 25
                        elif '\u6bb5' in query:
                            query_score += 10

                        if best_result is None or query_score > best_query_score:
                            best_result = (location.latitude, location.longitude)
                            best_query_score = query_score
                            best_query = query

                        if '\u5df7' in query and '\u865f' in query:
                            logger.info(f"Found full-address result: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                            return (location.latitude, location.longitude)

            except Exception as e:
                logger.debug(f"Query failed: {query} - {e}")
                continue

        if best_result:
            logger.info(f"Geocoding succeeded: {best_query} -> ({best_result[0]:.4f}, {best_result[1]:.4f})")
            return best_result

        # Fallback: progressively simplify the address
        if '\u5df7' in address or '\u865f' in address:
            logger.warning(f"Full address query failed, trying Taiwan address simplification: {address}")
            fallback_strategies: list[str] = []

            if '\u865f' in address:
                addr_without_number = re.sub(r'\d+\u865f.*$', '', address)
                if addr_without_number != address:
                    fallback_strategies.extend([f"{addr_without_number}, Taiwan", addr_without_number])

            if '\u5f04' in address:
                addr_without_alley = re.sub(r'\d+\u5f04.*$', '', address)
                if addr_without_alley != address:
                    fallback_strategies.extend([f"{addr_without_alley}, Taiwan", addr_without_alley])

            if '\u5df7' in address:
                addr_to_lane = re.sub(r'(\d+\u5df7).*$', r'\1', address)
                if addr_to_lane != address:
                    fallback_strategies.extend([f"{addr_to_lane}, Taiwan", addr_to_lane])

            road_match = re.search(
                r'([^\u5e02\u7e23\u5340\u9109\u93ae]*[\u8def\u8857\u5927\u9053](?:\u4e00|\u4e8c|\u4e09|\u56db|\u4e94|\u516d|\u4e03|\u516b|\u4e5d|\d+)*\u6bb5?)',
                address,
            )
            if road_match:
                main_road = road_match.group(1).strip()
                fallback_strategies.extend([
                    f"\u53f0\u5317\u5e02{main_road}, Taiwan",
                    f"{main_road}, Taiwan",
                    main_road,
                ])

            for i, query in enumerate(fallback_strategies):
                try:
                    logger.debug(f"Taiwan address simplification attempt {i + 1}: {query}")
                    location = geolocator.geocode(query, limit=1)
                    if location and 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                        if '\u5df7' in query:
                            logger.info(f"Lane-level simplification succeeded: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                        elif '\u6bb5' in query:
                            logger.warning(f"[WARNING] Section-level simplification succeeded: {query}")
                        else:
                            logger.warning(f"[WARNING] Road-level simplification succeeded: {query}")
                        return (location.latitude, location.longitude)
                except Exception:
                    continue

    except Exception as e:
        logger.error(f"Geocoding service error: {e}")

    logger.warning(f"Address resolution failed: {address}")
    return None


# ---------------------------------------------------------------------------
# Address validation / scoring helpers
# ---------------------------------------------------------------------------

def validate_and_select_best_address(addresses: List[str]) -> Optional[str]:
    """Score candidate addresses and return the best one."""
    if not addresses:
        return None

    def score_address(addr: str) -> int:
        score = 0
        addr = addr.strip()

        if 12 <= len(addr) <= 60:
            score += 15
        elif 8 <= len(addr) <= 80:
            score += 8

        has_city = any(kw in addr for kw in ['\u5e02', '\u7e23'])
        has_district = any(kw in addr for kw in ['\u5340', '\u9109', '\u93ae'])
        has_road = any(kw in addr for kw in ['\u8def', '\u8857', '\u5927\u9053', '\u5df7', '\u5f04'])
        has_number = bool(re.search(r'\d+\u865f', addr))
        has_postal = bool(re.match(r'^\d{3}', addr))

        if has_city:
            score += 20
        if has_district:
            score += 20
        if has_road:
            score += 15
        if has_number:
            score += 12
        if has_postal:
            score += 8

        if '\u6bb5' in addr:
            score += 5
        if '\u5df7' in addr:
            score += 4
        if '\u5f04' in addr:
            score += 3
        if '\u6a13' in addr:
            score += 2

        completeness_count = sum([has_city, has_district, has_road, has_number])
        if completeness_count >= 4:
            score += 25
        elif completeness_count >= 3:
            score += 15
        elif completeness_count >= 2:
            score += 5

        if re.search(r'[a-zA-Z]{5,}', addr):
            score -= 15
        if len(addr) < 6:
            score -= 20
        if '\u96fb\u8a71' in addr or '\u8a55\u5206' in addr or '\u71df\u696d\u6642\u9593' in addr:
            score -= 25
        if '\u516c\u91cc' in addr or '\u5206\u9418' in addr or '\u5c0f\u6642' in addr:
            score -= 20

        return score

    scored_addresses = [(addr, score_address(addr)) for addr in addresses]
    scored_addresses.sort(key=lambda x: x[1], reverse=True)

    logger.debug("Address candidate scores:")
    for addr, score in scored_addresses[:5]:
        logger.debug(f"  {addr[:30]}... -> score: {score}")

    if scored_addresses and scored_addresses[0][1] > 10:
        best_address = scored_addresses[0][0].strip()
        logger.info(f"Selected best address: {best_address} (score: {scored_addresses[0][1]})")
        return best_address

    return None


def is_valid_taiwan_address(address: str) -> bool:
    """Check whether *address* looks like a valid Taiwan address."""
    if not address or len(address.strip()) < 3:
        return False

    address = address.strip()

    has_city = any(kw in address for kw in ['\u5e02', '\u7e23'])
    has_district = any(kw in address for kw in ['\u5340', '\u9109', '\u93ae'])
    has_road = any(kw in address for kw in ['\u8def', '\u8857', '\u5927\u9053', '\u5df7', '\u5f04'])

    if has_city and (has_district or has_road):
        return True
    if has_district and has_road:
        return True
    if re.match(r'^\d{3}', address) and (has_city or has_district or has_road):
        return True

    exclude_keywords = ['\u96fb\u8a71', '\u8a55\u5206', '\u71df\u696d\u6642\u9593', '\u516c\u91cc', '\u5206\u9418', '\u661f\u671f', '\u5c0f\u6642', '\u7db2\u7ad9', 'http']
    if any(kw in address for kw in exclude_keywords):
        return False

    return False


def clean_address(address: str) -> str:
    """Strip common prefixes/suffixes from a raw address string."""
    if not address:
        return ""

    address = address.strip()

    prefixes_to_remove = ['\u5730\u5740:', '\u5730\u5740\uff1a', '\u4f4d\u65bc:', '\u4f4d\u65bc\uff1a', '\u5730\u9ede:', '\u5730\u9ede\uff1a']
    for prefix in prefixes_to_remove:
        if address.startswith(prefix):
            address = address[len(prefix):].strip()

    suffixes_to_remove = ['(', '\uff08', '\u00b7', '\u2022', '\u96fb\u8a71', '\u8a55\u5206', '\u71df\u696d\u6642\u9593']
    for suffix in suffixes_to_remove:
        if suffix in address:
            address = address.split(suffix)[0].strip()

    address = re.sub(r'\s+', ' ', address)
    return address


def is_complete_address(address: str) -> bool:
    """Check whether *address* has enough components to be considered complete."""
    if not address or len(address.strip()) < 6:
        return False

    address = address.strip()

    has_city = any(kw in address for kw in ['\u5e02', '\u7e23'])
    has_district = any(kw in address for kw in ['\u5340', '\u9109', '\u93ae'])
    has_road = any(kw in address for kw in ['\u8def', '\u8857', '\u5927\u9053', '\u5df7', '\u5f04'])
    has_number = bool(re.search(r'\d+\u865f', address))

    completeness_score = sum([has_city, has_district, has_road, has_number])

    has_postal = bool(re.match(r'^\d{3}', address))
    if has_postal:
        return completeness_score >= 3

    if has_road and has_number:
        return True
    if has_city and has_district and has_road:
        return True

    return completeness_score >= 4


# ---------------------------------------------------------------------------
# Extract address from a Maps detail page (Selenium)
# ---------------------------------------------------------------------------

def extract_address_from_maps_url(maps_url: str) -> Optional[str]:
    """
    Open a Google Maps page with Selenium and try to scrape the address.
    """
    try:
        if 'goo.gl' in maps_url or len(maps_url) < 50:
            maps_url = expand_short_url(maps_url)

        # Check URL place segment first
        place_match = re.search(r'/place/([^/@]+)', maps_url)
        if place_match:
            encoded_place = place_match.group(1)
            decoded_place = unquote(encoded_place).replace('+', ' ')
            if is_valid_taiwan_address(decoded_place):
                cleaned = clean_address(decoded_place)
                if is_complete_address(cleaned):
                    return cleaned

        # Fallback: use Selenium
        try:
            from modules.scraper.browser_pool import create_chrome_driver
            driver = create_chrome_driver(headless=True)
            driver.get(maps_url)
            time.sleep(1.2)

            for selector in MAPS_PAGE_ADDRESS_SELECTORS:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        text = elem.text.strip()
                        if is_valid_taiwan_address(text) and is_complete_address(text):
                            driver.quit()
                            return clean_address(text)
                except Exception:
                    continue

            driver.quit()
        except Exception as e:
            logger.debug(f"Selenium address extraction failed: {e}")

        return None
    except Exception as e:
        logger.error(f"extract_address_from_maps_url failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Parse a Google Maps URL into a restaurant info dict
# ---------------------------------------------------------------------------

def parse_google_maps_url(url: str) -> Optional[Dict[str, Any]]:
    """Parse a Google Maps URL and return basic restaurant info."""
    try:
        if 'maps.app.goo.gl' in url or 'goo.gl' in url:
            session = create_session()
            response = session.get(url, allow_redirects=True, timeout=10)
            url = response.url

        restaurant_info: Dict[str, Any] = {
            'name': None,
            'address': None,
            'maps_url': url,
            'latitude': None,
            'longitude': None,
            'rating': None,
            'price_level': None,
        }

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        if '/place/' in url:
            match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
            if match:
                restaurant_info['latitude'] = float(match.group(1))
                restaurant_info['longitude'] = float(match.group(2))

            place_match = re.search(r'/place/([^/@]+)', url)
            if place_match:
                restaurant_info['name'] = unquote(place_match.group(1)).replace('+', ' ')

        if 'q' in query_params:
            restaurant_info['name'] = query_params['q'][0]

        return restaurant_info
    except Exception as e:
        print(f"[URL parse] failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Reliable Maps URL generation / validation
# ---------------------------------------------------------------------------

def generate_fallback_maps_url(restaurant_name: str, address: str = "") -> str:
    """Generate a fallback Google Maps search URL."""
    try:
        encoded_name = quote(restaurant_name)
        if address:
            clean_addr = address.split(',')[0].strip() if ',' in address else address.strip()
            encoded_address = quote(clean_addr)
            return f"https://www.google.com/maps/search/{encoded_name}+{encoded_address}"
        else:
            return f"https://www.google.com/maps/search/{encoded_name}"
    except Exception as e:
        logger.warning(f"generate_fallback_maps_url failed: {e}")
        return f"https://www.google.com/maps/search/{restaurant_name}"


def validate_maps_url(url: str) -> bool:
    """Check whether a Google Maps URL is reachable."""
    if not url:
        return False
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            url,
            headers={'User-Agent': random.choice(USER_AGENTS)},
            timeout=10,
            verify=False,
            allow_redirects=True,
        )
        return response.status_code == 200
    except Exception:
        return False


def get_reliable_maps_url(restaurant_info: dict) -> str:
    """
    Return the most reliable Google Maps URL for a restaurant.
    Priority: original place URL > name+address search > name search.
    """
    name = restaurant_info.get('name', '')
    address = restaurant_info.get('address', '').split(',')[0] if restaurant_info.get('address') else ''
    original_url = restaurant_info.get('maps_url', '')

    if original_url and '/maps/place/' in original_url and '!' in original_url:
        return original_url

    if name and address:
        return generate_fallback_maps_url(name, address)

    if name:
        return generate_fallback_maps_url(name)

    return original_url or "https://www.google.com/maps"


# ---------------------------------------------------------------------------
# Location candidates (disambiguation UI)
# ---------------------------------------------------------------------------

def get_location_candidates(address: str, max_candidates: int = 3) -> List[Dict[str, Any]]:
    """
    Return a list of candidate locations for an ambiguous address.
    """
    if not address or len(address.strip()) < 2:
        return []

    candidates: List[Dict[str, Any]] = []

    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)

        search_queries: list[str] = []
        search_queries.extend([
            address + ", Taiwan",
            address + ", \u53f0\u7063",
            address,
        ])

        if address.endswith('\u7ad9') and not any(kw in address for kw in ['\u5e02', '\u7e23', '\u8def', '\u8857']):
            search_queries.extend([
                f"\u53f0\u5317\u6377\u904b{address}, Taiwan",
                f"\u6377\u904b{address}, Taiwan",
                f"\u53f0\u5317\u6377\u904b{address}",
                f"\u6377\u904b{address}",
            ])

        if not any(city in address for city in ['\u5e02', '\u7e23']) and any(road in address for road in ['\u8def', '\u8857', '\u5927\u9053']):
            search_queries.extend([
                f"\u53f0\u5317\u5e02{address}, Taiwan",
                f"\u53f0\u5317\u5e02{address}",
            ])

        seen_locations: set = set()

        for query in search_queries:
            try:
                locations = geolocator.geocode(query, limit=5, exactly_one=False)
                if locations:
                    for location in locations:
                        if location and location.latitude and location.longitude:
                            if 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                                location_key = f"{location.latitude:.4f},{location.longitude:.4f}"
                                if location_key not in seen_locations:
                                    seen_locations.add(location_key)

                                    address_parts = location.address.split(', ')
                                    display_name = address_parts[0] if address_parts else location.address

                                    district = ""
                                    city = ""
                                    for part in address_parts:
                                        if any(suffix in part for suffix in ['\u5340', '\u9109', '\u93ae']):
                                            district = part
                                        elif any(suffix in part for suffix in ['\u5e02', '\u7e23']):
                                            city = part

                                    candidate = {
                                        'name': display_name,
                                        'full_address': location.address,
                                        'coordinates': [location.latitude, location.longitude],
                                        'district': district,
                                        'city': city,
                                        'query_used': query,
                                    }
                                    candidates.append(candidate)

                                    if len(candidates) >= max_candidates:
                                        break

                        if len(candidates) >= max_candidates:
                            break

            except Exception as e:
                logger.debug(f"Candidate query failed: {query} - {e}")
                continue

            if len(candidates) >= max_candidates:
                break

    except Exception as e:
        logger.error(f"get_location_candidates error: {e}")

    logger.info(f"Found {len(candidates)} candidate(s) for address '{address}'")
    return candidates
