# modules/recommendation_engine.py
"""
Main orchestration engine for the AI lunch recommendation system.

Coordinates the full recommendation pipeline:
  Phase 1: Intent analysis (weather + user input -> structured intent)
  Phase 2: Triple-track parallel search (Google Maps + Google Search + PTT)
  Phase 3: Merge, score, rank, and return top results
"""

import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from modules.ai.intent_analyzer import analyze_intent
from modules.ai.restaurant_scorer import score_restaurants, _parse_price_avg
from modules.geo.distance import calculate_walking_distances_parallel
from modules.scraper.google_maps import search_restaurants
from modules.scraper.google_search import search_google_recommendations
from modules.scraper.ptt_scraper import search_ptt_recommendations
from modules.sweat_index import query_sweat_index_by_location

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEARCH_TIMEOUT_SECONDS = 3
MAX_SEARCH_WORKERS = 6

# Sweat index -> max search distance (km)
_SWEAT_DISTANCE_MAP = [
    (8, 0.5),   # sweat_index >= 8 -> 500m
    (6, 1.0),   # sweat_index >= 6 -> 1km
    (4, 2.0),   # sweat_index >= 4 -> 2km
    (0, 3.0),   # sweat_index < 4  -> 3km
]

# Budget overshoot tolerance: restaurants priced more than this factor above
# the user's stated max budget are filtered out.
_BUDGET_OVERSHOOT_FACTOR = 1.5


