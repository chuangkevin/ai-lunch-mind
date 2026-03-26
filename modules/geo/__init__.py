"""
modules.geo -- Geocoding and distance calculation utilities.
"""

from modules.geo.geocoding import (
    geocode_address,
    geocode_address_with_options,
    extract_location_from_url,
    expand_short_url,
    normalize_taiwan_address,
    smart_address_completion,
    validate_and_select_best_address,
    is_valid_taiwan_address,
    clean_address,
    is_complete_address,
    extract_address_from_maps_url,
    parse_google_maps_url,
    generate_fallback_maps_url,
    validate_maps_url,
    get_reliable_maps_url,
    get_location_candidates,
    create_session,
)

from modules.geo.distance import (
    calculate_distance,
    estimate_distance_by_address,
    calculate_walking_distance_from_google_maps,
    calculate_walking_distances_parallel,
)

__all__ = [
    "geocode_address",
    "geocode_address_with_options",
    "extract_location_from_url",
    "expand_short_url",
    "normalize_taiwan_address",
    "smart_address_completion",
    "validate_and_select_best_address",
    "is_valid_taiwan_address",
    "clean_address",
    "is_complete_address",
    "extract_address_from_maps_url",
    "parse_google_maps_url",
    "generate_fallback_maps_url",
    "validate_maps_url",
    "get_reliable_maps_url",
    "get_location_candidates",
    "create_session",
    "calculate_distance",
    "estimate_distance_by_address",
    "calculate_walking_distance_from_google_maps",
    "calculate_walking_distances_parallel",
]
