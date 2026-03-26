# modules/scraper/ptt_scraper.py
"""
PTT Food board scraper for the AI lunch recommendation system.

Scrapes PTT Food and Lifeismoney boards for restaurant recommendations
using requests + BeautifulSoup (no Selenium). Uses Gemini API via
gemini_pool to extract restaurant names from article text.
"""

import json
import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from modules.ai.gemini_pool import gemini_pool, GeminiPoolExhausted

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PTT_BASE = "https://www.ptt.cc"
BOARDS = ["Food", "Lifeismoney"]
ARTICLE_TAG_PATTERN = re.compile(r"\[(食記|推薦|心得)\]")
REQUEST_TIMEOUT = 2  # seconds per HTTP request
TOTAL_TIMEOUT = 3    # hard ceiling for the entire operation
CONTENT_SNIPPET_LENGTH = 500
HIGH_UPVOTE_THRESHOLD = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
COOKIES = {"over18": "1"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_push_count(text: str) -> int:
    """Convert PTT push-count text to an integer.

    PTT shows:
      - a plain number (e.g. "35")
      - "爆" for very popular articles (mapped to 100)
      - "XX" for heavily down-voted articles (mapped to -1)
      - empty string for zero pushes
    """
    text = text.strip()
    if not text:
        return 0
    if text == "爆":
        return 100
    if text.startswith("X"):
        return -1
    try:
        return int(text)
    except ValueError:
        return 0


def _fetch_search_results(
    session: requests.Session,
    board: str,
    keyword: str,
    location: str,
    deadline: float,
) -> List[Dict]:
    """Search a single PTT board and return a list of candidate articles.

    Each entry: {"title": str, "href": str, "pushes": int}
    """
    query = f"{keyword} {location}"
    url = f"{PTT_BASE}/bbs/{board}/search?q={quote(query)}"

    if time.time() >= deadline:
        return []

    try:
        resp = session.get(
            url, headers=HEADERS, cookies=COOKIES, timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 403:
            logger.info("PTT board %s returned 403, skipping", board)
            return []
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("PTT search request failed for board %s: %s", board, exc)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles: List[Dict] = []

    for entry in soup.select("div.r-ent"):
        # Push count
        nrec_el = entry.select_one("div.nrec")
        pushes = _parse_push_count(nrec_el.get_text() if nrec_el else "")

        # Title + link
        title_el = entry.select_one("div.title a")
        if title_el is None:
            continue
        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")

        # Only keep food-review / recommendation / experience articles
        if not ARTICLE_TAG_PATTERN.search(title):
            continue

        articles.append({
            "title": title,
            "href": href,
            "pushes": pushes,
        })

    return articles


def _fetch_article_snippet(
    session: requests.Session,
    href: str,
    deadline: float,
) -> str:
    """Fetch an article page and return the first N characters of body text."""
    if time.time() >= deadline:
        return ""

    url = f"{PTT_BASE}{href}" if href.startswith("/") else href

    try:
        resp = session.get(
            url, headers=HEADERS, cookies=COOKIES, timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return ""
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove metadata header lines (author, board, title, time)
    for meta in soup.select("div.article-metaline, div.article-metaline-right"):
        meta.decompose()

    main_content = soup.select_one("div#main-content")
    if main_content is None:
        return ""

    # Remove push (推文) section at the bottom
    for push in main_content.select("div.push"):
        push.decompose()

    text = main_content.get_text(separator="\n", strip=True)
    return text[:CONTENT_SNIPPET_LENGTH]


@gemini_pool.auto_retry
def _extract_restaurant_names(combined_text: str, *, api_key=None) -> List[Dict]:
    """Use Gemini to extract restaurant names from PTT article text.

    Returns a list of dicts: [{"name": "...", "mentioned_in_title": bool}, ...]
    """
    import google.generativeai as genai

    prompt = (
        "從以下PTT美食文章中提取所有被推薦的餐廳名稱，"
        "回傳JSON陣列，每個元素包含 name 和 mentioned_in_title (boolean)。\n"
        "只回傳JSON，不要包含其他文字或markdown格式。\n"
        "如果找不到任何餐廳名稱，回傳空陣列 []。\n\n"
        f"{combined_text}"
    )

    model = genai.GenerativeModel("gemini-2.0-flash-lite", api_key=api_key)
    response = model.generate_content(
        prompt,
        generation_config={"max_output_tokens": 512, "temperature": 0.1},
    )

    raw = response.text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, TypeError):
        logger.warning("Gemini returned unparseable JSON for PTT extraction: %s", raw[:200])

    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_ptt_recommendations(
    keyword: str,
    location: str,
    max_articles: int = 5,
) -> Dict:
    """Search PTT Food/Lifeismoney boards for restaurant recommendations.

    Args:
        keyword: Food type, e.g. "拉麵".
        location: Place name, e.g. "台北101" or "信義區".
        max_articles: Maximum number of articles to scrape for content.

    Returns:
        {
            "restaurants_mentioned": [
                {
                    "name": str,
                    "source": "ptt",
                    "ptt_title": str,
                    "ptt_upvotes": int,
                    "ptt_high_upvotes": bool,
                },
                ...
            ],
            "articles_found": int,
            "search_query": str,
        }
    """
    deadline = time.time() + TOTAL_TIMEOUT
    search_query = f"{keyword} {location}"

    empty_result = {
        "restaurants_mentioned": [],
        "articles_found": 0,
        "search_query": search_query,
    }

    # ---- 1. Search both boards ----
    session = requests.Session()
    all_articles: List[Dict] = []

    for board in BOARDS:
        if time.time() >= deadline:
            break
        results = _fetch_search_results(session, board, keyword, location, deadline)
        all_articles.extend(results)

    if not all_articles:
        logger.info("PTT search returned no articles for query: %s", search_query)
        return empty_result

    # ---- 2. De-duplicate by href, sort by pushes descending ----
    seen_hrefs = set()
    unique_articles: List[Dict] = []
    for art in all_articles:
        if art["href"] not in seen_hrefs:
            seen_hrefs.add(art["href"])
            unique_articles.append(art)

    unique_articles.sort(key=lambda a: a["pushes"], reverse=True)
    top_articles = unique_articles[:max_articles]

    articles_found = len(unique_articles)

    # ---- 3. Fetch article content snippets ----
    snippets: List[str] = []
    for art in top_articles:
        if time.time() >= deadline:
            break
        snippet = _fetch_article_snippet(session, art["href"], deadline)
        if snippet:
            snippets.append(f"標題: {art['title']}\n內容: {snippet}")
        else:
            snippets.append(f"標題: {art['title']}")

    combined_text = "\n---\n".join(snippets)

    if not combined_text.strip():
        return {
            "restaurants_mentioned": [],
            "articles_found": articles_found,
            "search_query": search_query,
        }

    # ---- 4. Extract restaurant names via Gemini ----
    try:
        extracted = _extract_restaurant_names(combined_text)
    except GeminiPoolExhausted:
        logger.warning("Gemini pool exhausted during PTT restaurant extraction")
        extracted = []
    except Exception as exc:
        logger.warning("Gemini extraction failed for PTT articles: %s", exc)
        extracted = []

    # ---- 5. Build result: match names with upvote data ----
    # Build a title -> pushes lookup from top articles
    title_pushes: Dict[str, int] = {art["title"]: art["pushes"] for art in top_articles}

    restaurants_mentioned: List[Dict] = []
    seen_names = set()

    for item in extracted:
        name = item.get("name", "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        # Find the best matching article for this restaurant
        best_title = ""
        best_pushes = 0
        mentioned_in_title = item.get("mentioned_in_title", False)

        for art in top_articles:
            if mentioned_in_title and name in art["title"]:
                best_title = art["title"]
                best_pushes = art["pushes"]
                break
            if art["pushes"] > best_pushes:
                best_title = art["title"]
                best_pushes = art["pushes"]

        # If no specific title matched, use the highest-upvoted article
        if not best_title and top_articles:
            best_title = top_articles[0]["title"]
            best_pushes = top_articles[0]["pushes"]

        restaurants_mentioned.append({
            "name": name,
            "source": "ptt",
            "ptt_title": best_title,
            "ptt_upvotes": best_pushes,
            "ptt_high_upvotes": best_pushes > HIGH_UPVOTE_THRESHOLD,
        })

    return {
        "restaurants_mentioned": restaurants_mentioned,
        "articles_found": articles_found,
        "search_query": search_query,
    }