# ---------------------------------------------------------------------------
# Fuzzy name matching utilities
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize a restaurant name for fuzzy comparison.

    Strips whitespace, punctuation, and Unicode category marks so that
    names like "麵屋 武藏" and "麵屋武藏" match correctly.
    """
    if not name:
        return ""
    # Collapse whitespace
    text = re.sub(r"\s+", "", name.strip())
    # Remove common punctuation and symbols
    text = re.sub(r"[·・．。，、！？\-—–()（）【】\[\]「」『』\"'`~～]", "", text)
    # Remove Unicode punctuation category characters
    text = "".join(
        ch for ch in text
        if not unicodedata.category(ch).startswith("P")
        and not unicodedata.category(ch).startswith("S")
    )
    return text.lower()


def _names_match(name_a: str, name_b: str) -> bool:
    """Return True if two restaurant names are considered the same."""
    norm_a = _normalize_name(name_a)
    norm_b = _normalize_name(name_b)
    if not norm_a or not norm_b:
        return False
    # Exact match after normalization
    if norm_a == norm_b:
        return True
    # One contains the other (handles "麵屋武藏 台北101店" vs "麵屋武藏")
    # Require minimum length of 2 characters to avoid false positives with
    # very short CJK names (e.g. single-character "麵" matching everything).
    if len(norm_a) >= 2 and len(norm_b) >= 2:
        if norm_a in norm_b or norm_b in norm_a:
            return True
    return False


# ---------------------------------------------------------------------------
# Distance budget from sweat index
# ---------------------------------------------------------------------------

def _max_distance_from_sweat_index(sweat_index: Optional[float]) -> float:
    """Determine the maximum search distance (km) based on sweat index."""
    if sweat_index is None:
        return 2.0  # sensible default
    for threshold, distance in _SWEAT_DISTANCE_MAP:
        if sweat_index >= threshold:
            return distance
    return 3.0


# ---------------------------------------------------------------------------
# Weather data extraction
# ---------------------------------------------------------------------------

def _extract_weather_data(sweat_result: Dict) -> Tuple[Dict, float]:
    """Extract a lightweight weather_data dict and sweat_index from the
    full sweat index query result.

    Returns:
        (weather_data dict suitable for intent_analyzer, sweat_index float)
    """
    weather_source = sweat_result.get("weather_source", {})
    sweat_index = sweat_result.get("sweat_index")

    weather_data = {
        "temperature": sweat_result.get("temperature"),
        "humidity": sweat_result.get("humidity"),
        "sweat_index": sweat_index,
    }

    # Rain probability can be nested in weather_source or rain_info
    rain_info = sweat_result.get("rain_info", {})
    rain_prob = rain_info.get("probability")
    if rain_prob is None:
        rain_prob = weather_source.get("rain_probability")
    # Attempt numeric conversion
    if rain_prob is not None and rain_prob != "N/A":
        try:
            rain_prob_str = str(rain_prob).replace("%", "").strip()
            weather_data["rain_probability"] = float(rain_prob_str)
        except (ValueError, TypeError):
            pass

    return weather_data, sweat_index if sweat_index is not None else 5.0


# ---------------------------------------------------------------------------
# Phase 2: Search tracks
# ---------------------------------------------------------------------------

def _run_google_maps_track(
    keywords: List[str],
    location: str,
    max_results_per_keyword: int,
) -> List[Dict]:
    """Track A: Search Google Maps for each keyword."""
    all_results: List[Dict] = []
    seen_names: set = set()

    for keyword in keywords:
        try:
            results = search_restaurants(
                keyword=keyword,
                user_address=location,
                max_results=max_results_per_keyword,
            )
            for r in results:
                name = r.get("name", "")
                norm = _normalize_name(name)
                if norm and norm not in seen_names:
                    seen_names.add(norm)
                    r.setdefault("search_keyword", keyword)
                    r.setdefault("source", "google_maps")
                    all_results.append(r)
        except Exception as exc:
            logger.warning("[Track-A] Google Maps search failed for '%s': %s", keyword, exc)

    return all_results


def _run_google_search_track(
    keywords: List[str],
    location: str,
) -> List[Dict]:
    """Track B: Google Search scraper for social mentions."""
    all_mentions: List[Dict] = []
    seen_names: set = set()

    for keyword in keywords:
        try:
            result = search_google_recommendations(
                keyword=keyword,
                location=location,
            )
            for mention in result.get("restaurants_mentioned", []):
                name = mention.get("name", "")
                norm = _normalize_name(name)
                if norm and norm not in seen_names:
                    seen_names.add(norm)
                    all_mentions.append(mention)
        except Exception as exc:
            logger.warning("[Track-B] Google Search scraper failed for '%s': %s", keyword, exc)

    return all_mentions


def _run_ptt_track(
    keywords: List[str],
    location: str,
) -> List[Dict]:
    """Track C: PTT scraper for social mentions."""
    all_mentions: List[Dict] = []
    seen_names: set = set()

    for keyword in keywords:
        try:
            result = search_ptt_recommendations(
                keyword=keyword,
                location=location,
            )
            for mention in result.get("restaurants_mentioned", []):
                name = mention.get("name", "")
                norm = _normalize_name(name)
                if norm and norm not in seen_names:
                    seen_names.add(norm)
                    all_mentions.append(mention)
        except Exception as exc:
            logger.warning("[Track-C] PTT scraper failed for '%s': %s", keyword, exc)

    return all_mentions


# ---------------------------------------------------------------------------
# Phase 3: Merge social proof into Maps results
# ---------------------------------------------------------------------------

def _merge_social_proof(
    maps_results: List[Dict],
    google_search_mentions: List[Dict],
    ptt_mentions: List[Dict],
    location: str,
) -> List[Dict]:
    """Merge social source data into Google Maps base results.

    1. Match social names against Maps results by fuzzy name comparison.
       Matched restaurants get a social_proof dict.
    2. Unmatched social names are looked up on Google Maps for coordinates.
    3. Still unmatched are kept with a "social recommendation, no Maps data" label.

    Returns the merged restaurant list (maps results first, then new entries).
    """
    # Build lookup for fast matching
    maps_norm_index: Dict[str, int] = {}
    for i, r in enumerate(maps_results):
        norm = _normalize_name(r.get("name", ""))
        if norm:
            maps_norm_index[norm] = i

    # Initialize social_proof on all maps results
    for r in maps_results:
        if "social_proof" not in r:
            r["social_proof"] = {}

    unmatched_social: List[Dict] = []

    # --- Google Search mentions ---
    for mention in google_search_mentions:
        name = mention.get("name", "")
        matched_idx = _find_match(name, maps_norm_index, maps_results)
        if matched_idx is not None:
            sp = maps_results[matched_idx].setdefault("social_proof", {})
            sp["google_search_mentions"] = sp.get("google_search_mentions", 0) + 1
            sp.setdefault("google_search_snippets", []).append(
                mention.get("snippet", "")
            )
        else:
            unmatched_social.append({
                "name": name,
                "source_type": "google_search",
                "snippet": mention.get("snippet", ""),
            })

    # --- PTT mentions ---
    for mention in ptt_mentions:
        name = mention.get("name", "")
        matched_idx = _find_match(name, maps_norm_index, maps_results)
        if matched_idx is not None:
            sp = maps_results[matched_idx].setdefault("social_proof", {})
            sp["ptt_title_mentions"] = sp.get("ptt_title_mentions", 0) + 1
            if mention.get("ptt_high_upvotes"):
                sp["ptt_high_upvotes"] = True
            sp.setdefault("ptt_titles", []).append(mention.get("ptt_title", ""))
        else:
            unmatched_social.append({
                "name": name,
                "source_type": "ptt",
                "ptt_title": mention.get("ptt_title", ""),
                "ptt_upvotes": mention.get("ptt_upvotes", 0),
                "ptt_high_upvotes": mention.get("ptt_high_upvotes", False),
            })

    # --- Attempt Maps lookup for unmatched social restaurants ---
    # Cap at 3 lookups to avoid excessive latency, and respect a time deadline.
    MAX_SOCIAL_LOOKUPS = 3
    _merge_deadline = time.time() + 3.0  # hard deadline for this phase

    new_entries: List[Dict] = []
    seen_unmatched: set = set()
    lookup_count = 0

    for item in unmatched_social:
        name = item["name"]
        norm = _normalize_name(name)
        if norm in seen_unmatched:
            continue
        seen_unmatched.add(norm)

        # Skip Maps lookups if we've hit the cap or remaining time < 1 second
        if lookup_count >= MAX_SOCIAL_LOOKUPS or (time.time() > _merge_deadline - 1.0):
            # Keep as social-only without Maps lookup
            entry = {
                "name": name,
                "source": "social_only",
                "address": "",
                "rating": None,
                "review_count": None,
                "social_proof": _build_social_proof_from_item(item),
                "social_label": "社群推薦，無Maps資料",
            }
            new_entries.append(entry)
            continue

        # Try a quick Maps search for coordinates
        lookup_count += 1
        try:
            lookup_results = search_restaurants(
                keyword=name,
                user_address=location,
                max_results=1,
            )
            if lookup_results:
                entry = lookup_results[0]
                entry["source"] = "social_lookup"
                # Build social proof from the unmatched item
                sp = {}
                if item["source_type"] == "google_search":
                    sp["google_search_mentions"] = 1
                elif item["source_type"] == "ptt":
                    sp["ptt_title_mentions"] = 1
                    if item.get("ptt_high_upvotes"):
                        sp["ptt_high_upvotes"] = True
                entry["social_proof"] = sp
                new_entries.append(entry)
            else:
                # Keep as social-only recommendation
                entry = {
                    "name": name,
                    "source": "social_only",
                    "address": "",
                    "rating": None,
                    "review_count": None,
                    "social_proof": _build_social_proof_from_item(item),
                    "social_label": "社群推薦，無Maps資料",
                }
                new_entries.append(entry)
        except Exception as exc:
            logger.debug("[Merge] Maps lookup failed for '%s': %s", name, exc)
            entry = {
                "name": name,
                "source": "social_only",
                "address": "",
                "rating": None,
                "review_count": None,
                "social_proof": _build_social_proof_from_item(item),
                "social_label": "社群推薦，無Maps資料",
            }
            new_entries.append(entry)

    return maps_results + new_entries


def _find_match(
    name: str,
    norm_index: Dict[str, int],
    restaurants: List[Dict],
) -> Optional[int]:
    """Find the index of a matching restaurant by normalized name."""
    norm = _normalize_name(name)
    if not norm:
        return None

    # Direct lookup
    if norm in norm_index:
        return norm_index[norm]

    # Substring / containment check (require min 2 chars to avoid false positives)
    if len(norm) >= 2:
        for norm_key, idx in norm_index.items():
            if len(norm_key) >= 2 and (norm in norm_key or norm_key in norm):
                return idx

    return None


def _build_social_proof_from_item(item: Dict) -> Dict:
    """Build a social_proof dict from an unmatched social item."""
    sp: Dict[str, Any] = {}
    if item.get("source_type") == "google_search":
        sp["google_search_mentions"] = 1
    elif item.get("source_type") == "ptt":
        sp["ptt_title_mentions"] = 1
        if item.get("ptt_high_upvotes"):
            sp["ptt_high_upvotes"] = True
    return sp


# ---------------------------------------------------------------------------
# Budget filtering
# ---------------------------------------------------------------------------

def _filter_by_budget(
    restaurants: List[Dict],
    budget: Optional[Dict],
) -> List[Dict]:
    """Remove restaurants whose estimated price significantly exceeds the budget.

    Restaurants without price info are kept (benefit of the doubt).
    """
    if not budget:
        return restaurants

    budget_max = budget.get("max")
    if budget_max is None:
        return restaurants

    try:
        budget_max = float(budget_max)
    except (TypeError, ValueError):
        return restaurants

    threshold = budget_max * _BUDGET_OVERSHOOT_FACTOR
    filtered: List[Dict] = []

    for r in restaurants:
        price_str = r.get("estimated_price") or r.get("price_level")
        if price_str is None:
            filtered.append(r)
            continue

        avg_price = _parse_price_avg(str(price_str))
        if avg_price is None or avg_price <= threshold:
            filtered.append(r)
        else:
            logger.debug(
                "[Budget] Filtered '%s' (avg_price=%.0f > threshold=%.0f)",
                r.get("name", "?"), avg_price, threshold,
            )

    return filtered


# ---------------------------------------------------------------------------
# Search plan text generation
# ---------------------------------------------------------------------------

def _build_search_plan_text(
    intent: Dict,
    max_distance_km: float,
    location: str,
) -> str:
    """Generate a human-readable search plan for UI display."""
    primary = intent.get("primary_keywords", [])
    secondary = intent.get("secondary_keywords", [])
    all_kw = primary + secondary

    kw_text = "、".join(all_kw) if all_kw else "一般餐廳"
    radius_text = (
        f"{int(max_distance_km * 1000)}m"
        if max_distance_km < 1
        else f"{max_distance_km:.1f}km"
    )

    return (
        f"搜尋「{kw_text}」在 {location} 附近 {radius_text} 範圍內的餐廳，"
        f"同時搜尋 Google 搜尋結果與 PTT 美食板的社群推薦。"
    )


# ---------------------------------------------------------------------------
# Source count summary
# ---------------------------------------------------------------------------

def _count_sources(restaurants: List[Dict]) -> Dict[str, int]:
    """Count how many restaurants came from each source."""
    counts: Dict[str, int] = {
        "google_maps": 0,
        "google_search": 0,
        "ptt": 0,
    }
    for r in restaurants:
        source = r.get("source", "google_maps")
        if source in ("google_maps",):
            counts["google_maps"] += 1
        elif source in ("social_lookup", "social_only"):
            # Determine original source from social_proof
            sp = r.get("social_proof", {})
            if sp.get("ptt_title_mentions", 0) > 0:
                counts["ptt"] += 1
            elif sp.get("google_search_mentions", 0) > 0:
                counts["google_search"] += 1
            else:
                counts["google_maps"] += 1
        else:
            counts["google_maps"] += 1

    # Also count maps restaurants with social proof
    for r in restaurants:
        sp = r.get("social_proof", {})
        if r.get("source") == "google_maps" or r.get("source") is None:
            if sp.get("google_search_mentions", 0) > 0:
                counts["google_search"] += sp["google_search_mentions"]
            if sp.get("ptt_title_mentions", 0) > 0:
                counts["ptt"] += sp["ptt_title_mentions"]

    return counts


# ---------------------------------------------------------------------------
# Recommendation summary
# ---------------------------------------------------------------------------

def _build_recommendation_summary(
    restaurants: List[Dict],
    intent: Dict,
) -> str:
    """Build a one-line summary of the recommendation results."""
    count = len(restaurants)
    keywords = intent.get("primary_keywords", [])
    kw_text = "、".join(keywords[:3]) if keywords else "餐廳"
    return f"推薦 {count} 家餐廳，涵蓋{kw_text}等類型"


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def generate_recommendation(
    location: str,
    user_input: str,
    max_results: int = 8,
) -> Dict:
    """Generate restaurant recommendations for a given location and user input.

    Orchestrates the full recommendation pipeline:
      Phase 1 - Intent analysis with weather context
      Phase 2 - Triple-track parallel search (Maps + Google Search + PTT)
      Phase 3 - Merge, score, rank, and return top results

    Parameters
    ----------
    location : str
        User location (landmark, address, or area name).
    user_input : str
        Natural language input describing what the user wants to eat.
    max_results : int
        Maximum number of restaurants to return (default 8).

    Returns
    -------
    dict
        Recommendation result with restaurants sorted by final_score.
    """
    pipeline_start = time.time()
    current_hour = datetime.now().hour

    # =====================================================================
    # Phase 1: Intent Analysis (target < 1s)
    # =====================================================================
    phase1_start = time.time()

    # 1a. Get weather / sweat index
    weather_data: Optional[Dict] = None
    sweat_index: Optional[float] = None

    try:
        sweat_result = query_sweat_index_by_location(location)
        if "error" not in sweat_result:
            weather_data, sweat_index = _extract_weather_data(sweat_result)
            logger.info(
                "[Phase 1] Weather: temp=%.1f, humidity=%.0f, sweat=%.1f",
                weather_data.get("temperature", 0),
                weather_data.get("humidity", 0),
                sweat_index,
            )
        else:
            logger.warning("[Phase 1] Sweat index query failed: %s", sweat_result.get("error"))
    except Exception as exc:
        logger.warning("[Phase 1] Weather/sweat query exception: %s", exc)

    # 1b. Intent analysis
    try:
        intent = analyze_intent(
            user_input=user_input,
            weather_data=weather_data,
            current_hour=current_hour,
        )
    except Exception as exc:
        logger.error("[Phase 1] Intent analysis failed: %s", exc)
        return {
            "success": False,
            "error": f"意圖分析失敗: {exc}",
            "location": location,
            "restaurants": [],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    # Use location from intent if available and user didn't provide one explicitly
    effective_location = location or intent.get("location") or ""
    if not effective_location:
        return {
            "success": False,
            "error": "無法判斷搜尋地點，請提供地點資訊",
            "location": "",
            "restaurants": [],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    # 1c. Calculate max search distance from sweat index
    max_distance_km = _max_distance_from_sweat_index(sweat_index)

    phase1_elapsed = time.time() - phase1_start
    logger.info(
        "[Phase 1] Complete in %.2fs | keywords=%s, budget=%s, distance=%.1fkm",
        phase1_elapsed,
        intent.get("primary_keywords"),
        intent.get("budget"),
        max_distance_km,
    )

    # =====================================================================
    # Phase 2: Triple-Track Parallel Search (target < 3s, hard timeout)
    # =====================================================================
    phase2_start = time.time()

    primary_keywords = intent.get("primary_keywords", [])
    secondary_keywords = intent.get("secondary_keywords", [])
    all_keywords = primary_keywords + secondary_keywords

    # Determine per-keyword result limit based on total keywords
    maps_per_keyword = max(5, 12 // max(len(all_keywords), 1))

    maps_results: List[Dict] = []
    google_search_mentions: List[Dict] = []
    ptt_mentions: List[Dict] = []

    with ThreadPoolExecutor(max_workers=MAX_SEARCH_WORKERS) as executor:
        future_maps = executor.submit(
            _run_google_maps_track,
            all_keywords,
            effective_location,
            maps_per_keyword,
        )
        future_google_search = executor.submit(
            _run_google_search_track,
            primary_keywords[:2],  # limit to top 2 keywords for speed
            effective_location,
        )
        future_ptt = executor.submit(
            _run_ptt_track,
            primary_keywords[:2],  # limit to top 2 keywords for speed
            effective_location,
        )

        futures = {
            future_maps: "google_maps",
            future_google_search: "google_search",
            future_ptt: "ptt",
        }

        try:
            for future in as_completed(futures, timeout=SEARCH_TIMEOUT_SECONDS + 1):
                track_name = futures[future]
                try:
                    result = future.result(timeout=0.5)
                    if track_name == "google_maps":
                        maps_results = result
                    elif track_name == "google_search":
                        google_search_mentions = result
                    elif track_name == "ptt":
                        ptt_mentions = result
                    logger.info("[Phase 2] Track %s returned %d results", track_name, len(result))
                except TimeoutError:
                    logger.warning("[Phase 2] Track %s timed out", track_name)
                except Exception as exc:
                    logger.warning("[Phase 2] Track %s failed: %s", track_name, exc)
        except TimeoutError:
            logger.warning("[Phase 2] as_completed global timeout — collecting partial results")

    # Handle case where as_completed itself times out
    # Collect any remaining results that completed within the window
    for future, track_name in futures.items():
        if future.done() and not future.cancelled():
            try:
                result = future.result(timeout=0)
                if track_name == "google_maps" and not maps_results:
                    maps_results = result
                elif track_name == "google_search" and not google_search_mentions:
                    google_search_mentions = result
                elif track_name == "ptt" and not ptt_mentions:
                    ptt_mentions = result
            except Exception:
                pass

    phase2_elapsed = time.time() - phase2_start
    logger.info(
        "[Phase 2] Complete in %.2fs | maps=%d, google_search=%d, ptt=%d",
        phase2_elapsed,
        len(maps_results),
        len(google_search_mentions),
        len(ptt_mentions),
    )

    # Graceful degradation: if all tracks returned nothing, report error
    if not maps_results and not google_search_mentions and not ptt_mentions:
        return {
            "success": False,
            "error": "所有搜尋管道均未找到餐廳，請嘗試更換關鍵字或地點",
            "location": effective_location,
            "restaurants": [],
            "search_keywords": {
                "primary": primary_keywords,
                "secondary": secondary_keywords,
            },
            "weather_info": weather_data,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }

    # =====================================================================
    # Phase 3: Merge + Score + Rank (target < 1.5s)
    # =====================================================================
    phase3_start = time.time()

    # 3a. Merge social proof into maps results
    merged = _merge_social_proof(
        maps_results,
        google_search_mentions,
        ptt_mentions,
        effective_location,
    )
    logger.info("[Phase 3] Merged total: %d restaurants", len(merged))

    # 3b. Calculate walking distances (in-place)
    try:
        calculate_walking_distances_parallel(effective_location, merged)
    except Exception as exc:
        logger.warning("[Phase 3] Walking distance calculation failed: %s", exc)

    # 3c. Filter by distance
    if max_distance_km:
        before_count = len(merged)
        distance_filtered = []
        for r in merged:
            dist = r.get("distance_km")
            if dist is None:
                # Keep restaurants without distance info
                distance_filtered.append(r)
            elif dist <= max_distance_km:
                distance_filtered.append(r)
            else:
                logger.debug(
                    "[Phase 3] Filtered '%s' by distance (%.2f km > %.2f km)",
                    r.get("name", "?"), dist, max_distance_km,
                )
        merged = distance_filtered
        if before_count != len(merged):
            logger.info(
                "[Phase 3] Distance filter: %d -> %d restaurants",
                before_count, len(merged),
            )

    # 3d. Score restaurants with Gemini
    try:
        scored = score_restaurants(
            user_request=user_input,
            intent_analysis=intent,
            restaurants=merged,
        )
    except Exception as exc:
        logger.warning("[Phase 3] Gemini scoring failed, using distance sort: %s", exc)
        # Fallback: sort by distance only
        scored = merged
        for r in scored:
            r.setdefault("final_score", 5.0)
            r.setdefault("relevance_score", 5.0)

    # 3e. Budget filtering (after scoring so estimated_price is populated)
    budget = intent.get("budget")
    scored = _filter_by_budget(scored, budget)

    # 3f. Sort by final_score descending
    scored.sort(key=lambda r: r.get("final_score", 0), reverse=True)

    # 3g. Take top N results
    top_results = scored[:max_results]
    total_found = len(scored)

    phase3_elapsed = time.time() - phase3_start
    logger.info("[Phase 3] Complete in %.2fs | scored=%d, returned=%d", phase3_elapsed, total_found, len(top_results))

    # =====================================================================
    # Build response
    # =====================================================================
    total_elapsed = time.time() - pipeline_start

    weather_info = None
    if weather_data:
        weather_info = {
            "temperature": weather_data.get("temperature"),
            "humidity": weather_data.get("humidity"),
            "sweat_index": weather_data.get("sweat_index"),
            "rain_probability": weather_data.get("rain_probability"),
        }

    search_plan = _build_search_plan_text(intent, max_distance_km, effective_location)

    response = {
        "success": True,
        "location": effective_location,
        "restaurants": top_results,
        "total_found": total_found,
        "recommendation_summary": _build_recommendation_summary(top_results, intent),
        "weather_info": weather_info,
        "search_keywords": {
            "primary": primary_keywords,
            "secondary": secondary_keywords,
        },
        "max_distance_km": max_distance_km,
        "search_sources": _count_sources(top_results),
        "search_plan": search_plan,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "timing": {
            "phase1_intent_s": round(phase1_elapsed, 2),
            "phase2_search_s": round(phase2_elapsed, 2),
            "phase3_score_s": round(phase3_elapsed, 2),
            "total_s": round(total_elapsed, 2),
        },
    }

    logger.info(
        "[Pipeline] Total %.2fs | Phase1=%.2fs Phase2=%.2fs Phase3=%.2fs | %d results",
        total_elapsed, phase1_elapsed, phase2_elapsed, phase3_elapsed, len(top_results),
    )

    return response
