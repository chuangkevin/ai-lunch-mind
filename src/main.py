"""
FastAPI 主應用程式
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uvicorn

from src.config import settings
from src.models import UserQuery, RecommendationResponse, UserLocation
from src.services.weather_service import weather_service
from src.services.google_maps_service import google_maps_service
from src.services.conversation_service import conversation_service
from src.services.recommendation_engine import recommendation_engine

# 建立 FastAPI 應用程式
app = FastAPI(
    title="AI 午餐推薦系統",
    description="根據天氣、預算、用餐偏好的智慧餐廳推薦系統",
    version="1.0.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生產環境應設定具體網域
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """API 根路徑"""
    return {
        "message": "AI 午餐推薦系統 API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "healthy", "timestamp": "2025-07-08"}

@app.post("/recommend", response_model=RecommendationResponse)
async def get_recommendations(query: UserQuery):
    """取得餐廳推薦
    
    根據使用者查詢條件，整合天氣、位置、偏好等因素，
    提供個人化的餐廳推薦清單。
    """
    try:
        # 1. 解析使用者查詢
        parsed_preferences = await conversation_service.parse_user_query(query.text)
        
        # 2. 取得天氣資訊
        weather = await weather_service.get_current_weather(query.location)
        if not weather:
            raise HTTPException(status_code=500, detail="無法取得天氣資訊")
        
        # 3. 搜尋附近餐廳
        restaurants = await google_maps_service.search_nearby_restaurants(query.location)
        if not restaurants:
            raise HTTPException(status_code=404, detail="附近沒有找到餐廳")
        
        # 4. 產生推薦
        recommendations = await recommendation_engine.generate_recommendations(
            restaurants=restaurants,
            user_location=query.location,
            weather=weather,
            user_preferences=parsed_preferences
        )
        
        # 5. 產生推薦說明
        explanation = await conversation_service.generate_recommendation_explanation(
            user_query=query.text,
            weather_info=f"溫度{weather.temperature}°C, 濕度{weather.humidity}%, {weather.description}",
            recommendations=[{
                "restaurant": {"name": rec.restaurant.name},
                "reasons": rec.reasons,
                "distance": rec.distance
            } for rec in recommendations]
        )
        
        return RecommendationResponse(
            recommendations=recommendations,
            explanation=explanation,
            weather_info=weather,
            total_count=len(recommendations)
        )
        
    except Exception as e:
        print(f"推薦產生錯誤: {e}")
        raise HTTPException(status_code=500, detail="推薦系統發生錯誤")

@app.get("/restaurants/search")
async def search_restaurants(lat: float, lng: float, radius: int = 500):
    """搜尋附近餐廳"""
    try:
        location = UserLocation(latitude=lat, longitude=lng)
        restaurants = await google_maps_service.search_nearby_restaurants(location, radius)
        return {"restaurants": restaurants, "count": len(restaurants)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"餐廳搜尋失敗: {str(e)}")

@app.get("/weather")
async def get_weather(lat: float, lng: float):
    """取得天氣資訊"""
    try:
        location = UserLocation(latitude=lat, longitude=lng)
        weather = await weather_service.get_current_weather(location)
        if not weather:
            raise HTTPException(status_code=500, detail="無法取得天氣資訊")
        return weather
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"天氣資訊取得失敗: {str(e)}")

@app.post("/analyze/query")
async def analyze_query(text: str):
    """分析使用者查詢"""
    try:
        parsed = await conversation_service.parse_user_query(text)
        return {"analysis": parsed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查詢分析失敗: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
