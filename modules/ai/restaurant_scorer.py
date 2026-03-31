# modules/ai/restaurant_scorer.py
"""
餐廳評分模組 - 取代舊的 ai_validator.py 判斷代理

功能：
1. 使用 Gemini AI 對餐廳進行 0-10 相關性評分
2. 估算缺失的價格資訊
3. 綜合距離、評分、社群口碑、預算等因素計算最終分數
"""

import json
import logging
import math
import re
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from modules.ai.gemini_pool import gemini_pool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BATCH_SIZE = 15
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.3

# Distance scoring breakpoints: (km, score)
_DISTANCE_BREAKPOINTS = [
    (0.0, 10.0),
    (0.5, 8.0),
    (1.0, 6.0),
    (2.0, 4.0),
    (3.0, 2.0),
    (4.0, 0.0),
]

# ---------------------------------------------------------------------------
# Score helper functions
# ---------------------------------------------------------------------------


def _distance_to_score(km: Optional[float]) -> float:
    """Convert distance in km to a 0-10 score. Closer is higher.

    Linear interpolation between breakpoints.
    None / invalid -> 3 (neutral).
    """
    if km is None:
        return 3.0
    try:
        km = float(km)
    except (TypeError, ValueError):
        return 3.0

    if km <= 0:
        return 10.0
    if km >= 4.0:
        return 0.0

    # Linear interpolation between adjacent breakpoints
    for i in range(len(_DISTANCE_BREAKPOINTS) - 1):
        d0, s0 = _DISTANCE_BREAKPOINTS[i]
        d1, s1 = _DISTANCE_BREAKPOINTS[i + 1]
        if d0 <= km <= d1:
            ratio = (km - d0) / (d1 - d0)
            return round(s0 + ratio * (s1 - s0), 2)

    return 0.0


def _rating_to_score(rating: Optional[float]) -> float:
    """Linear map: 3.0 -> 0, 5.0 -> 10. None -> 5 (neutral)."""
    if rating is None:
        return 5.0
    try:
        rating = float(rating)
    except (TypeError, ValueError):
        return 5.0

    score = (rating - 3.0) / 2.0 * 10.0
    return round(max(0.0, min(10.0, score)), 2)


def _social_to_score(social_proof: Optional[Any]) -> float:
    """Score based on social proof mentions using weighted bonus system.

    social_proof can be:
    - dict with structured keys (google_search_mentions, ptt_title_mentions, ptt_high_upvotes)
    - list of mention strings
    - int / float count
    None -> 0.
    """
    if social_proof is None:
        return 0.0

    if isinstance(social_proof, dict):
        score = 0.0
        score += social_proof.get("google_search_mentions", 0) * 1.0
        score += social_proof.get("ptt_title_mentions", 0) * 1.5
        if social_proof.get("ptt_high_upvotes", False):
            score += 0.5
        sources = sum(1 for k in ["google_search_mentions", "ptt_title_mentions"] if social_proof.get(k, 0) > 0)
        if sources > 1:
            score += 1.0
        return round(min(10.0, score), 1)

    if isinstance(social_proof, (int, float)):
        return min(10.0, float(social_proof))

    if isinstance(social_proof, list):
        return min(10.0, float(len(social_proof)))

    return 0.0


def _parse_price_avg(price_str: Optional[str]) -> Optional[float]:
    """Parse a price string like '$180-250' or '180~250' into an average number.

    Also handles Google Maps dollar-sign notation (e.g. '$$', '$$$').
    """
    if price_str is None:
        return None

    price_str = str(price_str).strip()

    # Google Maps $ notation (e.g. "$$", "$$$", "＄＄")
    dollar_count = price_str.count("$") + price_str.count("\uff04")
    if dollar_count > 0 and not re.search(r"\d", price_str):
        price_map = {1: 150, 2: 300, 3: 600, 4: 1000}
        return price_map.get(dollar_count, 300)

    price_str = price_str.replace(",", "").replace("$", "").replace("\uff04", "").replace("NT", "").strip()

    # Range pattern: 180-250, 180~250, 180—250
    m = re.search(r"(\d+)\s*[-~\u2014\u81f3\u5230]\s*(\d+)", price_str)
    if m:
        low, high = float(m.group(1)), float(m.group(2))
        return (low + high) / 2.0

    # Single number
    m = re.search(r"(\d+)", price_str)
    if m:
        return float(m.group(1))

    return None


