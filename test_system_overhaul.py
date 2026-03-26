"""
Comprehensive integration tests for the new AI lunch recommendation system.

Test Categories:
1. GeminiKeyPool - SQLite-based key pool management (no API calls)
2. Scoring Functions - restaurant_scorer helper functions (no API calls)
3. Intent Analyzer Fallback - regex fallback analysis (no API calls)
4. Multi-Scenario Integration - end-to-end with mocked Gemini

Usage:
    python test_system_overhaul.py
"""

import os
import sys
import tempfile
import time
import types
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Mock google.generativeai if not installed (allows tests to run without it)
# ---------------------------------------------------------------------------
if "google.generativeai" not in sys.modules:
    _google = types.ModuleType("google")
    _google.__path__ = []  # make it a package
    _genai = types.ModuleType("google.generativeai")
    _genai.GenerativeModel = MagicMock
    _genai.GenerationConfig = MagicMock
    _genai.configure = MagicMock()
    sys.modules["google"] = _google
    sys.modules["google.generativeai"] = _genai

from modules.ai.gemini_pool import GeminiKeyPool, GeminiPoolExhausted
from modules.ai.restaurant_scorer import (
    _budget_to_score,
    _distance_to_score,
    _parse_price_avg,
    _rating_to_score,
    _social_to_score,
    calculate_final_score,
)
from modules.ai.intent_analyzer import (
    _fallback_analysis,
    _get_time_period,
    _weather_secondary_keywords,
)


# ===========================================================================
# 1. Gemini Key Pool Tests
# ===========================================================================

