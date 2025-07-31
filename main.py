# 主程式入口

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from modules.weather import get_weather_data
from modules.google_maps import search_restaurants, geocode_address_with_options
from modules.sweat_index import query_sweat_index_by_location, get_sweat_risk_alerts
from modules.sweat_index import get_location_coordinates, get_real_weather_data
from modules.ai_recommendation_engine import SmartRecommendationEngine, get_ai_lunch_recommendation

# 創建全域 AI 推薦引擎實例（支援對話記憶）
ai_engine = SmartRecommendationEngine()


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
    return FileResponse(os.path.join(STATIC_DIR, "ai_lunch.html"))


# API 路由
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


# AI 午餐推薦主功能 API 端點
@app.get("/ai-lunch-recommendation")
def ai_lunch_recommendation_endpoint(location: str = None, user_input: str = "", max_results: int = 10):
    """
    AI 午餐推薦主功能 API 端點
    :param location: 位置資訊（地址、地標、經緯度）
    :param user_input: 使用者自然語言輸入（可選）
    :param max_results: 最大推薦結果數量
    :return: 智能餐廳推薦結果
    """
    try:
        if not location:
            raise HTTPException(status_code=400, detail="請提供位置資訊（location 參數）")
        
        # 限制最大結果數量
        max_results = min(max_results, 20)
        
        print(f"[AI推薦] 位置: {location}, 使用者輸入: '{user_input}', 最大結果: {max_results}")
        
        # 調用 AI 推薦引擎
        recommendation_result = ai_engine.generate_recommendation(
            location=location,
            user_input=user_input,
            max_results=max_results
        )
        
        # 檢查是否有錯誤
        if 'error' in recommendation_result:
            raise HTTPException(
                status_code=500, 
                detail=recommendation_result.get('message', '推薦生成失敗')
            )
        
        return recommendation_result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] AI 午餐推薦失敗: {e}")
        raise HTTPException(status_code=500, detail=f"推薦失敗: {str(e)}")


# 對話式推薦 API 端點（支援位置自動解析）
@app.get("/chat-recommendation")
def chat_recommendation_endpoint(message: str = None, phase: str = "start"):
    """
    對話式餐廳推薦 API 端點（分階段執行）
    :param message: 完整的使用者輸入訊息
    :param phase: 執行階段 ("start" 回傳搜尋計劃, "search" 執行實際搜尋)
    :return: 分階段的推薦結果
    """
    try:
        if not message:
            raise HTTPException(status_code=400, detail="請提供使用者訊息（message 參數）")
        
        print(f"[對話推薦] 使用者訊息: '{message}', 階段: {phase}")
        
        # 根據階段執行對應操作
        if phase == "start":
            # 第一階段：只生成搜尋計劃
            result = ai_engine.process_conversation(message, phase="start")
            if result.get("phase") == "plan":
                # 返回搜尋計劃，讓前端先顯示
                return {
                    "phase": "plan",
                    "success": True,
                    "location": result.get("location"),
                    "search_plan": result.get("search_plan"),
                    "weather_info": result.get("weather_info"),
                    "search_keywords": result.get("search_keywords"),
                    "message": "搜尋計劃已生成",
                    "timestamp": result.get("timestamp")
                }
            else:
                return result
        
        elif phase == "search":
            # 第二階段：執行實際餐廳搜尋
            result = ai_engine.process_conversation(message, phase="search")
            return result
        
        else:
            raise HTTPException(status_code=400, detail="phase 參數必須是 'start' 或 'search'")
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 對話式推薦失敗: {e}")
        raise HTTPException(status_code=500, detail=f"推薦失敗: {str(e)}")


# 分階段對話式推薦 API 端點（POST 版本，支援 JSON 請求體）
@app.post("/chat/recommend")
def staged_chat_recommendation(request: Request):
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
    import asyncio
    
    async def handle_request():
        try:
            # 解析 JSON 請求體
            body = await request.json()
            message = body.get("message")
            phase = body.get("phase", "start")
            
            if not message:
                raise HTTPException(status_code=400, detail="請提供使用者訊息（message 參數）")
            
            print(f"[分階段推薦] 階段: {phase}, 訊息: '{message}'")
            
            # 使用 AI 推薦引擎處理對話（分階段）
            result = ai_engine.process_conversation(message, phase=phase)
            
            # 根據階段決定回應內容
            if phase == "start":
                response_text = result.get("search_plan", "搜尋計劃生成中...")
            else:
                response_text = result.get("recommendation_summary", "推薦結果處理中...")
            
            return {
                "status": "success",
                "phase": phase,
                "response": response_text,
                "recommendations": result.get("restaurants", []),
                "data": result,
                "timestamp": result.get("timestamp")
            }
            
        except HTTPException:
            raise
        except Exception as e:
            print(f"[API ERROR] 分階段推薦失敗: {e}")
            raise HTTPException(status_code=500, detail=f"推薦失敗: {str(e)}")
    
    return asyncio.run(handle_request())


# 健康檢查 API 端點
@app.get("/health")
def health_check():
    """
    系統健康檢查
    """
    try:
        # 檢查環境變數
        api_key_status = "已設置" if os.getenv("CWB_API_KEY") else "未設置"
        
        return {
            "status": "healthy",
            "service": "AI 午餐推薦系統（整合流汗指數）",
            "version": "3.0.0",
            "cwb_api_key": api_key_status,
            "endpoints": [
                "/ai-lunch-recommendation?location=地點&user_input=需求 - 🤖 AI智能推薦",
                "/chat-recommendation?message=完整訊息 - 💬 對話式推薦",
                "/sweat-index?location=地點名稱",
                "/sweat-alerts?temperature=溫度&humidity=濕度",
                "/weather_enhanced?location=地點名稱",
                "/weather?latitude=緯度&longitude=經度",
                "/restaurants?keyword=關鍵字&user_address=地址",
                "/health"
            ],
            "pages": [
                "/ - 主頁面",
                "/ai_lunch - 🤖 AI智能午餐推薦頁面",
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
        print("⚠️  警告：CWB_API_KEY 環境變數未設置，無法獲取真實天氣資料")
        print("請先設置中央氣象署 API 金鑰")
        print()
    
    print("🌡️ AI 午餐推薦系統（整合流汗指數）啟動中...")
    print("📍 可用頁面：")
    print("   • http://localhost:5000/ - 主頁面")
    print("   • http://localhost:5000/sweat_index - 流汗指數查詢介面") 
    print("   • http://localhost:5000/restaurant - 餐廳搜尋介面")
    print("   • http://localhost:5000/weather_page - 天氣查詢介面")
    print("📍 可用 API：")
    print("   • http://localhost:5000/sweat-index?location=台北101 - 流汗指數查詢")
    print("   • http://localhost:5000/weather_enhanced?location=花蓮市 - 增強版天氣查詢")
    print("   • http://localhost:5000/health - 健康檢查")
    print()
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
