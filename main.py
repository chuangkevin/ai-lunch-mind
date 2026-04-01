# 主程式入口

# Fix Windows cp950 encoding crash when printing emoji characters
import sys
import os
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

import logging
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from modules.weather import get_weather_data
from modules.google_maps import search_restaurants, geocode_address_with_options
from modules.sweat_index import query_sweat_index_by_location, get_sweat_risk_alerts
from modules.sweat_index import get_location_coordinates, get_real_weather_data

# Lazy import: recommendation engine is imported inside endpoints to speed up startup


app = FastAPI(title="AI 午餐推薦系統", description="整合天氣查詢與餐廳推薦的智慧系統")

# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載 frontend 靜態檔案到 /static


# 正確的靜態檔案掛載方式，加上 html=True
import pathlib
STATIC_DIR = str(pathlib.Path(__file__).parent / "frontend")
print(f"[DEBUG] FastAPI static mount: {STATIC_DIR}")
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# / 路徑自動回傳 static/index.html
@app.get("/", response_class=HTMLResponse)
def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# 新增餐廳搜尋頁面路由
@app.get("/restaurant", response_class=HTMLResponse)
def restaurant_page():
    return FileResponse(os.path.join(STATIC_DIR, "restaurant.html"))

# 新增流汗指數頁面路由
@app.get("/sweat_index", response_class=HTMLResponse)
def sweat_index_page():
    return FileResponse(os.path.join(STATIC_DIR, "sweat_index.html"))

# 新增天氣頁面路由
@app.get("/weather_page", response_class=HTMLResponse)
def weather_page():
    return FileResponse(os.path.join(STATIC_DIR, "weather.html"))

# 新增 AI 午餐推薦頁面路由
@app.get("/ai_lunch", response_class=HTMLResponse)
def ai_lunch_page():
    return FileResponse(os.path.join(STATIC_DIR, "ai_lunch_v2.html"))

# 新增設定頁面路由
@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    """Settings page for key management"""
    return FileResponse(os.path.join(STATIC_DIR, "settings.html"))


# ---------------------------------------------------------------------------
# Helper: lazily import the new recommendation engine
# ---------------------------------------------------------------------------
_generate_recommendation = None

def _get_generate_recommendation():
    """Lazily import the new recommendation engine so startup stays fast."""
    global _generate_recommendation
    if _generate_recommendation is None:
        from modules.recommendation_engine import generate_recommendation
        _generate_recommendation = generate_recommendation
    return _generate_recommendation


# ---------------------------------------------------------------------------
# Key Management API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/keys/import")
async def import_keys(request: Request):
    """Bulk import Gemini API keys from textarea text"""
    body = await request.json()
    keys_text = body.get("keys", "")
    validate = body.get("validate", False)
    from modules.ai.gemini_pool import gemini_pool
    result = gemini_pool.add_keys(keys_text, validate=validate)
    return result

@app.get("/api/keys/status")
async def keys_status():
    """Get all keys status (suffix only, never full key)"""
    from modules.ai.gemini_pool import gemini_pool
    return {"keys": gemini_pool.get_key_status()}

