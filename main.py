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
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

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
    return FileResponse(os.path.join(STATIC_DIR, "ai_lunch_v2.html"))

@app.get("/ai_lunch", response_class=HTMLResponse)
def ai_lunch_page():
    """Backward-compatible redirect"""
    return FileResponse(os.path.join(STATIC_DIR, "ai_lunch_v2.html"))

@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
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




# ---------------------------------------------------------------------------
# SSE Streaming Recommendation Endpoint
# ---------------------------------------------------------------------------

@app.get("/chat-recommendation-stream")
async def chat_recommendation_stream(message: str = None, lat: float = None, lng: float = None):
    """SSE streaming endpoint for real-time recommendation progress."""
    if not message:
        raise HTTPException(status_code=400, detail="Missing message")
    user_coords = (lat, lng) if lat is not None and lng is not None else None

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

            # Intent (20s timeout — Gemini can hang if API is slow or keys exhausted)
            try:
                intent = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: analyze_intent(
                            user_input=message,
                            weather_data=weather_data,
                            current_hour=current_hour,
                        ),
                    ),
                    timeout=20,
                )
            except asyncio.TimeoutError:
                yield send_event("thinking", {"step": "intent", "message": "意圖分析超時，使用快速模式"})
                from modules.ai.intent_analyzer import _fallback_analysis
                intent = _fallback_analysis(message, weather_data, current_hour)

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

            # ONLY use Google Maps (Selenium) for real restaurant data.
            # NEVER use Gemini to generate restaurants — it hallucinates.

            search_kws = keywords[:3]

            yield send_event("thinking", {"step": "search", "message": f"Google Maps + Uber Eats 搜尋中（{len(search_kws)} 個關鍵字並行）..."})

            # Geocode search_location for Uber Eats (needs lat/lng)
            ue_lat, ue_lng = None, None
            try:
                from geopy.geocoders import ArcGIS
                _geolocator = ArcGIS(timeout=5)
                for _variant in [search_location, search_location + " 台灣", search_location + " Taiwan"]:
                    _geo_result = _geolocator.geocode(_variant)
                    if _geo_result:
                        ue_lat, ue_lng = _geo_result.latitude, _geo_result.longitude
                        break
            except Exception as e:
                logger.warning("ArcGIS geocode for Uber Eats failed: %s", e)

            # Parallel Selenium searches + Uber Eats with longer timeout (30s)
            ue_worker_count = 1 if ue_lat is not None else 0
            selenium_pool = ThreadPoolExecutor(max_workers=min(3, len(search_kws)) + ue_worker_count)

            # Submit Google Maps futures
            selenium_futures = {
                selenium_pool.submit(search_restaurants_fast, kw, search_location, 8): kw
                for kw in search_kws
            }

            # Submit Uber Eats future in parallel (if geocoding succeeded)
            ue_future = None
            if ue_lat is not None and ue_lng is not None:
                from modules.scraper.ubereats import search_ubereats, match_ubereats_to_restaurants
                ue_keyword = keywords[0] if keywords else ""
                ue_future = selenium_pool.submit(
                    search_ubereats, ue_keyword, ue_lat, ue_lng, search_location, 20
                )

            seen_names = set()
            ubereats_results = []
            try:
                for future in _as_completed(selenium_futures, timeout=30):
                    kw = selenium_futures[future]
                    try:
                        results = future.result(timeout=1)
                        for r in results:
                            name = r.get("name", "").strip()
                            if name and name not in seen_names:
                                seen_names.add(name)
                                r["food_type"] = kw
                                r["source"] = "google_maps"
                                all_restaurants.append(r)
                        # Stream progress as each keyword completes
                        yield send_event("thinking", {
                            "step": "search_progress",
                            "message": f"「{kw}」找到 {len(results)} 間（累計 {len(all_restaurants)} 間）",
                        })
                    except Exception as e:
                        logger.warning("Selenium search failed for '%s': %s", kw, e)
            except Exception:
                logger.warning("Some Selenium searches timed out")

            # Collect Uber Eats results (non-blocking — if not done yet, wait up to 5s)
            if ue_future is not None:
                try:
                    ubereats_results = ue_future.result(timeout=5)
                    if ubereats_results:
                        yield send_event("thinking", {
                            "step": "ubereats_done",
                            "message": f"Uber Eats 找到 {len(ubereats_results)} 間外送餐廳",
                        })
                except Exception as e:
                    logger.warning("Uber Eats search failed: %s", e)

            selenium_pool.shutdown(wait=False)

            # Merge Uber Eats data into Google Maps results
            if ubereats_results and all_restaurants:
                try:
                    all_restaurants = match_ubereats_to_restaurants(all_restaurants, ubereats_results)
                    ue_matched = sum(1 for r in all_restaurants if r.get("uber_eats_url"))
                    if ue_matched > 0:
                        yield send_event("thinking", {
                            "step": "ubereats_merged",
                            "message": f"{ue_matched} 間餐廳支援 Uber Eats 外送",
                        })
                except Exception as e:
                    logger.warning("Uber Eats merge failed: %s", e)

            # Fallback: if Google Maps found nothing, use Uber Eats results directly
            if not all_restaurants and ubereats_results:
                # Filter out non-restaurant stores (supermarkets, convenience stores, etc.)
                _NON_RESTAURANT = ["百貨", "超市", "便利", "7-ELEVEN", "全家", "萊爾富",
                                   "OK超商", "家樂福", "全聯", "小北", "寶雅", "屈臣氏",
                                   "康是美", "大潤發", "好市多", "Costco", "美廉社"]
                filtered_ue = [
                    r for r in ubereats_results
                    if not any(ex in r.get("name", "") for ex in _NON_RESTAURANT)
                ]
                if not filtered_ue:
                    filtered_ue = ubereats_results  # fallback to all if nothing left

                yield send_event("thinking", {
                    "step": "ubereats_fallback",
                    "message": f"Google Maps 無結果，改用 Uber Eats {len(filtered_ue)} 間餐廳",
                })
                for ue_r in filtered_ue:
                    ue_r.setdefault("address", "")
                    ue_r.setdefault("maps_url", f"https://www.google.com/maps/search/{quote(ue_r.get('name', ''))}+{quote(search_location)}")
                    ue_r.setdefault("food_type", keywords[0] if keywords else "")
                    ue_r.setdefault("source", "uber_eats")
                    ue_r.setdefault("social_proof", None)
                    ue_r.setdefault("relevance_score", 7.0)
                    ue_r.setdefault("estimated_price", None)
                    ue_r.setdefault("price_level", None)
                    ue_r.setdefault("distance_km", None)
                all_restaurants = filtered_ue

            ue_fallback = any(r.get("source") == "uber_eats" for r in all_restaurants)
            source_label = "Uber Eats" if ue_fallback and not any(r.get("source") == "google_maps" for r in all_restaurants) else "Google Maps"
            yield send_event("thinking", {
                "step": "search_done",
                "message": f"共找到 {len(all_restaurants)} 間餐廳（{source_label}）",
            })

            # Enrich with Gemini (ONLY add reasons to existing restaurants, never add new ones)
            if all_restaurants:
                yield send_event("thinking", {"step": "enrich", "message": "AI 補充推薦理由..."})
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
                        lambda: calculate_real_distances(all_restaurants, search_location, user_coords=user_coords),
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

                # Sort: open first, then distance (nearest), then social proof, then rating
                all_restaurants.sort(
                    key=lambda r: (
                        0 if r.get("open_now") is True else (1 if r.get("open_now") is None else 2),
                        r.get("distance_km") if r.get("distance_km") is not None else 999,
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
            "service": "AI Lunch Mind",
            "version": "5.1.0",
            "cwb_api_key": api_key_status,
            "gemini_keys": gemini_key_count,
            "endpoints": [
                "/chat-recommendation-stream?message=訊息 - SSE 串流推薦",
                "/api/keys/* - Gemini 金鑰管理",
                "/health"
            ],
            "pages": [
                "/ - AI 午餐推薦",
                "/settings - 設定（金鑰管理）"
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

    print("AI Lunch Mind 啟動中...")
    print("   • http://localhost:5000/ - AI 午餐推薦")
    print("   • http://localhost:5000/settings - 設定（金鑰管理）")
    print("   • http://localhost:5000/health - 健康檢查")
    print()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
