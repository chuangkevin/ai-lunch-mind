# modules/scraper/google_search.py
"""
Google Search Results Scraper - Extracts restaurant recommendations from search snippets.

Searches Google for blog posts, PTT, Dcard articles about restaurants near a location,
then uses Gemini to extract restaurant names from the collected snippets.
"""

import json
import logging
import time
import urllib.parse
from typing import Dict, List, Optional

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.scraper.browser_pool import browser_pool
from modules.ai.gemini_pool import gemini_pool, GeminiPoolExhausted

logger = logging.getLogger(__name__)

# CSS selectors for Google search results (multiple fallbacks)
TITLE_SELECTORS = [
    "h3",
    "div.BNeawe.vvjwJb",
]

SNIPPET_SELECTORS = [
    "div.VwiC3b",
    "span.aCOpRe",
    "div.BNeawe.s3v9rd",
]

# Strings that indicate Google CAPTCHA / bot detection
CAPTCHA_INDICATORS = [
    "sorry/index",
    "google.com/sorry",
    "unusual traffic",
    "automated requests",
]


def _build_search_url(keyword: str, location: str, num_results: int = 10) -> str:
    """Build a Google search URL for restaurant recommendations."""
    query = f"{location} {keyword} 推薦"
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "zh-TW",
        "num": num_results,
    })
    return f"https://www.google.com/search?{params}"


def _is_captcha_page(page_source: str) -> bool:
    """Check if Google returned a CAPTCHA / bot-detection page."""
    lower_source = page_source.lower()
    return any(indicator in lower_source for indicator in CAPTCHA_INDICATORS)


def _extract_snippets(browser, max_results: int) -> tuple:
    """Extract titles and snippets from the current Google search results page.

    Returns:
        Tuple of (titles: list[str], snippets: list[str])
    """
    titles: List[str] = []
    snippets: List[str] = []

    # Extract titles with fallback selectors
    for selector in TITLE_SELECTORS:
        try:
            elements = browser.find_elements(By.CSS_SELECTOR, selector)
            for el in elements[:max_results]:
                text = el.text.strip()
                if text and text not in titles:
                    titles.append(text)
        except Exception:
            continue
        if titles:
            break

    # Extract snippets with fallback selectors
    for selector in SNIPPET_SELECTORS:
        try:
            elements = browser.find_elements(By.CSS_SELECTOR, selector)
            for el in elements[:max_results]:
                text = el.text.strip()
                if text and text not in snippets:
                    snippets.append(text)
        except Exception:
            continue
        if snippets:
            break

    return titles, snippets


@gemini_pool.auto_retry
def _extract_restaurant_names(combined_text: str, *, api_key=None) -> List[Dict]:
    """Use Gemini to extract restaurant names from search snippets.

    Args:
        combined_text: All titles and snippets joined together.
        api_key: Injected by gemini_pool.auto_retry decorator.

    Returns:
        List of dicts with 'name' and 'snippet' keys.
    """
    import google.generativeai as genai

    prompt = (
        "從以下搜尋結果中提取所有被推薦的餐廳名稱。\n"
        "只回傳 JSON 陣列，每個元素格式為 {\"name\": \"餐廳名\", \"snippet\": \"相關描述片段\"}。\n"
        "如果找不到任何餐廳名稱，回傳空陣列 []。\n"
        "不要包含任何其他文字，只回傳 JSON。\n\n"
        f"搜尋結果：\n{combined_text}"
    )

    model = genai.GenerativeModel("gemini-2.0-flash-lite", api_key=api_key)
    response = model.generate_content(
        prompt,
        generation_config={
            "max_output_tokens": 1024,
            "temperature": 0.1,
        },
    )

    # Parse the JSON response
    raw_text = response.text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw_text = "\n".join(lines).strip()

    results = json.loads(raw_text)

    if not isinstance(results, list):
        logger.warning("Gemini returned non-list response: %s", type(results))
        return []

    # Normalize each entry
    normalized = []
    for item in results:
        if isinstance(item, dict) and "name" in item:
            normalized.append({
                "name": item["name"],
                "snippet": item.get("snippet", ""),
            })
        elif isinstance(item, str):
            normalized.append({"name": item, "snippet": ""})

    return normalized


def search_google_recommendations(
    keyword: str,
    location: str,
    max_results: int = 10,
) -> Dict:
    """Scrape Google search results to find restaurant recommendations.

    Searches for "{location} {keyword} 推薦" on Google, extracts titles and
    snippets from the results, then uses Gemini to identify restaurant names.

    Args:
        keyword: Food type, e.g. "拉麵".
        location: Place name, e.g. "台北101".
        max_results: Maximum number of snippet results to scrape.

    Returns:
        Dict with keys:
            - restaurants_mentioned: list of {name, source, snippet}
            - raw_snippets: list of raw snippet strings
            - search_query: the query string used
    """
    search_url = _build_search_url(keyword, location, num_results=max_results)
    search_query = f"{location} {keyword} 推薦"

    empty_result = {
        "restaurants_mentioned": [],
        "raw_snippets": [],
        "search_query": search_query,
    }

    # --- Step 1: Fetch search results via browser pool ---
    browser = None
    titles: List[str] = []
    snippets: List[str] = []

    try:
        browser = browser_pool.get_browser()
        if browser is None:
            logger.warning("Browser pool exhausted, returning empty results")
            return empty_result
    except Exception as e:
        logger.warning("Failed to acquire browser from pool: %s", e)
        return empty_result

    try:
        browser.set_page_load_timeout(3)
        browser.get(search_url)

        # Brief wait for results to render
        time.sleep(0.5)

        # Check for CAPTCHA
        if _is_captcha_page(browser.page_source):
            logger.warning("Google CAPTCHA detected for query: %s", search_query)
            return empty_result

        # Extract snippets
        titles, snippets = _extract_snippets(browser, max_results)

    except TimeoutException:
        logger.warning("Page load timed out for query: %s", search_query)
        # Try to extract whatever loaded before timeout
        try:
            titles, snippets = _extract_snippets(browser, max_results)
        except Exception:
            pass
    except WebDriverException as e:
        logger.error("Selenium error during Google search: %s", e)
    except Exception as e:
        logger.error("Unexpected error during Google search: %s", e)
    finally:
        try:
            browser_pool.release_browser(browser)
        except Exception:
            pass

    raw_snippets = snippets if snippets else []

    if not titles and not snippets:
        logger.info("No search results extracted for query: %s", search_query)
        return empty_result

    # --- Step 2: Use Gemini to extract restaurant names ---
    combined_text = "\n".join(titles + snippets)
    restaurants_mentioned: List[Dict] = []

    try:
        extracted = _extract_restaurant_names(combined_text)
        for item in extracted:
            restaurants_mentioned.append({
                "name": item["name"],
                "source": "google_search",
                "snippet": item.get("snippet", ""),
            })
        logger.info(
            "Extracted %d restaurant names from Google search: %s",
            len(restaurants_mentioned),
            search_query,
        )
    except GeminiPoolExhausted:
        logger.warning("Gemini pool exhausted, returning raw snippets only")
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Gemini JSON response: %s", e)
    except Exception as e:
        logger.error("Gemini extraction failed: %s", e)

    return {
        "restaurants_mentioned": restaurants_mentioned,
        "raw_snippets": raw_snippets,
        "search_query": search_query,
    }