@app.delete("/api/keys/{suffix}")
async def delete_key(suffix: str):
    """Delete a key by its last 4 characters"""
    from modules.ai.gemini_pool import gemini_pool
    try:
        gemini_pool.remove_key(suffix)
        return {"status": "ok", "detail": f"已刪除後綴為 {suffix} 的金鑰"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.get("/api/keys/usage")
async def keys_usage():
    """Get usage statistics"""
    from modules.ai.gemini_pool import gemini_pool
    return gemini_pool.get_usage_stats()


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.get("/weather")
def weather_endpoint(latitude: float = None, longitude: float = None, location: str = None):
    """
    天氣查詢 API 端點
    :param latitude: 緯度
    :param longitude: 經度
    :param location: 地名
    :return: 天氣資料
    """
    try:
        if latitude is not None and longitude is not None:
            return get_weather_data(latitude, longitude)
        elif location:
            # 使用流汗指數模組的地理編碼功能
            coords = get_location_coordinates(location)
            if not coords:
                raise HTTPException(status_code=404, detail=f"無法找到地點: {location}")

            latitude, longitude, display_name = coords
            print(f"[API] 天氣查詢請求 - 地點: {display_name} ({latitude}, {longitude})")

            # 獲取天氣資料
            weather_data = get_real_weather_data(latitude, longitude)

            if 'error' in weather_data:
                raise HTTPException(status_code=500, detail=weather_data['message'])

            # 回傳天氣資訊（格式相容於原有前端）
            return {
                "location": display_name,
                "temperature": weather_data.get('temperature'),
                "humidity": weather_data.get('humidity'),
                "wind_speed": weather_data.get('wind_speed'),
                "rain_probability": weather_data.get('rain_probability', {"probability": "N/A", "source": "無資料"}),
                "station_name": weather_data.get('station_name'),
                "distance_km": weather_data.get('distance_km'),
                "data_time": weather_data.get('data_time')
            }
        else:
            raise HTTPException(status_code=400, detail="請提供座標或地名")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 天氣查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")

@app.get("/restaurants")
def restaurants_endpoint(keyword: str = None, user_address: str = None, max_results: int = 10):
    """
    餐廳搜尋 API 端點
    :param keyword: 搜尋關鍵字（如：火鍋、羊肉、燒烤）
    :param user_address: 使用者地址或 Google Maps 短網址
    :param max_results: 最大結果數量
    :return: 餐廳資料列表
    """
    try:
        if not keyword and not user_address:
            raise HTTPException(status_code=400, detail="請提供搜尋關鍵字或地址")

        # 限制最大結果數量
        max_results = min(max_results, 20)

        print(f"[API] 餐廳搜尋請求 - 關鍵字: {keyword}, 地址: {user_address}")

        # 呼叫搜尋函數
        restaurants = search_restaurants(
            keyword=keyword or "餐廳",
            user_address=user_address,
            max_results=max_results
        )

        return {
            "success": True,
            "restaurants": restaurants,
            "total": len(restaurants),
            "keyword": keyword,
            "user_address": user_address
        }

    except Exception as e:
        print(f"[API ERROR] 餐廳搜尋失敗: {e}")
        raise HTTPException(status_code=500, detail=f"搜尋失敗: {str(e)}")


# 流汗指數查詢 API 端點
@app.get("/location-options")
def location_options_endpoint(address: str):
    """
    位置選擇 API - 當地址模糊時返回多個選項供用戶選擇
    :param address: 地址字串
    :return: 單一位置或多個選項
    """
    try:
        result = geocode_address_with_options(address)
        return result
    except Exception as e:
        print(f"[API ERROR] 位置查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=f"位置查詢失敗: {str(e)}")

# 流汗指數查詢 API 端點
@app.get("/sweat-index")
def sweat_index_endpoint(location: str = None):
    """
    流汗指數查詢 API 端點
    :param location: 地點名稱、地址或經緯度
    :return: 流汗指數資料
    """
    try:
        if not location:
            raise HTTPException(status_code=400, detail="請提供地點名稱、地址或經緯度")

        print(f"[API] 流汗指數查詢請求 - 地點: {location}")

        # 調用流汗指數查詢函數
        result = query_sweat_index_by_location(location)

        # 檢查是否有錯誤
        if 'error' in result:
            raise HTTPException(status_code=500, detail=result['message'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 流汗指數查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")


# 流汗風險警報 API 端點
@app.get("/sweat-alerts")
def sweat_alerts_endpoint(temperature: float = None, humidity: float = None, wind_speed: float = 0):
    """
    流汗風險警報 API 端點
    :param temperature: 溫度
    :param humidity: 濕度
    :param wind_speed: 風速（可選）
    :return: 警報列表
    """
    try:
        if temperature is None or humidity is None:
            raise HTTPException(status_code=400, detail="請提供 temperature 和 humidity 參數")

        print(f"[API] 流汗警報查詢請求 - 溫度: {temperature}°C, 濕度: {humidity}%")

        # 調用警報函數
        alerts = get_sweat_risk_alerts(temperature, humidity, wind_speed)

        return {"alerts": alerts}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 流汗警報查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")


# 增強版天氣查詢 API 端點（支援地名）
@app.get("/weather_enhanced")
def weather_enhanced_endpoint(location: str = None, latitude: float = None, longitude: float = None):
    """
    增強版天氣查詢 API 端點（支援地名和座標）
    :param location: 地點名稱
    :param latitude: 緯度
    :param longitude: 經度
    :return: 天氣資料
    """
    try:
        if location:
            # 使用地理編碼功能
            coords = get_location_coordinates(location)
            if not coords:
                raise HTTPException(status_code=404, detail=f"無法找到地點: {location}")

            latitude, longitude, display_name = coords
        elif latitude and longitude:
            display_name = f"座標({latitude},{longitude})"
        else:
            raise HTTPException(status_code=400, detail="請提供 location 或 latitude/longitude 參數")

        print(f"[API] 增強版天氣查詢請求 - 地點: {display_name}")

        # 獲取天氣資料
        weather_data = get_weather_data(latitude, longitude)

        if 'error' in weather_data:
            raise HTTPException(status_code=500, detail=weather_data.get('error', '未知錯誤'))

        # 回傳天氣資訊
        return {
            "locationName": display_name,
            "temperature": weather_data.get('temperature'),
            "humidity": weather_data.get('humidity'),
            "wind_speed": weather_data.get('wind_speed'),
            "station_name": weather_data.get('station_name'),
            "distance_km": weather_data.get('distance_km'),
            "data_time": weather_data.get('data_time'),
            "rain_probability": weather_data.get('rain_probability', {"probability": "N/A", "source": "無資料"})
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 增強版天氣查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")


# ---------------------------------------------------------------------------
# AI 午餐推薦 API 端點 (uses new modules when available, falls back to legacy)
# ---------------------------------------------------------------------------

def _enrich_restaurant(r: dict) -> dict:
    """Ensure new fields exist on every restaurant dict for frontend compatibility."""
    r.setdefault("social_proof", None)
    r.setdefault("ai_reason", None)
    r.setdefault("estimated_price", None)
    r.setdefault("relevance_score", None)
    return r


# AI 午餐推薦主功能 API 端點
@app.get("/ai-lunch-recommendation")
async def ai_lunch_recommendation_endpoint(location: str = None, user_input: str = "", max_results: int = 10):
    """
    AI 午餐推薦主功能 API 端點
    :param location: 位置資訊（地址、地標、經緯度）
    :param user_input: 使用者自然語言輸入（可選）
    :param max_results: 最大推薦結果數量
    :return: 智能餐廳推薦結果
    """
    import asyncio

    try:
        if not location:
            raise HTTPException(status_code=400, detail="請提供位置資訊（location 參數）")

        max_results = min(max_results, 20)

        print(f"[AI推薦] 位置: {location}, 使用者輸入: '{user_input}', 最大結果: {max_results}")

        gen_rec = _get_generate_recommendation()

        loop = asyncio.get_event_loop()
        try:
            recommendation_result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: gen_rec(location=location, user_input=user_input, max_results=max_results),
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="推薦搜尋超時（30秒），請稍後再試")

        # 檢查是否有錯誤
        if 'error' in recommendation_result:
            raise HTTPException(
                status_code=500,
                detail=recommendation_result.get('message', '推薦生成失敗')
            )

        # Enrich restaurants with new fields for frontend
        if "restaurants" in recommendation_result:
            recommendation_result["restaurants"] = [
                _enrich_restaurant(r) for r in recommendation_result["restaurants"]
            ]

        # 提取驗證結果用於記錄
        validation_results = recommendation_result.get('validation_results', {})

        # 記錄驗證警告（不影響使用者回應）
        location_val = validation_results.get('location_validation', {})
        if not location_val.get('is_valid', True):
            print(f"[WARNING] API警告 - 位置驗證問題：{location_val.get('issues', [])}")

        plan_val = validation_results.get('plan_validation', {})
        if not plan_val.get('is_relevant', True):
            print(f"[WARNING] API警告 - 計畫相關性問題：{plan_val.get('missing_aspects', [])}")

        rec_val = validation_results.get('recommendation_validation', {})
        if not rec_val.get('is_satisfactory', True):
            print(f"[WARNING] API警告 - 推薦品質問題：{rec_val.get('issues', [])}")

        return recommendation_result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] AI 午餐推薦失敗: {e}")
        raise HTTPException(status_code=500, detail=f"推薦失敗: {str(e)}")


# 對話式推薦 API 端點（支援位置自動解析）
@app.get("/chat-recommendation")
async def chat_recommendation_endpoint(message: str = None, phase: str = "start"):
    """
    對話式餐廳推薦 API 端點（分階段執行）
    :param message: 完整的使用者輸入訊息
    :param phase: 執行階段 ("start" 回傳搜尋計劃, "search" 執行實際搜尋)
    :return: 分階段的推薦結果
    """
    import asyncio

    try:
        if not message:
            raise HTTPException(status_code=400, detail="請提供使用者訊息（message 參數）")

        print(f"[對話推薦] 使用者訊息: '{message}', 階段: {phase}")

        if phase not in ("start", "search"):
            raise HTTPException(status_code=400, detail="phase 參數必須是 'start' 或 'search'")

        gen_rec = _get_generate_recommendation()

        # Run blocking pipeline in a thread to avoid blocking uvicorn event loop
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: gen_rec(location="", user_input=message, max_results=10),
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="推薦搜尋超時（30秒），請稍後再試")

        if phase == "start":
            return {
                "phase": "plan",
                "success": result.get("success", False),
                "location": result.get("location"),
                "search_plan": result.get("search_plan"),
                "weather_info": result.get("weather_info"),
                "search_keywords": result.get("search_keywords"),
                "message": "搜尋計劃已生成",
                "timestamp": result.get("timestamp"),
                "restaurants": [
                    _enrich_restaurant(r) for r in result.get("restaurants", [])
                ],
            }
        else:
            if "restaurants" in result:
                result["restaurants"] = [
                    _enrich_restaurant(r) for r in result["restaurants"]
                ]
            return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 對話式推薦失敗: {e}")
        raise HTTPException(status_code=500, detail=f"推薦失敗: {str(e)}")


# 分階段對話式推薦 API 端點（POST 版本，支援 JSON 請求體）
@app.post("/chat/recommend")
async def staged_chat_recommendation(request: Request):
    """
    分階段對話式餐廳推薦 API 端點
    支援兩個階段：
    1. phase="start" - 返回搜尋計劃
    2. phase="search" - 執行實際搜尋

    POST Body:
    {
        "message": "使用者訊息",
        "phase": "start" | "search"
    }
    """
    try:
        # 解析 JSON 請求體
        body = await request.json()
        message = body.get("message")
        phase = body.get("phase", "start")

        if not message:
            raise HTTPException(status_code=400, detail="請提供使用者訊息（message 參數）")

        print(f"[分階段推薦] 階段: {phase}, 訊息: '{message}'")

        gen_rec = _get_generate_recommendation()

        # The new engine runs the full pipeline in one call.
        result = gen_rec(
            location=message,
            user_input=message,
            max_results=10,
        )

        # 根據階段決定回應內容
        if phase == "start":
            response_text = result.get("search_plan", "搜尋計劃生成中...")
        else:
            response_text = result.get("recommendation_summary", "推薦結果處理中...")

        # Enrich restaurants with new fields
        restaurants = result.get("restaurants", [])
        restaurants = [_enrich_restaurant(r) for r in restaurants]

        return {
            "status": "success",
            "phase": phase,
            "response": response_text,
            "recommendations": restaurants,
            "data": result,
            "timestamp": result.get("timestamp")
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 分階段推薦失敗: {e}")
        raise HTTPException(status_code=500, detail=f"推薦失敗: {str(e)}")


# ---------------------------------------------------------------------------
# SSE Streaming Recommendation Endpoint
# ---------------------------------------------------------------------------

@app.get("/chat-recommendation-stream")
async def chat_recommendation_stream(message: str = None):
    """SSE streaming endpoint for real-time recommendation progress."""
    if not message:
        raise HTTPException(status_code=400, detail="Missing message")

    async def event_stream():
        import json
        import asyncio
        import time

        def send_event(event_type, data):
            return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        loop = asyncio.get_event_loop()

        # Step 1: Intent Analysis
        yield send_event("thinking", {"step": "intent", "message": "分析您的需求..."})

        try:
            from modules.ai.intent_analyzer import analyze_intent
            from modules.sweat_index import query_sweat_index_by_location
            from modules.recommendation_engine import _extract_weather_data
            from datetime import datetime

            current_hour = datetime.now().hour
            weather_data = None
            sweat_index = None

            # Weather
            try:
                # Extract clean location for weather query (not full message)
                import re as _re
                weather_location = message
                _loc_match = _re.search(r'我在([^\s，。！？,]{2,20})', message)
                if _loc_match:
                    weather_location = _loc_match.group(1)

                sweat_result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None, lambda: query_sweat_index_by_location(weather_location)
                    ),
                    timeout=8,
                )
                if "error" not in sweat_result:
                    weather_data, sweat_index = _extract_weather_data(sweat_result)
                    rain_prob = weather_data.get("rain_probability")
                    yield send_event("weather", {
                        "temperature": weather_data.get("temperature"),
                        "humidity": weather_data.get("humidity"),
                        "sweat_index": sweat_index,
                        "rain_probability": rain_prob,
                    })
                else:
                    yield send_event("thinking", {"step": "weather", "message": "天氣查詢無資料"})
            except asyncio.TimeoutError:
                yield send_event("thinking", {"step": "weather", "message": "天氣查詢超時，跳過"})
            except Exception as e:
                yield send_event("thinking", {"step": "weather", "message": f"天氣查詢跳過: {str(e)[:30]}"})

            # Intent
            intent = await loop.run_in_executor(
                None,
                lambda: analyze_intent(
                    user_input=message,
                    weather_data=weather_data,
                    current_hour=current_hour,
                ),
            )

            location = intent.get("location", "")
            keywords = intent.get("primary_keywords", [])
            secondary = intent.get("secondary_keywords", [])
            budget = intent.get("budget")

            yield send_event("intent", {
                "location": location,
                "keywords": keywords,
                "secondary_keywords": secondary,
                "budget": budget,
                "source": intent.get("_source", "unknown"),
            })

            # Step 2: Search for real restaurants
            search_location = location or "台北"
            kw_preview = ", ".join(keywords[:3]) if keywords else "餐廳"

            # Calculate search distance: max 10min walk (good) / 5min walk (bad)
            # 10min walk ≈ 800m, 5min walk ≈ 400m
            rain_prob = weather_data.get("rain_probability", 0) if weather_data else 0
            max_distance_km = 0.8  # default: good weather, 10min walk
            distance_reason = "舒適天氣，步行10分鐘內 (800m)"
            if sweat_index is not None and sweat_index >= 7:
                max_distance_km = 0.4
                distance_reason = f"流汗指數 {sweat_index} (不舒適)，步行5分鐘內 (400m)"
            elif rain_prob and float(rain_prob) >= 50:
                max_distance_km = 0.4
                distance_reason = f"降雨機率 {rain_prob}%，步行5分鐘內 (400m)"
            elif sweat_index is not None and sweat_index >= 5:
                max_distance_km = 0.6
                distance_reason = f"流汗指數 {sweat_index} (普通)，步行8分鐘內 (600m)"

            yield send_event("analysis", {
                "distance_reason": distance_reason,
                "max_distance_km": max_distance_km,
            })

            yield send_event("thinking", {"step": "search", "message": f"搜尋 {search_location} 的 {kw_preview}..."})

            from modules.fast_search import search_restaurants_fast, enrich_with_gemini, search_social_mentions
            from urllib.parse import quote
            from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

            all_restaurants = []

            # Strategy: Gemini recommends first (fast ~3s), Selenium searches in parallel
            # If Selenium returns results, use those (real data).
            # If Selenium times out, fall back to Gemini results.

            search_kws = keywords[:3]

            # Start Selenium searches in background
            selenium_pool = ThreadPoolExecutor(max_workers=min(3, len(search_kws)))
            selenium_futures = {
                selenium_pool.submit(search_restaurants_fast, kw, search_location, 5): kw
                for kw in search_kws
            }

            # Meanwhile, get Gemini recommendations (fast path ~3s)
            yield send_event("thinking", {"step": "search", "message": f"AI 推薦 + Google Maps 搜尋中..."})

            gemini_results = []
            try:
                from modules.ai.gemini_pool import gemini_pool
                from google import genai as _genai
                from google.genai import types as _types

                api_key = gemini_pool.get_key()
                if api_key:
                    budget_hint = f", 預算{budget['max']}元以內" if budget and budget.get("max") else ""
                    weather_hint = ""
                    if weather_data and weather_data.get("temperature"):
                        weather_hint = f", 天氣{weather_data['temperature']}°C"

                    prompt = f"""推薦 {search_location} 附近的 {', '.join(keywords)} 餐廳{budget_hint}{weather_hint}。
回傳 JSON 陣列，每間包含 name, address, rating, price_level, food_type, reason。
只推薦你確定真實存在的餐廳，地址要具體到路名門牌。回傳 5-8 間。"""

                    client = _genai.Client(api_key=api_key)
                    resp = await loop.run_in_executor(
                        None,
                        lambda: client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=prompt,
                            config=_types.GenerateContentConfig(
                                temperature=0.3,
                                response_mime_type="application/json",
                            ),
                        ),
                    )
                    gemini_list = json.loads(resp.text.strip())
                    if isinstance(gemini_list, list):
                        for r in gemini_list:
                            gemini_results.append({
                                "name": r.get("name", ""),
                                "address": r.get("address", ""),
                                "rating": r.get("rating"),
                                "price_level": r.get("price_level"),
                                "food_type": r.get("food_type", ""),
                                "ai_reason": r.get("reason", ""),
                                "maps_url": f"https://www.google.com/maps/search/{quote(r.get('name',''))}+{quote(search_location)}",
                                "source": "gemini_initial",
                            })
                    logger.info("Gemini initial: %d results", len(gemini_results))
            except Exception as e:
                logger.warning("Gemini initial recommendation failed: %s", e)

            # Collect Selenium results (wait up to 15s more)
            selenium_results = []
            try:
                for future in _as_completed(selenium_futures, timeout=15):
                    kw = selenium_futures[future]
                    try:
                        results = future.result(timeout=1)
                        for r in results:
                            r["food_type"] = kw
                            selenium_results.append(r)
                        logger.info("Selenium '%s': %d results", kw, len(results))
                    except Exception as e:
                        logger.warning("Selenium search failed for '%s': %s", kw, e)
            except Exception:
                logger.warning("Some Selenium searches timed out")
            finally:
                selenium_pool.shutdown(wait=False)

            # Merge: prefer Selenium (real data), supplement with Gemini
            seen_names = set()
            for r in selenium_results:
                name = r.get("name", "").strip()
                if name and name not in seen_names:
                    seen_names.add(name)
                    r["source"] = "google_maps"
                    all_restaurants.append(r)

            for r in gemini_results:
                name = r.get("name", "").strip()
                if name and name not in seen_names:
                    seen_names.add(name)
                    all_restaurants.append(r)

            selenium_count = sum(1 for r in all_restaurants if r.get("source") == "google_maps")
            gemini_count = sum(1 for r in all_restaurants if r.get("source") == "gemini_initial")
            yield send_event("thinking", {
                "step": "search_done",
                "message": f"Google Maps {selenium_count} 間 + AI 推薦 {gemini_count} 間",
            })

            # Enrich (only for Selenium results that lack AI reason)
            yield send_event("thinking", {"step": "enrich", "message": "AI 補充資訊中..."})

            try:
                all_restaurants = await loop.run_in_executor(
                    None,
                    lambda: enrich_with_gemini(
                        all_restaurants, message, search_location,
                        keywords, budget, weather_data,
                    ),
                )
            except Exception as e:
                logger.warning("Gemini enrichment failed: %s", e)

            # Phase 3: Score and rank
            if all_restaurants:
                # Add maps URLs for any missing
                for r in all_restaurants:
                    if not r.get("maps_url"):
                        r["maps_url"] = f"https://www.google.com/maps/search/{quote(r.get('name',''))}+{quote(search_location)}"
                    r.setdefault("social_proof", None)
                    r.setdefault("relevance_score", 7.0)
                    r.setdefault("estimated_price", r.get("price_level"))

                # Phase 3a: Calculate real distances
                yield send_event("thinking", {"step": "distance", "message": "計算步行距離..."})
                try:
                    from modules.fast_search import calculate_real_distances
                    all_restaurants = await loop.run_in_executor(
                        None,
                        lambda: calculate_real_distances(all_restaurants, search_location),
                    )
                    # Filter by max distance + sort
                    # Filter: try preferred distance, expand if nothing found
                    within = [r for r in all_restaurants if r.get("distance_km") is not None and r.get("distance_km") <= max_distance_km]
                    unknown = [r for r in all_restaurants if r.get("distance_km") is None]

                    before_count = len(all_restaurants)
                    if within:
                        all_restaurants = within + unknown
                    elif not within and all_restaurants:
                        # Nothing within preferred range — show closest available
                        known = [r for r in all_restaurants if r.get("distance_km") is not None]
                        known.sort(key=lambda r: r["distance_km"])
                        all_restaurants = known[:5] + unknown
                        if known:
                            yield send_event("thinking", {
                                "step": "distance_expanded",
                                "message": f"{int(max_distance_km*1000)}m 內沒有結果，顯示最近的 {len(known[:5])} 間",
                            })
                    filtered_count = before_count - len(all_restaurants)
                    if filtered_count > 0:
                        logger.info("Filtered %d restaurants beyond %.1fkm", filtered_count, max_distance_km)
                    all_restaurants.sort(key=lambda r: r.get("distance_km") or 999)
                except Exception as e:
                    logger.warning("Distance calculation failed: %s", e)

                # Phase 3b: Social media search
                yield send_event("thinking", {"step": "social", "message": "搜尋 Dcard/Threads/PTT 討論..."})

                try:
                    restaurant_names = [r.get("name", "") for r in all_restaurants if r.get("name")]
                    social_mentions = await loop.run_in_executor(
                        None,
                        lambda: search_social_mentions(restaurant_names, search_location),
                    )
                    # Attach social mentions to restaurants
                    for r in all_restaurants:
                        name = r.get("name", "")
                        if name in social_mentions and social_mentions[name]:
                            platforms = list(set(m["platform"] for m in social_mentions[name]))
                            r["social_proof"] = {
                                "platforms": platforms,
                                "mentions": social_mentions[name][:3],
                                "count": len(social_mentions[name]),
                            }
                    social_count = sum(1 for r in all_restaurants if r.get("social_proof"))
                    if social_count > 0:
                        yield send_event("thinking", {"step": "social_done", "message": f"找到 {social_count} 間有社群討論"})
                except Exception as e:
                    logger.warning("Social search failed: %s", e)

                yield send_event("thinking", {
                    "step": "scoring",
                    "message": f"共 {len(all_restaurants)} 間餐廳，排序中...",
                })

                # Sort: restaurants with social proof first, then by rating
                all_restaurants.sort(
                    key=lambda r: (
                        0 if r.get("social_proof") else 1,
                        -(r.get("rating") or 0),
                    ),
                )

                for i, restaurant in enumerate(all_restaurants):
                    yield send_event("restaurant", {"index": i, "restaurant": restaurant})
                    await asyncio.sleep(0.05)

                yield send_event("done", {
                    "total": len(all_restaurants),
                })
            else:
                yield send_event("error", {"message": "沒有找到餐廳，請換個說法試試"})

        except asyncio.TimeoutError:
            yield send_event("error", {"message": "搜尋超時，請稍後再試"})
        except Exception as e:
            yield send_event("error", {"message": f"推薦失敗: {str(e)}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 健康檢查 API 端點
@app.get("/health")
def health_check():
    """
    系統健康檢查
    """
    try:
        # 檢查環境變數
        api_key_status = "已設置" if os.getenv("CWB_API_KEY") else "未設置"

        # Check Gemini key pool status
        try:
            from modules.ai.gemini_pool import gemini_pool
            gemini_status = gemini_pool.get_key_status()
            gemini_key_count = len(gemini_status)
        except Exception:
            gemini_key_count = 0

        return {
            "status": "healthy",
            "service": "AI 午餐推薦系統（整合流汗指數）",
            "version": "4.0.0",
            "cwb_api_key": api_key_status,
            "gemini_keys": gemini_key_count,
            "endpoints": [
                "/ai-lunch-recommendation?location=地點&user_input=需求 - AI智能推薦",
                "/chat-recommendation?message=完整訊息 - 對話式推薦",
                "/sweat-index?location=地點名稱",
                "/sweat-alerts?temperature=溫度&humidity=濕度",
                "/weather_enhanced?location=地點名稱",
                "/weather?latitude=緯度&longitude=經度",
                "/restaurants?keyword=關鍵字&user_address=地址",
                "/api/keys/import - POST - 匯入 Gemini API 金鑰",
                "/api/keys/status - GET - 金鑰狀態",
                "/api/keys/usage - GET - 使用統計",
                "/health"
            ],
            "pages": [
                "/ - 主頁面",
                "/ai_lunch - AI智能午餐推薦頁面",
                "/settings - 設定頁面（金鑰管理）",
                "/sweat_index - 流汗指數查詢頁面",
                "/restaurant - 餐廳搜尋頁面",
                "/weather_page - 天氣查詢頁面"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # 檢查環境變數
    if not os.getenv("CWB_API_KEY"):
        print("警告：CWB_API_KEY 環境變數未設置，無法獲取真實天氣資料")
        print("請先設置中央氣象署 API 金鑰")
        print()

    print("AI 午餐推薦系統（整合流汗指數）啟動中...")
    print("可用頁面：")
    print("   • http://localhost:5000/ - 主頁面")
    print("   • http://localhost:5000/ai_lunch - AI智能午餐推薦介面")
    print("   • http://localhost:5000/settings - 設定頁面（金鑰管理）")
    print("   • http://localhost:5000/sweat_index - 流汗指數查詢介面")
    print("   • http://localhost:5000/restaurant - 餐廳搜尋介面")
    print("   • http://localhost:5000/weather_page - 天氣查詢介面")
    print("可用 API：")
    print("   • http://localhost:5000/sweat-index?location=台北101 - 流汗指數查詢")
    print("   • http://localhost:5000/weather_enhanced?location=花蓮市 - 增強版天氣查詢")
    print("   • http://localhost:5000/api/keys/status - Gemini 金鑰狀態")
    print("   • http://localhost:5000/health - 健康檢查")
    print()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