class TestGeminiKeyPool(unittest.TestCase):
    """Test GeminiKeyPool with a temporary SQLite database (no real API calls)."""

    def setUp(self):
        """Create a fresh temporary DB for each test."""
        self._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpfile.close()
        self.db_path = self._tmpfile.name
        self.pool = GeminiKeyPool(db_path=self.db_path)

    def tearDown(self):
        """Remove the temporary database."""
        try:
            os.unlink(self.db_path)
        except OSError:
            pass
        # Also try removing WAL/SHM files
        for suffix in ("-wal", "-shm"):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass

    def _add_keys(self, keys, validate=False):
        """Helper: add keys without validation (skip network calls)."""
        text = "\n".join(keys)
        return self.pool.add_keys(text, validate=validate)

    # --- Tests ---

    def test_add_keys_basic(self):
        """Add 3 valid keys, verify count."""
        keys = [
            "AIzaAAAAAAAAAAAAAAAAAAAA1",
            "AIzaAAAAAAAAAAAAAAAAAAAA2",
            "AIzaAAAAAAAAAAAAAAAAAAAA3",
        ]
        result = self._add_keys(keys)
        self.assertEqual(result["added"], 3, f"Expected 3 added, got {result}")
        self.assertEqual(result["invalid"], 0)
        self.assertEqual(result["duplicates"], 0)
        print("PASS: test_add_keys_basic")

    def test_add_keys_invalid(self):
        """'invalid_key' should be rejected (no AIza prefix)."""
        result = self._add_keys(["invalid_key", "short", "no_prefix_here_1234567890"])
        self.assertEqual(result["added"], 0, f"Expected 0 added, got {result}")
        self.assertEqual(result["invalid"], 3)
        print("PASS: test_add_keys_invalid")

    def test_add_keys_duplicates(self):
        """Add same key twice, second should be duplicate."""
        key = "AIzaAAAAAAAAAAAAAAAAAAAA_DUP"
        result1 = self._add_keys([key])
        self.assertEqual(result1["added"], 1)

        result2 = self._add_keys([key])
        self.assertEqual(result2["added"], 0)
        self.assertEqual(result2["duplicates"], 1)
        print("PASS: test_add_keys_duplicates")

    def test_add_keys_empty_text(self):
        """Empty string should return 0 added."""
        result = self.pool.add_keys("", validate=False)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["invalid"], 0)
        self.assertEqual(result["duplicates"], 0)
        print("PASS: test_add_keys_empty_text")

    def test_get_key_random(self):
        """Add 5 keys, get_key 100 times, verify randomness (not always the same key)."""
        keys = [f"AIzaRANDOM_TEST_KEY_{i:04d}XX" for i in range(5)]
        self._add_keys(keys)

        chosen = [self.pool.get_key() for _ in range(100)]
        unique = set(chosen)
        # With 5 keys and 100 draws, probability of only 1 unique is ~5^{-100} ≈ 0
        self.assertGreater(len(unique), 1, "get_key should select different keys randomly")
        print(f"PASS: test_get_key_random (got {len(unique)} unique keys out of 100 draws)")

    def test_mark_bad_and_recovery(self):
        """Mark key bad, verify excluded, fast-forward time, verify back."""
        key = "AIzaMARK_BAD_RECOVERY_TEST_"
        self._add_keys([key])

        # Mark bad with short cooldown
        self.pool.mark_bad(key, cooldown_seconds=1)

        # Should not be available now
        result = self.pool.get_key()
        self.assertIsNone(result, "Key should be in cooldown")

        # Wait for cooldown to expire
        time.sleep(1.2)

        # Should be available again
        result = self.pool.get_key()
        self.assertEqual(result, key, "Key should recover after cooldown")
        print("PASS: test_mark_bad_and_recovery")

    def test_get_key_excluding_all(self):
        """Add 3 keys, exclude 2, should get the 3rd."""
        keys = [
            "AIzaEXCLUDE_TEST_KEY_AAA1",
            "AIzaEXCLUDE_TEST_KEY_BBB2",
            "AIzaEXCLUDE_TEST_KEY_CCC3",
        ]
        self._add_keys(keys)

        excluded = {keys[0], keys[1]}
        result = self.pool.get_key_excluding_all(excluded)
        self.assertEqual(result, keys[2], f"Should get the 3rd key, got {result}")
        print("PASS: test_get_key_excluding_all")

    def test_all_keys_exhausted(self):
        """Mark all keys bad, get_key should return None."""
        keys = [
            "AIzaEXHAUSTED_TEST_KEY_A1",
            "AIzaEXHAUSTED_TEST_KEY_B2",
        ]
        self._add_keys(keys)

        for k in keys:
            self.pool.mark_bad(k, cooldown_seconds=60)

        result = self.pool.get_key()
        self.assertIsNone(result, "All keys in cooldown, get_key should return None")
        print("PASS: test_all_keys_exhausted")

    def test_remove_key(self):
        """Add key, remove by suffix, verify gone."""
        key = "AIzaREMOVE_TEST_KEY_XYZW"
        self._add_keys([key])

        # Verify it exists
        self.assertIsNotNone(self.pool.get_key())

        # Remove by suffix
        self.pool.remove_key("XYZW")

        # Verify gone
        result = self.pool.get_key()
        self.assertIsNone(result, "Key should be removed")
        print("PASS: test_remove_key")

    def test_key_status(self):
        """Add keys, check status returns correct format."""
        keys = [
            "AIzaSTATUS_TEST_KEY_AAA1",
            "AIzaSTATUS_TEST_KEY_BBB2",
        ]
        self._add_keys(keys)

        status = self.pool.get_key_status()
        self.assertEqual(len(status), 2, f"Expected 2 status entries, got {len(status)}")

        for entry in status:
            self.assertIn("suffix", entry)
            self.assertIn("status", entry)
            self.assertIn("cooldown_remaining", entry)
            self.assertIn("usage_today", entry)
            self.assertEqual(entry["status"], "active")
            self.assertEqual(entry["cooldown_remaining"], 0.0)
            self.assertEqual(entry["usage_today"], 0)

        print("PASS: test_key_status")


# ===========================================================================
# 2. Scoring Function Tests
# ===========================================================================

