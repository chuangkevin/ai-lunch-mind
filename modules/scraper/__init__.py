"""
modules.scraper -- Google Maps scraping subsystem.

Convenience re-exports so callers can do::

    from modules.scraper import search_restaurants, browser_pool
"""

from modules.scraper.browser_pool import (
    browser_pool,
    search_cache,
    BrowserPool,
    SearchCache,
    create_chrome_driver,
    create_chrome_driver_fast,
    USER_AGENTS,
)

from modules.scraper.google_maps import (
    search_restaurants,
    search_restaurants_parallel,
    search_restaurants_selenium,
    search_google_maps_restaurants,
    search_google_maps_web,
    search_google_maps_web_fallback,
    search_duckduckgo,
    find_search_results,
    extract_restaurant_info_minimal,
    extract_restaurant_info_display_only,
    extract_restaurant_info_from_element_improved,
    execute_search_strategy_with_pool,
    is_restaurant_relevant,
    remove_duplicate_restaurants,
    sort_restaurants_by_distance,
    get_restaurant_details,
    cleanup_resources,
)

from modules.geo.distance import (
    calculate_walking_distances_parallel,
    calculate_walking_distance_from_google_maps,
    calculate_distance,
    estimate_distance_by_address,
)

__all__ = [
    # Browser pool
    "browser_pool",
    "search_cache",
    "BrowserPool",
    "SearchCache",
    "create_chrome_driver",
    "create_chrome_driver_fast",
    "USER_AGENTS",
    # Search
    "search_restaurants",
    "search_restaurants_parallel",
    "search_restaurants_selenium",
    "search_google_maps_restaurants",
    "search_google_maps_web",
    "search_google_maps_web_fallback",
    "search_duckduckgo",
    "find_search_results",
    "extract_restaurant_info_minimal",
    "extract_restaurant_info_display_only",
    "extract_restaurant_info_from_element_improved",
    "execute_search_strategy_with_pool",
    "is_restaurant_relevant",
    "remove_duplicate_restaurants",
    "sort_restaurants_by_distance",
    "get_restaurant_details",
    "cleanup_resources",
    # Distance (re-exported for convenience)
    "calculate_walking_distances_parallel",
    "calculate_walking_distance_from_google_maps",
    "calculate_distance",
    "estimate_distance_by_address",
]
