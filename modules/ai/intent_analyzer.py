# modules/ai/intent_analyzer.py
"""
意圖分析器 - 使用 Gemini 進行單次融合分析

將使用者意圖、天氣資訊、時間、預算整合為一次 Gemini 呼叫，
取代舊版 dialog_analysis.py 的多步驟分析流程。
"""

import json
import re
import logging
from datetime import datetime
from typing import Optional

from google import genai
from google.genai import types

from modules.ai.gemini_pool import gemini_pool
from modules.sqlite_cache_manager import get_ai_cache, set_ai_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 備用食物類型模式字典
# ---------------------------------------------------------------------------
FOOD_PATTERNS = {
    "冰品": ["冰", "剉冰", "冰品", "冰店", "雪花冰", "芒果冰"],
    "甜點": ["甜點", "蛋糕", "布丁", "甜湯", "仙草"],
    "飲料": ["飲料", "奶茶", "果汁", "氣泡水"],
    "咖啡廳": ["咖啡", "拿鐵", "美式"],
    "早餐": ["早餐", "蛋餅", "三明治", "土司", "漢堡"],
    "火鍋": ["火鍋", "麻辣鍋", "涮涮鍋"],
    "燒烤": ["燒烤", "烤肉", "燒肉"],
    "熱炒": ["熱炒", "炒菜", "合菜"],
    "便當": ["便當", "飯盒", "餐盒"],
    "麵食": ["麵", "拉麵", "意麵", "湯麵", "義大利麵", "牛肉麵", "擔仔麵", "陽春麵"],
    "小吃": ["小吃", "點心", "東山鴨頭", "鹽酥雞", "雞排", "臭豆腐"],
    "輕食": ["輕食", "沙拉"],
    "湯品": ["湯", "煲湯"],
    "素食": ["素食", "蔬食", "素"],
}

# 時段預設關鍵字
_TIME_BASED_KEYWORDS = {
    "morning":  ["早餐", "蛋餅", "三明治"],
    "lunch":    ["便當", "麵食", "小吃"],
    "afternoon": ["咖啡", "甜點", "飲料"],
    "dinner":   ["熱炒", "火鍋", "燒烤"],
    "late_night": ["小吃", "鹽酥雞", "宵夜"],
}

# ---------------------------------------------------------------------------
# Gemini 系統提示
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """你是一個台灣餐廳推薦系統的意圖分析引擎。分析使用者輸入，結合天氣與時間，產出 JSON。

## 核心原則
- **使用者明確指定的食物永遠優先。** 即使天氣熱，使用者要吃火鍋就得搜尋火鍋。

## 欄位規範
1. location: 地點、地標名稱或 null。
2. primary_keywords: 2-4 個具體關鍵字。**指定優先，不受天氣影響。**
3. secondary_keywords: 2-3 個相關菜系或替代選項。
4. budget: {"min": null, "max": 數字, "currency": "TWD"} 或 null。
5. estimated_price_range: "平價"|"中等"|"高價"（150以下/150-400/400以上）。
6. search_radius_hint: "近距離"|"中距離"|"遠距離可"（依天氣熱/雨決定）。
7. intent: "search_food_type"|"location_query"|"search_specific_store"|"search_restaurants"。
8. weather_hints: 0-2 個天氣建議食物（僅供參考，不入搜尋關鍵字）。

回應格式：僅回傳 JSON，不含 Markdown、解釋或多餘文字。"""

# ---------------------------------------------------------------------------
# 內部工具函式
# ---------------------------------------------------------------------------

def _get_time_period(hour: int) -> str:
    """將小時轉換為時段名稱。"""
    if 5 <= hour < 10:
        return "morning"
    elif 10 <= hour < 14:
        return "lunch"
    elif 14 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "dinner"
    else:
        return "late_night"


def _get_time_period_zh(hour: int) -> str:
    """將小時轉換為中文時段描述。"""
    mapping = {
        "morning": "早上",
        "lunch": "中午",
        "afternoon": "下午",
        "dinner": "傍晚/晚上",
        "late_night": "深夜/宵夜時段",
    }
    return mapping[_get_time_period(hour)]