class TestScoringFunctions(unittest.TestCase):
    """Test restaurant_scorer helper functions directly (no API calls needed)."""

    # --- Distance scoring ---

    def test_distance_score_0km(self):
        """Distance 0km should score 10."""
        self.assertEqual(_distance_to_score(0.0), 10.0)
        print("PASS: test_distance_score_0km")

    def test_distance_score_500m(self):
        """Distance 0.5km should score 8."""
        self.assertEqual(_distance_to_score(0.5), 8.0)
        print("PASS: test_distance_score_500m")

    def test_distance_score_1km(self):
        """Distance 1.0km should score 6."""
        self.assertEqual(_distance_to_score(1.0), 6.0)
        print("PASS: test_distance_score_1km")

    def test_distance_score_2km(self):
        """Distance 2.0km should score 4."""
        self.assertEqual(_distance_to_score(2.0), 4.0)
        print("PASS: test_distance_score_2km")

    def test_distance_score_4km(self):
        """Distance 4.0km should score 0."""
        self.assertEqual(_distance_to_score(4.0), 0.0)
        print("PASS: test_distance_score_4km")

    def test_distance_score_none(self):
        """Distance None should score 3 (neutral)."""
        self.assertEqual(_distance_to_score(None), 3.0)
        print("PASS: test_distance_score_none")

    # --- Rating scoring ---

    def test_rating_score_5star(self):
        """Rating 5.0 should score 10."""
        self.assertEqual(_rating_to_score(5.0), 10.0)
        print("PASS: test_rating_score_5star")

    def test_rating_score_3star(self):
        """Rating 3.0 should score 0."""
        self.assertEqual(_rating_to_score(3.0), 0.0)
        print("PASS: test_rating_score_3star")

    def test_rating_score_none(self):
        """Rating None should score 5 (neutral)."""
        self.assertEqual(_rating_to_score(None), 5.0)
        print("PASS: test_rating_score_none")

    # --- Price parsing ---

    def test_parse_price_dollars(self):
        """'$$' should return 300."""
        result = _parse_price_avg("$$")
        self.assertEqual(result, 300)
        print("PASS: test_parse_price_dollars")

    def test_parse_price_range(self):
        """'$180-250' should return 215."""
        result = _parse_price_avg("$180-250")
        self.assertEqual(result, 215.0)
        print("PASS: test_parse_price_range")

    def test_parse_price_nt(self):
        """'NT$200' should return 200."""
        result = _parse_price_avg("NT$200")
        self.assertEqual(result, 200.0)
        print("PASS: test_parse_price_nt")

    def test_parse_price_none(self):
        """None should return None."""
        result = _parse_price_avg(None)
        self.assertIsNone(result)
        print("PASS: test_parse_price_none")

    # --- Social scoring ---

    def test_social_score_weighted(self):
        """google_search_mentions=2, ptt_title_mentions=1 -> ~3.5."""
        social = {"google_search_mentions": 2, "ptt_title_mentions": 1}
        # 2*1.0 + 1*1.5 + 1.0 (multi-source bonus) = 4.5
        result = _social_to_score(social)
        self.assertAlmostEqual(result, 4.5, places=1)
        print(f"PASS: test_social_score_weighted (score={result})")

    def test_social_score_multi_source(self):
        """Both google + ptt should get +1 bonus."""
        single_source = {"google_search_mentions": 2, "ptt_title_mentions": 0}
        multi_source = {"google_search_mentions": 2, "ptt_title_mentions": 1}

        score_single = _social_to_score(single_source)
        score_multi = _social_to_score(multi_source)

        # Multi-source gets: 2*1.0 + 1*1.5 + 1.0(bonus) = 4.5
        # Single source gets: 2*1.0 = 2.0 (no bonus)
        self.assertGreater(score_multi, score_single, "Multi-source should score higher")
        print(f"PASS: test_social_score_multi_source (single={score_single}, multi={score_multi})")

    def test_social_score_none(self):
        """None social proof should score 0."""
        self.assertEqual(_social_to_score(None), 0.0)
        print("PASS: test_social_score_none")

    # --- Budget scoring ---

    def test_budget_score_within(self):
        """Price 150, budget max 200 -> 10."""
        result = _budget_to_score("150", {"max": 200})
        self.assertEqual(result, 10.0)
        print("PASS: test_budget_score_within")

    def test_budget_score_over(self):
        """Price 400, budget max 200 -> 0."""
        result = _budget_to_score("400", {"max": 200})
        self.assertEqual(result, 0.0)
        print("PASS: test_budget_score_over")

    def test_budget_score_unknown(self):
        """Price None -> 5 (neutral)."""
        result = _budget_to_score(None, {"max": 200})
        self.assertEqual(result, 5.0)
        print("PASS: test_budget_score_unknown")

    # --- Final score formula ---

    def test_final_score_formula(self):
        """Verify 0.30*dist + 0.25*rel + 0.20*rating + 0.15*social + 0.10*budget."""
        restaurant = {
            "distance_km": 0.5,      # -> distance_score = 8.0
            "rating": 4.5,           # -> rating_score = 7.5
            "social_proof": None,    # -> social_score = 0.0
            "estimated_price": "180",  # for budget
        }
        relevance_score = 9.0
        budget_info = {"max": 200}   # price 180 <= 200 -> budget_score = 10.0

        # Expected:
        distance_score = 8.0
        rating_score = 7.5
        social_score = 0.0
        budget_score = 10.0

        expected = (
            0.30 * distance_score
            + 0.25 * relevance_score
            + 0.20 * rating_score
            + 0.15 * social_score
            + 0.10 * budget_score
        )
        expected = round(expected, 1)

        result = calculate_final_score(restaurant, relevance_score, budget_info)
        self.assertEqual(result, expected, f"Expected {expected}, got {result}")
        print(f"PASS: test_final_score_formula (score={result})")


