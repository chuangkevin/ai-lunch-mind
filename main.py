# 主程式入口

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
from modules.weather import get_weather_data
from modules.google_maps import search_restaurants


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
    if latitude is not None and longitude is not None:
        return get_weather_data(latitude, longitude)
    # 可擴充：支援地名查詢
    return {"error": "請提供座標或城市名稱。"}

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