def _budget_to_score(
    price_str: Optional[str],
    budget_info: Optional[Dict],
) -> float:
    """Score how well the price matches budget. 10=match, 5=unknown, 0=way over.

    budget_info may contain keys like 'max', 'min', 'level', 'description'.
    """
    if budget_info is None:
        return 5.0

    budget_max = budget_info.get("max") or budget_info.get("budget_max")
    if budget_max is None:
        # Try to parse from description
        desc = budget_info.get("description", "") or budget_info.get("level", "")
        parsed = _parse_price_avg(str(desc)) if desc else None
        if parsed:
            budget_max = parsed * 1.2  # treat description as rough center, add margin
        else:
            return 5.0

    try:
        budget_max = float(budget_max)
    except (TypeError, ValueError):
        return 5.0

    avg_price = _parse_price_avg(price_str)
    if avg_price is None:
        return 5.0

    if avg_price <= budget_max:
        return 10.0
    elif avg_price <= budget_max * 1.3:
        # Slightly over: linear drop from 10 to 5
        ratio = (avg_price - budget_max) / (budget_max * 0.3)
        return round(10.0 - 5.0 * ratio, 1)
    elif avg_price <= budget_max * 2.0:
        # Moderately over: linear drop from 5 to 0
        ratio = (avg_price - budget_max * 1.3) / (budget_max * 0.7)
        return round(5.0 - 5.0 * ratio, 1)
    else:
        return 0.0


# ---------------------------------------------------------------------------
# Final score calculation
# ---------------------------------------------------------------------------


def calculate_final_score(
    restaurant: Dict,
    relevance_score: float,
    budget_info: Optional[Dict],
) -> float:
    """Weighted combination of all scoring dimensions."""
    distance_score = _distance_to_score(restaurant.get("distance_km"))
    google_rating_score = _rating_to_score(restaurant.get("rating"))
    social_score = _social_to_score(restaurant.get("social_proof"))
    budget_score = _budget_to_score(
        restaurant.get("estimated_price") or restaurant.get("price_level"),
        budget_info,
    )

    final = (
        0.30 * distance_score
        + 0.25 * relevance_score
        + 0.20 * google_rating_score
        + 0.15 * social_score
        + 0.10 * budget_score
    )
    return round(final, 1)


# ---------------------------------------------------------------------------
# Gemini prompt construction
# ---------------------------------------------------------------------------


def _build_scoring_prompt(
    user_request: str,
    intent_analysis: Dict,
    batch: List[Dict],
    batch_offset: int,
) -> str:
    """Build the Traditional Chinese scoring prompt for a batch of restaurants."""
    keywords = intent_analysis.get("primary_keywords", [])
    budget_desc = ""
    budget_info = intent_analysis.get("budget")
    if budget_info:
        if isinstance(budget_info, dict):
            budget_desc = json.dumps(budget_info, ensure_ascii=False)
        else:
            budget_desc = str(budget_info)

    # User location context for better Gemini assessment
    location = intent_analysis.get("location") or intent_analysis.get("user_location", "")
    location_desc = ""
    if location:
        if isinstance(location, dict):
            location_desc = json.dumps(location, ensure_ascii=False)
        else:
            location_desc = str(location)

    restaurant_lines = []
    for i, r in enumerate(batch):
        idx = batch_offset + i
        line = (
            f"[{idx}] 名稱: {r.get('name', '未知')}, "
            f"地址: {r.get('address', '未知')}, "
            f"Google評分: {r.get('rating', 'N/A')}, "
            f"評論數: {r.get('review_count', 'N/A')}, "
            f"價位: {r.get('price_level', '未知')}, "
            f"距離: {r.get('distance_km', 'N/A')}km, "
            f"營業中: {r.get('open_now', '未知')}"
        )
        if r.get("social_proof"):
            line += f", 社群口碑: {json.dumps(r['social_proof'], ensure_ascii=False)}"
        restaurant_lines.append(line)

    restaurants_text = "\n".join(restaurant_lines)

    prompt = f"""你是午餐推薦系統的餐廳相關性評分器。請根據使用者需求，為每間餐廳評分。

## 使用者原始需求
{user_request}

## 使用者位置
{location_desc if location_desc else '未指定'}

## 已分析的關鍵字
{json.dumps(keywords, ensure_ascii=False)}

## 預算資訊
{budget_desc if budget_desc else '未指定'}

## 餐廳列表
{restaurants_text}

## 評分規則
請為每間餐廳進行以下評估：

### 相關性分數 (relevance_score: 0-10)
- 9-10: 完美匹配（例如使用者要「拉麵」，餐廳名稱或類型就是拉麵店）
- 7-8: 強相關（相關料理類型，例如使用者要「拉麵」，餐廳是日式料理含有拉麵品項）
- 4-6: 中等相關（同大類別，例如使用者要「拉麵」，餐廳是麵食類）
- 1-3: 弱相關（不同料理類型）
- 0: 完全不相關

### 估計價格 (estimated_price)
- 如果餐廳已有價位資訊，保留原始資訊
- 如果缺少價位，請根據餐廳名稱、類型、地段推估合理價格範圍
- 格式：「$下限-上限」，例如「$180-250」

### 推薦理由 (reason)
- 用一句話說明為何推薦或不推薦此餐廳
- 包含匹配度、距離、特色等關鍵資訊
- 使用繁體中文

## 回應格式
請只回傳 JSON 陣列，不要包含其他文字或 markdown 標記：
[
  {{"index": 0, "relevance_score": 8.5, "estimated_price": "$180-250", "reason": "日式豚骨拉麵專賣店，距離近且評價高"}},
  ...
]"""

    return prompt


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------