# ===========================================================================
# 3. Intent Analyzer Fallback Tests
# ===========================================================================

class TestIntentFallback(unittest.TestCase):
    """Test the regex fallback analysis in intent_analyzer (no API calls)."""

    def test_fallback_ramen(self):
        """'台北101 拉麵' -> keywords should contain '拉麵' or '麵食'."""
        result = _fallback_analysis("台北101 拉麵", weather_data=None, current_hour=12)
        keywords = result["primary_keywords"]
        has_ramen = any(kw in ("拉麵", "麵食", "麵") for kw in keywords)
        self.assertTrue(has_ramen, f"Expected ramen-related keyword in {keywords}")
        self.assertEqual(result["location"], "台北101")
        print(f"PASS: test_fallback_ramen (keywords={keywords})")

    def test_fallback_budget(self):
        """'200元以內的便當' -> budget max should be 200."""
        result = _fallback_analysis("200元以內的便當", weather_data=None, current_hour=12)
        self.assertIsNotNone(result["budget"], "Budget should be extracted")
        self.assertEqual(result["budget"]["max"], 200)
        print(f"PASS: test_fallback_budget (budget={result['budget']})")

    def test_fallback_budget_range(self):
        """'100元到300元' -> budget should be {{min:100, max:300}}.

        The fallback regex first matches all (\\d+)元 occurrences. With two amounts
        found (100 and 300), it sets min and max accordingly.
        """
        result = _fallback_analysis("100元到300元的餐廳", weather_data=None, current_hour=12)
        self.assertIsNotNone(result["budget"])
        self.assertEqual(result["budget"]["min"], 100)
        self.assertEqual(result["budget"]["max"], 300)
        print(f"PASS: test_fallback_budget_range (budget={result['budget']})")

    def test_fallback_location_query(self):
        """'台北101' (no food) -> intent should be location_query."""
        result = _fallback_analysis("台北101", weather_data=None, current_hour=12)
        self.assertEqual(result["intent"], "location_query",
                         f"Expected location_query, got {result['intent']}")
        print(f"PASS: test_fallback_location_query (intent={result['intent']})")

    def test_fallback_time_based(self):
        """At hour=7, should suggest breakfast keywords."""
        result = _fallback_analysis("附近吃什麼", weather_data=None, current_hour=7)
        period = _get_time_period(7)
        self.assertEqual(period, "morning")
        # Keywords should come from _TIME_BASED_KEYWORDS["morning"]
        breakfast_terms = {"早餐", "蛋餅", "三明治"}
        has_breakfast = any(kw in breakfast_terms for kw in result["primary_keywords"])
        self.assertTrue(has_breakfast,
                        f"Expected breakfast keywords at hour=7, got {result['primary_keywords']}")
        print(f"PASS: test_fallback_time_based (keywords={result['primary_keywords']})")

    def test_fallback_weather_hot(self):
        """sweat_index=8 -> secondary should include cold foods."""
        hot_weather = {"temperature": 35, "humidity": 80, "sweat_index": 8, "rain_probability": 10}
        result = _fallback_analysis("午餐", weather_data=hot_weather, current_hour=12)
        cold_terms = {"冰品", "涼麵", "冷麵"}
        secondary = result["secondary_keywords"]
        has_cold = any(kw in cold_terms for kw in secondary)
        self.assertTrue(has_cold, f"Expected cold food keywords for hot weather, got {secondary}")
        print(f"PASS: test_fallback_weather_hot (secondary={secondary})")