def _build_user_message(
    user_input: str,
    weather_data: Optional[dict],
    current_hour: int,
) -> str:
    """組合使用者訊息，附上天氣與時間的上下文。"""
    parts = [f"使用者輸入：{user_input}"]

    parts.append(f"\n目前時間：{current_hour}:00（{_get_time_period_zh(current_hour)}）")

    if weather_data:
        weather_desc_parts = []
        if "temperature" in weather_data:
            weather_desc_parts.append(f"氣溫 {weather_data['temperature']}°C")
        if "humidity" in weather_data:
            weather_desc_parts.append(f"濕度 {weather_data['humidity']}%")
        if "sweat_index" in weather_data:
            weather_desc_parts.append(f"流汗指數 {weather_data['sweat_index']}")
        if "rain_probability" in weather_data:
            weather_desc_parts.append(f"降雨機率 {weather_data['rain_probability']}%")
        if weather_desc_parts:
            parts.append(f"天氣狀況：{', '.join(weather_desc_parts)}")
    else:
        parts.append("天氣狀況：無資料")

    return "\n".join(parts)


def _build_cache_key(user_input: str, weather_data: Optional[dict], current_hour: int) -> str:
    """
    產生用於快取的複合鍵值。
    天氣與時段會影響分析結果，因此納入鍵值。
    """
    period = _get_time_period(current_hour)
    weather_sig = ""
    if weather_data:
        # 只用影響結果的欄位，並做適度量化以提升命中率
        temp = weather_data.get("temperature")
        si = weather_data.get("sweat_index")
        rain = weather_data.get("rain_probability")
        # 將溫度四捨五入到最近 2 度，降雨機率到最近 10%
        temp_bucket = round(temp / 2) * 2 if temp is not None else "x"
        si_bucket = si if si is not None else "x"
        rain_bucket = round(rain / 10) * 10 if rain is not None else "x"
        weather_sig = f"|t{temp_bucket}|si{si_bucket}|r{rain_bucket}"
    return f"{user_input}|{period}{weather_sig}"


# ---------------------------------------------------------------------------
# Gemini API 呼叫（含自動重試）
# ---------------------------------------------------------------------------

@gemini_pool.auto_retry
def _call_gemini(user_message: str, *, api_key=None) -> str:
    """
    透過 gemini_pool 呼叫 Gemini API，回傳原始文字回應。
    使用 @gemini_pool.auto_retry 裝飾器處理暫時性失敗與 key 輪替。
    """
    client = genai.Client(api_key=api_key, http_options={"timeout": 15})
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            system_instruction=_SYSTEM_PROMPT,
        ),
    )
    return response.text


# ---------------------------------------------------------------------------
# 備用分析（正則表達式）
# ---------------------------------------------------------------------------