@gemini_pool.auto_retry
def _call_gemini_scoring(prompt: str, *, api_key: Optional[str] = None) -> Optional[List[Dict]]:
    """Call Gemini API to score a batch of restaurants.

    Decorated with gemini_pool.auto_retry for resilience.
    The api_key parameter is injected by the auto_retry decorator.
    Returns parsed JSON list or None on failure.
    """
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
            response_mime_type="application/json",
        ),
    )

    if not response:
        logger.warning("[Scorer] Gemini 回傳空結果")
        return None

    # Extract text content from response
    text = response.text if hasattr(response, "text") else str(response)

    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.index("\n") if "\n" in text else 3
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        logger.warning("[Scorer] Gemini 回傳非陣列格式: %s", type(parsed).__name__)
        return None
    except json.JSONDecodeError as e:
        logger.warning("[Scorer] Gemini JSON 解析失敗: %s | 原始回應前200字: %s", e, text[:200])
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def score_restaurants(
    user_request: str,
    intent_analysis: Dict,
    restaurants: List[Dict],
) -> List[Dict]:
    """Score a list of restaurants based on user intent and multiple factors.

    Each restaurant dict gets these fields added:
    - relevance_score (float 0-10)
    - estimated_price (str like "$180-250")
    - ai_reason (str, one-line recommendation reason)
    - final_score (float, weighted combination of all factors)

    Returns the same list with added fields.
    """
    if not restaurants:
        logger.info("[Scorer] 無餐廳需要評分")
        return restaurants

    budget_info = intent_analysis.get("budget")
    total = len(restaurants)

    # Collect all Gemini scoring results keyed by original index
    gemini_results: Dict[int, Dict] = {}
    gemini_succeeded = False

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = restaurants[batch_start:batch_end]

        prompt = _build_scoring_prompt(user_request, intent_analysis, batch, batch_start)

        try:
            result_list = _call_gemini_scoring(prompt)
            if result_list:
                gemini_succeeded = True
                for item in result_list:
                    try:
                        idx = int(item.get("index", -1))
                        if 0 <= idx < total:
                            gemini_results[idx] = item
                    except (TypeError, ValueError):
                        continue
        except Exception as e:
            logger.warning("[Scorer] Gemini 批次評分失敗 (batch %d-%d): %s", batch_start, batch_end, e)

    if not gemini_succeeded:
        logger.warning("[Scorer] Gemini 評分全部失敗，使用中性分數 5.0")

    # Apply scores to each restaurant
    relevance_scores = []
    for i, restaurant in enumerate(restaurants):
        gemini_item = gemini_results.get(i, {})

        # Relevance score: from Gemini or neutral fallback
        try:
            relevance_score = float(gemini_item.get("relevance_score", 5.0))
            relevance_score = max(0.0, min(10.0, relevance_score))
        except (TypeError, ValueError):
            relevance_score = 5.0

        # Estimated price: Gemini estimation or existing value
        estimated_price = gemini_item.get("estimated_price")
        if not estimated_price:
            # Preserve existing price_level if available
            existing = restaurant.get("price_level")
            if existing:
                estimated_price = str(existing)
            else:
                estimated_price = None

        # AI reason
        ai_reason = gemini_item.get("reason", "")

        # Set fields on restaurant dict
        restaurant["relevance_score"] = round(relevance_score, 1)
        restaurant["estimated_price"] = estimated_price
        restaurant["ai_reason"] = ai_reason

        # Calculate final composite score
        restaurant["final_score"] = calculate_final_score(
            restaurant, relevance_score, budget_info
        )

        relevance_scores.append(relevance_score)

    # Log summary
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
    logger.info(
        "[Scorer] Scored %d restaurants, avg relevance: %.1f",
        total,
        avg_relevance,
    )

    return restaurants