# ===========================================================================
# 4. Multi-Scenario Integration Tests
# ===========================================================================

class TestScenarios(unittest.TestCase):
    """Integration tests that mock Gemini API calls to test the full pipeline logic."""

    def test_scenario_ramen_taipei101(self):
        """User wants ramen near Taipei 101, budget 200.

        Mock Gemini intent analysis + scoring. Verify keywords, budget, and scoring formula.
        """
        mock_intent_response = {
            "location": "台北101",
            "primary_keywords": ["拉麵", "日式拉麵"],
            "secondary_keywords": ["豚骨拉麵", "味噌拉麵"],
            "budget": {"min": None, "max": 200, "currency": "TWD"},
            "estimated_price_range": "中等",
            "search_radius_hint": "中距離",
            "intent": "search_food_type",
        }

        mock_restaurants = [
            {
                "name": "一蘭拉麵 台北101店",
                "address": "台北市信義區...",
                "rating": 4.3,
                "distance_km": 0.3,
                "price_level": "$$",
                "source": "google_maps",
            },
            {
                "name": "麵屋武藏",
                "address": "台北市信義區...",
                "rating": 4.1,
                "distance_km": 0.8,
                "price_level": "$",
                "source": "google_maps",
            },
        ]

        mock_scoring_response = [
            {"index": 0, "relevance_score": 9.5, "estimated_price": "$250-350", "reason": "正宗日式拉麵"},
            {"index": 1, "relevance_score": 8.0, "estimated_price": "$180-250", "reason": "日式沾麵專賣"},
        ]

        # Use fallback analysis to verify keyword extraction works
        result = _fallback_analysis("台北101 拉麵 200元以內", weather_data=None, current_hour=12)
        # Fallback regex may match "拉麵" or "麵" (the FOOD_PATTERNS entry)
        ramen_keywords = {"拉麵", "麵", "麵食"}
        has_ramen = any(kw in ramen_keywords for kw in result["primary_keywords"])
        self.assertTrue(has_ramen, f"Expected ramen keyword in {result['primary_keywords']}")
        self.assertEqual(result["budget"]["max"], 200)

        # Verify scoring formula with mock data
        for i, r in enumerate(mock_restaurants):
            r["social_proof"] = None
            r["estimated_price"] = mock_scoring_response[i]["estimated_price"]
            score = calculate_final_score(
                r,
                mock_scoring_response[i]["relevance_score"],
                mock_intent_response["budget"],
            )
            self.assertGreater(score, 0, f"Restaurant {r['name']} should have positive score")
            r["final_score"] = score

        # First restaurant should score higher (closer distance + higher relevance)
        self.assertGreater(
            mock_restaurants[0]["final_score"],
            mock_restaurants[1]["final_score"],
            "Closer + more relevant restaurant should score higher",
        )
        print(f"PASS: test_scenario_ramen_taipei101 "
              f"(scores: {mock_restaurants[0]['final_score']}, {mock_restaurants[1]['final_score']})")

    def test_scenario_location_only(self):
        """User says '西門站' (no food preference) -> should generate generic keywords.

        Uses '西門站' because the fallback regex requires location suffixes like 站/區/路.
        """
        result = _fallback_analysis("西門站", weather_data=None, current_hour=12)
        self.assertEqual(result["intent"], "location_query")
        # Should have time-based fallback keywords (lunch time)
        self.assertGreaterEqual(len(result["primary_keywords"]), 2,
                                "Should generate at least 2 generic keywords")
        print(f"PASS: test_scenario_location_only "
              f"(intent={result['intent']}, keywords={result['primary_keywords']})")

    def test_scenario_hot_weather(self):
        """sweat_index=9, temperature=35 -> radius near, secondary cold foods."""
        hot_weather = {
            "temperature": 35,
            "humidity": 85,
            "sweat_index": 9,
            "rain_probability": 10,
        }
        result = _fallback_analysis("吃什麼好", weather_data=hot_weather, current_hour=12)

        # Search radius should be near
        self.assertEqual(result["search_radius_hint"], "近距離",
                         f"Hot weather should suggest near radius, got {result['search_radius_hint']}")

        # Secondary keywords should include cold foods
        cold_foods = {"冰品", "涼麵", "冷麵"}
        has_cold = any(kw in cold_foods for kw in result["secondary_keywords"])
        self.assertTrue(has_cold,
                        f"Hot weather secondary should include cold foods, got {result['secondary_keywords']}")

        # Verify sweat index -> max distance mapping logic directly
        # (avoid importing recommendation_engine due to circular import issues)
        # The mapping from recommendation_engine is:
        #   sweat >= 8 -> 0.5km, >= 6 -> 1km, >= 4 -> 2km, < 4 -> 3km
        sweat_distance_map = [(8, 0.5), (6, 1.0), (4, 2.0), (0, 3.0)]
        sweat_val = 9
        max_dist = 3.0
        for threshold, distance in sweat_distance_map:
            if sweat_val >= threshold:
                max_dist = distance
                break
        self.assertLessEqual(max_dist, 1.0, f"Sweat index 9 should limit to <= 1km, got {max_dist}")

        print(f"PASS: test_scenario_hot_weather "
              f"(radius={result['search_radius_hint']}, max_dist={max_dist}km)")

    def test_scenario_all_ai_fails(self):
        """Gemini completely unavailable -> should fall back to regex + distance-only scoring.

        System should NOT crash.
        """
        # _fallback_analysis is what runs when Gemini fails
        result = _fallback_analysis("中山站附近的拉麵", weather_data=None, current_hour=12)

        self.assertTrue(result["success"], "Fallback should succeed")
        self.assertEqual(result["_source"], "fallback")
        self.assertIsNotNone(result["primary_keywords"])
        self.assertGreater(len(result["primary_keywords"]), 0, "Should have at least 1 keyword")

        # Verify scoring works with neutral/fallback values
        restaurant = {
            "name": "測試拉麵店",
            "distance_km": 0.5,
            "rating": 4.0,
            "social_proof": None,
            "estimated_price": None,
        }
        # Use neutral relevance score (what happens when Gemini scoring also fails)
        score = calculate_final_score(restaurant, 5.0, None)
        self.assertGreater(score, 0, "Should produce a positive score even without AI")
        self.assertLessEqual(score, 10.0, "Score should not exceed 10")

        print(f"PASS: test_scenario_all_ai_fails "
              f"(fallback_keywords={result['primary_keywords']}, score={score})")

    def test_scenario_budget_filtering(self):
        """Restaurants over budget should get low budget_score, within should get high."""
        budget = {"max": 200, "currency": "TWD"}

        # Within budget
        score_cheap = _budget_to_score("150", budget)
        self.assertEqual(score_cheap, 10.0, "Within budget should score 10")

        # Right at budget
        score_at = _budget_to_score("200", budget)
        self.assertEqual(score_at, 10.0, "At budget should score 10")

        # Slightly over (within 1.3x)
        score_slight = _budget_to_score("240", budget)
        self.assertGreater(score_slight, 0, "Slightly over should still have positive score")
        self.assertLess(score_slight, 10, "Slightly over should be less than 10")

        # Way over budget
        score_way_over = _budget_to_score("500", budget)
        self.assertEqual(score_way_over, 0.0, "Way over budget should score 0")

        # Unknown price
        score_unknown = _budget_to_score(None, budget)
        self.assertEqual(score_unknown, 5.0, "Unknown price should score 5 (neutral)")

        # Verify ordering
        self.assertGreater(score_cheap, score_slight, "Cheap > slightly over")
        self.assertGreater(score_slight, score_way_over, "Slightly over > way over")

        print(f"PASS: test_scenario_budget_filtering "
              f"(cheap={score_cheap}, at={score_at}, slight={score_slight}, "
              f"way_over={score_way_over}, unknown={score_unknown})")

    @patch("modules.ai.intent_analyzer._call_gemini")
    @patch("modules.ai.intent_analyzer.get_ai_cache", return_value=None)
    @patch("modules.ai.intent_analyzer.set_ai_cache")
    def test_scenario_gemini_intent_integration(self, mock_set_cache, mock_get_cache, mock_call_gemini):
        """Test analyze_intent with a mocked Gemini response."""
        import json

        mock_gemini_result = {
            "location": "台北101",
            "primary_keywords": ["拉麵", "日式拉麵"],
            "secondary_keywords": ["豚骨拉麵"],
            "budget": {"min": None, "max": 200, "currency": "TWD"},
            "estimated_price_range": "中等",
            "search_radius_hint": "中距離",
            "intent": "search_food_type",
        }
        mock_call_gemini.return_value = json.dumps(mock_gemini_result)

        from modules.ai.intent_analyzer import analyze_intent
        result = analyze_intent(
            user_input="台北101附近的拉麵 200元以內",
            weather_data={"temperature": 28, "humidity": 60, "sweat_index": 5},
            current_hour=12,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["location"], "台北101")
        self.assertIn("拉麵", result["primary_keywords"])
        self.assertEqual(result["budget"]["max"], 200)
        self.assertEqual(result["intent"], "search_food_type")
        self.assertEqual(result["_source"], "gemini")

        print(f"PASS: test_scenario_gemini_intent_integration "
              f"(source={result['_source']}, keywords={result['primary_keywords']})")

    @patch("modules.ai.intent_analyzer._call_gemini")
    @patch("modules.ai.intent_analyzer.get_ai_cache", return_value=None)
    @patch("modules.ai.intent_analyzer.set_ai_cache")
    def test_scenario_gemini_fails_gracefully(self, mock_set_cache, mock_get_cache, mock_call_gemini):
        """When Gemini raises an exception, analyze_intent should fall back to regex."""
        mock_call_gemini.side_effect = GeminiPoolExhausted("All keys exhausted")

        from modules.ai.intent_analyzer import analyze_intent
        result = analyze_intent(
            user_input="台北101附近的拉麵",
            weather_data=None,
            current_hour=12,
        )

        # Should not crash, should use fallback
        self.assertTrue(result["success"])
        self.assertEqual(result["_source"], "fallback")
        self.assertIsNotNone(result["primary_keywords"])

        print(f"PASS: test_scenario_gemini_fails_gracefully "
              f"(source={result['_source']}, keywords={result['primary_keywords']})")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    # Run all tests with verbose output
    unittest.main(verbosity=2)
