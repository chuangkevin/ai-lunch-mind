"""
Distance calculation utilities.

Contains:
- calculate_distance() -- haversine (geodesic) straight-line distance
- estimate_distance_by_address() -- heuristic based on Taiwan address components
- calculate_walking_distance_from_google_maps() -- Selenium-based walking route
- calculate_walking_distances_parallel() -- parallel walking distance for many restaurants
"""

from typing import List, Dict, Optional, Any, Tuple
import re
import time
import logging
import urllib.parse
import concurrent.futures

from geopy.distance import geodesic
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# Lazy imports to avoid circular dependency with scraper modules
# from modules.scraper.browser_pool import create_chrome_driver  # imported in functions
# from modules.scraper.selectors import WALKING_TAB_SELECTORS  # imported in functions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Straight-line (geodesic) distance
# ---------------------------------------------------------------------------

def calculate_distance(user_coords: Tuple[float, float], restaurant_coords: Tuple[float, float]) -> Optional[float]:
    """
    Calculate the straight-line distance between two coordinates (km).

    :param user_coords: (lat, lon)
    :param restaurant_coords: (lat, lon)
    :return: distance in km (rounded to 2 dp), or None on error
    """
    try:
        distance = geodesic(user_coords, restaurant_coords).kilometers
        return round(distance, 2)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Address-based heuristic distance
# ---------------------------------------------------------------------------

def estimate_distance_by_address(user_address: str, restaurant_address: str) -> float:
    """
    Estimate distance based on Taiwan address component differences.
    Used as a fallback when GPS coordinates are identical / unavailable.
    """
    try:
        user_clean = user_address.replace('\u53f0\u5317\u5e02', '').replace('\u677e\u5c71\u5340', '').strip()
        restaurant_clean = restaurant_address.replace('\u53f0\u5317\u5e02', '').replace('\u677e\u5c71\u5340', '').strip()

        def extract_address_components(addr):
            components = {}
            road_match = re.search(
                r'([^\u5e02\u7e23\u5340\u9109\u93ae]*[\u8def\u8857\u5927\u9053](?:\u4e00|\u4e8c|\u4e09|\u56db|\u4e94|\u516d|\u4e03|\u516b|\u4e5d|\d+)*\u6bb5?)',
                addr,
            )
            components['road'] = road_match.group(1) if road_match else ''

            lane_match = re.search(r'(\d+)\u5df7', addr)
            components['lane'] = int(lane_match.group(1)) if lane_match else 0

            alley_match = re.search(r'(\d+)\u5f04', addr)
            components['alley'] = int(alley_match.group(1)) if alley_match else 0

            number_match = re.search(r'(\d+)\u865f', addr)
            components['number'] = int(number_match.group(1)) if number_match else 0

            return components

        user_comp = extract_address_components(user_clean)
        restaurant_comp = extract_address_components(restaurant_clean)

        if user_comp['road'] != restaurant_comp['road']:
            return 1.0  # different road -> ~1 km estimate

        distance = 0.0

        lane_diff = abs(user_comp['lane'] - restaurant_comp['lane'])
        if lane_diff > 0:
            distance += lane_diff * 0.15  # ~150 m per lane

        alley_diff = abs(user_comp['alley'] - restaurant_comp['alley'])
        if alley_diff > 0:
            distance += alley_diff * 0.08  # ~80 m per alley

        number_diff = abs(user_comp['number'] - restaurant_comp['number'])
        if number_diff > 0:
            distance += (number_diff / 10) * 0.05  # ~50 m per 10 numbers

        if distance == 0:
            distance = 0.05  # same lane/alley -> minimum 50 m

        return round(distance, 2)

    except Exception as e:
        logger.debug(f"Address distance estimation failed: {e}")
        return 0.1  # default 100 m


# ---------------------------------------------------------------------------
# Google Maps walking distance (Selenium)
# ---------------------------------------------------------------------------