def _fallback_analysis(
    user_input: str,
    weather_data: Optional[dict],
    current_hour: int,
) -> dict:
    """
    當 Gemini 完全不可用時，使用正則表達式進行基礎分析。
    """
    logger.warning("使用備用正則分析 (Gemini 不可用)")

    # --- 地點提取 ---
    location = None
    location_patterns = [
        r'([^\s，。！？]*(?:海生館|101|車站|機場|夜市|博物館|美術館|故宮|小巨蛋|威秀|京站|遠百|大學|醫院|高鐵|捷運|商場|百貨|科博館))',
        r'([^\s，。！？]*(?:區|站|路|街|市|縣|鎮|鄉|村))',
        r'(台北[\w]{1,8}|高雄[\w]{1,8}|台中[\w]{1,8}|台南[\w]{1,8}|屏東[\w]{1,8}|新竹[\w]{1,8}|桃園[\w]{1,8})',
    ]
    for pattern in location_patterns:
        matches = re.findall(pattern, user_input)
        if matches:
            location = matches[0]
            break

    # --- 預算提取 ---
    budget = None
    budget_matches = re.findall(r'(\d+)\s*(?:元|塊)', user_input)
    if budget_matches:
        amounts = sorted(int(m) for m in budget_matches)
        if len(amounts) >= 2:
            budget = {"min": amounts[0], "max": amounts[-1], "currency": "TWD"}
        else:
            budget = {"min": None, "max": amounts[0], "currency": "TWD"}

    # 也嘗試匹配 "100-300" 格式
    range_match = re.search(r'(\d+)\s*[-~]\s*(\d+)', user_input)
    if range_match and budget is None:
        lo, hi = int(range_match.group(1)), int(range_match.group(2))
        budget = {"min": min(lo, hi), "max": max(lo, hi), "currency": "TWD"}

    # --- 食物關鍵字檢測 ---
    detected_categories = []
    detected_specifics = []
    user_lower = user_input.lower()
    for category, patterns in FOOD_PATTERNS.items():
        for pat in patterns:
            if pat in user_lower:
                if category not in detected_categories:
                    detected_categories.append(category)
                if pat not in detected_specifics:
                    detected_specifics.append(pat)
                break  # 一個分類只需匹配一次

    # --- 判斷意圖 ---
    chain_stores = ["麥當勞", "星巴克", "肯德基", "摩斯", "漢堡王", "必勝客",
                    "達美樂", "吉野家", "丸亀", "壽司郎", "鼎泰豐", "路易莎"]
    intent = "search_restaurants"
    for store in chain_stores:
        if store in user_input:
            intent = "search_specific_store"
            detected_specifics = [store]
            break
    if intent != "search_specific_store":
        if detected_specifics:
            intent = "search_food_type"
        elif location and not detected_specifics:
            intent = "location_query"

    # --- 主要關鍵字 ---
    primary_keywords = detected_specifics[:4] if detected_specifics else []
    if not primary_keywords:
        period = _get_time_period(current_hour)
        primary_keywords = _TIME_BASED_KEYWORDS.get(period, ["便當", "小吃"])[:3]

    # --- 次要關鍵字（與使用者需求相關的同類型食物，不受天氣影響） ---
    period = _get_time_period(current_hour)
    time_kws = _TIME_BASED_KEYWORDS.get(period, ["便當", "小吃"])
    secondary_keywords = [kw for kw in time_kws if kw not in primary_keywords][:3]

    # --- 天氣提示（軟信號，僅供評分參考，不作為搜尋關鍵字） ---
    weather_hints = _weather_secondary_keywords(weather_data)

    # --- 價格帶 ---
    estimated_price_range = _estimate_price_range(budget, detected_categories)

    # --- 搜尋半徑 ---
    search_radius_hint = _weather_radius_hint(weather_data)

    return {
        "success": True,
        "location": location,
        "primary_keywords": primary_keywords,
        "secondary_keywords": secondary_keywords,
        "budget": budget,
        "estimated_price_range": estimated_price_range,
        "search_radius_hint": search_radius_hint,
        "intent": intent,
        "weather_hints": weather_hints,
        "raw_input": user_input,
        "_source": "fallback",
    }


def _weather_secondary_keywords(weather_data: Optional[dict]) -> list:
    """根據天氣產出次要推薦關鍵字。"""
    if not weather_data:
        return ["便當", "小吃"]

    temp = weather_data.get("temperature", 25)
    sweat = weather_data.get("sweat_index", 5)
    rain = weather_data.get("rain_probability", 0)

    if (temp is not None and temp > 30) or (sweat is not None and sweat >= 7):
        return ["冰品", "涼麵", "冷麵"]
    elif temp is not None and temp < 18:
        return ["火鍋", "湯品", "熱炒"]
    elif rain is not None and rain > 60:
        return ["便當", "外帶小吃"]
    else:
        return ["小吃", "輕食"]


def _weather_radius_hint(weather_data: Optional[dict]) -> str:
    """根據天氣推估搜尋半徑。"""
    if not weather_data:
        return "中距離"

    temp = weather_data.get("temperature", 25)
    sweat = weather_data.get("sweat_index", 5)
    rain = weather_data.get("rain_probability", 0)

    if (temp is not None and temp > 30) or (sweat is not None and sweat >= 7) or (rain is not None and rain > 60):
        return "近距離"
    elif temp is not None and temp < 22 and (rain is None or rain < 30):
        return "遠距離可"
    else:
        return "中距離"


