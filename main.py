# 主程式入口

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from modules.weather import get_weather_data
from modules.google_maps import search_restaurants
from modules.sweat_index import query_sweat_index_by_location, get_sweat_risk_alerts
from modules.sweat_index import get_location_coordinates, get_real_weather_data


app = FastAPI(title="AI 午餐推薦系統", description="整合天氣查詢與餐廳推薦的智慧系統")

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
                "rain_probability": weather_data.get('rain_probability', {}),
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
            "rain_probability": weather_data.get('rain_probability', {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[API ERROR] 增強版天氣查詢失敗: {e}")
        raise HTTPException(status_code=500, detail=f"查詢失敗: {str(e)}")


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
            "version": "2.0.0",
            "cwb_api_key": api_key_status,
            "endpoints": [
                "/sweat-index?location=地點名稱",
                "/sweat-alerts?temperature=溫度&humidity=濕度",
                "/weather_enhanced?location=地點名稱",
                "/weather?latitude=緯度&longitude=經度",
                "/restaurants?keyword=關鍵字&user_address=地址",
                "/health"
            ],
            "pages": [
                "/ - 主頁面",
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