def calculate_walking_distance_from_google_maps(
    user_address: str,
    restaurant_address: str,
) -> Tuple[Optional[float], Optional[int], str]:
    """
    Obtain actual walking distance & time from Google Maps directions page.

    Uses a standard (JS-enabled) Chrome driver, forces walking mode (travelmode=walking),
    and parses distance/time from the rendered page text.

    :return: (distance_km, walking_minutes, route_url)
             distance and minutes may be None if parsing fails; URL is always returned.
    """

    def build_route_url(origin_text: str, dest_text: str) -> str:
        origin = origin_text.strip()
        if re.match(r"^\s*-?\d{1,3}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?\s*$", origin):
            origin_param = origin.replace(' ', '')
        else:
            origin_param = urllib.parse.quote(origin)

        dest_clean = dest_text.strip()
        if re.match(r"^\s*-?\d{1,3}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?\s*$", dest_clean):
            dest_param = dest_clean.replace(' ', '')
        else:
            dest_param = urllib.parse.quote(dest_clean)

        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={origin_param}"
            f"&destination={dest_param}"
            "&travelmode=walking&hl=zh-TW"
        )

    route_url = build_route_url(str(user_address), str(restaurant_address))
    driver = None
    try:
        from modules.scraper.browser_pool import create_chrome_driver
        driver = create_chrome_driver(headless=True)
        driver.get(route_url)
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(0.8)

        # Try to click the walking tab
        try:
            from selenium.webdriver.support import expected_conditions as EC
            from modules.scraper.selectors import WALKING_TAB_SELECTORS
            for sel in WALKING_TAB_SELECTORS:
                try:
                    el = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    if el and el.is_displayed():
                        el.click()
                        time.sleep(0.8)
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # Get page text
        try:
            page_text = driver.find_element(By.TAG_NAME, 'body').text
        except Exception:
            page_text = driver.page_source or ""

        # Parse distance + time from same line first
        candidates: list[tuple[int, float]] = []
        for line in page_text.splitlines():
            line = line.strip()
            if not line:
                continue
            m_km = re.search(r"(\d+)\s*\u5206[^\n]*?(\d+(?:\.\d+)?)\s*\u516c\u91cc", line)
            if m_km:
                minutes = int(m_km.group(1))
                dist_km = float(m_km.group(2))
                candidates.append((minutes, dist_km))
                continue
            m_m = re.search(r"(\d+)\s*\u5206[^\n]*?(\d+)\s*(?:\u516c\u5c3a|m)\b", line)
            if m_m:
                minutes = int(m_m.group(1))
                dist_km = int(m_m.group(2)) / 1000.0
                candidates.append((minutes, dist_km))

        distance_km: Optional[float] = None
        walking_minutes: Optional[int] = None

        if candidates:
            candidates.sort(key=lambda x: (x[1], x[0]))
            walking_minutes, distance_km = candidates[0][0], candidates[0][1]
        else:
            # Fallback: scan entire page
            m_only = re.search(r"(\d+)\s*\u5206", page_text)
            km_vals = [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*\u516c\u91cc", page_text)]
            if km_vals:
                distance_km = min(km_vals)
            else:
                m_vals = [int(m) for m in re.findall(r"(\d+)\s*(?:\u516c\u5c3a|m)\b", page_text)]
                if m_vals:
                    m_vals_sorted = sorted(m_vals)
                    if len(m_vals_sorted) >= 4:
                        idx = int(len(m_vals_sorted) * 0.75)
                        idx = min(idx, len(m_vals_sorted) - 1)
                        distance_km = m_vals_sorted[idx] / 1000.0
                    else:
                        distance_km = max(m_vals_sorted) / 1000.0
            if m_only:
                walking_minutes = int(m_only.group(1))

        # Support hour format
        if walking_minutes is None:
            hm = re.search(r"(\d+)\s*\u5c0f\u6642.*?(\d+)\s*\u5206", page_text)
            if hm:
                walking_minutes = int(hm.group(1)) * 60 + int(hm.group(2))
            else:
                h_only = re.search(r"(\d+)\s*\u5c0f\u6642", page_text)
                m_only2 = re.search(r"(\d+)\s*\u5206", page_text)
                if h_only and m_only2:
                    walking_minutes = int(h_only.group(1)) * 60 + int(m_only2.group(1))
                elif m_only2:
                    walking_minutes = int(m_only2.group(1))

        return (round(distance_km, 3) if distance_km is not None else None, walking_minutes, route_url)

    except Exception as e:
        logger.error(f"Walking distance retrieval failed: {e}")
        return None, None, route_url
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Parallel walking distance calculation
# ---------------------------------------------------------------------------

def calculate_walking_distances_parallel(
    user_address: str,
    restaurants: List[Dict[str, Any]],
    max_workers: int = 6,
) -> None:
    """
    Calculate walking distances for multiple restaurants in parallel.

    Modifies each restaurant dict in-place (adds distance_km, walking_minutes, etc.).
    """
    # Import geocode_address lazily to avoid circular import at module level
    from modules.geo.geocoding import geocode_address

    logger.info(f"[PARALLEL] Starting parallel distance calculation for {len(restaurants)} restaurants")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_restaurant = {}
        for restaurant in restaurants:
            if restaurant.get('address'):
                restaurant_address = restaurant['address']
                dest_for_routing = restaurant_address

                try:
                    incomplete = (
                        not any(city in restaurant_address for city in ['\u5e02', '\u7e23'])
                    ) or (
                        not any(k in restaurant_address for k in ['\u865f', '\u5df7', '\u8857', '\u8def'])
                    )
                    if incomplete:
                        try:
                            coords = geocode_address(restaurant_address, user_address)
                            if coords:
                                dest_for_routing = f"{coords[0]},{coords[1]}"
                        except Exception:
                            pass
                except Exception:
                    pass

                future = executor.submit(
                    calculate_walking_distance_from_google_maps,
                    user_address,
                    dest_for_routing,
                )
                future_to_restaurant[future] = restaurant

        completed = 0
        for future in concurrent.futures.as_completed(future_to_restaurant):
            restaurant = future_to_restaurant[future]
            completed += 1
            try:
                walking_distance, walking_mins, google_maps_url = future.result()

                if google_maps_url:
                    restaurant['google_maps_url'] = google_maps_url

                if walking_distance is not None:
                    restaurant['distance_km'] = walking_distance
                    restaurant['walking_minutes'] = walking_mins
                    restaurant['distance'] = f"{walking_distance:.2f}km"
                    logger.info(
                        f"[SUCCESS] [{completed}/{len(restaurants)}] "
                        f"{restaurant.get('name', 'unknown')}: {walking_distance:.2f}km, {walking_mins}min"
                    )
                else:
                    logger.warning(
                        f"[FAIL] [{completed}/{len(restaurants)}] "
                        f"{restaurant.get('name', 'unknown')}: distance calculation failed"
                    )
            except Exception as e:
                logger.warning(
                    f"[ERROR] [{completed}/{len(restaurants)}] "
                    f"{restaurant.get('name', 'unknown')}: distance calculation error - {e}"
                )

    elapsed = time.time() - start_time
    logger.info(
        f"[COMPLETE] Parallel distance calculation done! "
        f"Total {elapsed:.1f}s (avg {elapsed / max(len(restaurants), 1):.1f}s/restaurant)"
    )