def _estimate_price_range(budget: Optional[dict], categories: list) -> str:
    """推估價格帶。"""
    if budget and budget.get("max"):
        max_val = budget["max"]
        if max_val < 150:
            return "平價"
        elif max_val <= 400:
            return "中等"
        else:
            return "高價"

    # 根據食物類型推估
    expensive = {"火鍋", "燒烤", "燒肉"}
    cheap = {"小吃", "便當", "早餐", "輕食"}
    if any(c in expensive for c in categories):
        return "中等"
    if any(c in cheap for c in categories):
        return "平價"
    return "中等"


# ---------------------------------------------------------------------------
# 主要公開函式
# ---------------------------------------------------------------------------

def analyze_intent(
    user_input: str,
    weather_data: Optional[dict] = None,
    current_hour: Optional[int] = None,
) -> dict:
    """
    分析使用者輸入意圖，融合天氣與時間資訊。

    Parameters
    ----------
    user_input : str
        使用者原始輸入，例如 "台北101附近想吃拉麵，預算200以內"
    weather_data : dict, optional
        天氣資料，包含 temperature, humidity, sweat_index, rain_probability
    current_hour : int, optional
        當前小時 (0-23)，預設取系統時間

    Returns
    -------
    dict
        結構化的意圖分析結果
    """
    if current_hour is None:
        current_hour = datetime.now().hour

    # --- 快取檢查 ---
    cache_key = _build_cache_key(user_input, weather_data, current_hour)
    try:
        cached = get_ai_cache(cache_key, analysis_type="intent")
        if cached:
            logger.info("意圖分析快取命中: '%s'", user_input[:40])
            return cached
    except Exception as e:
        logger.warning("快取讀取失敗: %s", e)

    # --- Gemini 呼叫 ---
    try:
        user_message = _build_user_message(user_input, weather_data, current_hour)
        raw_response = _call_gemini(user_message)

        # 清理可能的 Markdown 包裹
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            # 移除 ```json ... ``` 包裹
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)

        parsed = json.loads(cleaned)

        # 建構標準化輸出
        primary_keywords = parsed.get("primary_keywords", [])[:4]
        secondary_keywords = parsed.get("secondary_keywords", [])[:3]

        # 去重：確保 secondary_keywords 不與 primary_keywords 重疊
        primary_set = set(primary_keywords)
        secondary_keywords = [kw for kw in secondary_keywords if kw not in primary_set]

        # weather_hints: soft scoring signal only — never used as search keywords
        weather_hints = parsed.get("weather_hints", []) or _weather_secondary_keywords(weather_data)

        result = {
            "success": True,
            "location": parsed.get("location"),
            "primary_keywords": primary_keywords,
            "secondary_keywords": secondary_keywords,
            "budget": parsed.get("budget"),
            "estimated_price_range": parsed.get("estimated_price_range", "中等"),
            "search_radius_hint": parsed.get("search_radius_hint", "中距離"),
            "intent": parsed.get("intent", "search_restaurants"),
            "weather_hints": weather_hints,
            "raw_input": user_input,
            "_source": "gemini",
        }

        # 確保 primary_keywords 至少有 2 個
        if len(result["primary_keywords"]) < 2:
            period = _get_time_period(current_hour)
            fallback_kws = _TIME_BASED_KEYWORDS.get(period, ["便當", "小吃"])
            for kw in fallback_kws:
                if kw not in result["primary_keywords"]:
                    result["primary_keywords"].append(kw)
                if len(result["primary_keywords"]) >= 2:
                    break

        # --- 寫入快取 ---
        try:
            set_ai_cache(cache_key, result, analysis_type="intent")
        except Exception as e:
            logger.warning("快取寫入失敗: %s", e)

        logger.info(
            "意圖分析完成: intent=%s, location=%s, keywords=%s",
            result["intent"],
            result["location"],
            result["primary_keywords"],
        )
        return result

    except json.JSONDecodeError as e:
        logger.error("Gemini 回應 JSON 解析失敗: %s", e)
    except Exception as e:
        logger.error("Gemini 意圖分析失敗: %s", e)

    # --- 備用分析 ---
    fallback_result = _fallback_analysis(user_input, weather_data, current_hour)

    # 嘗試快取備用結果
    try:
        set_ai_cache(cache_key, fallback_result, analysis_type="intent")
    except Exception as e:
        logger.warning("備用結果快取寫入失敗: %s", e)

    return fallback_result
