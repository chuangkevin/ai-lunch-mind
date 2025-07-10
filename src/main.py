"""
FastAPI 主應用程式
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uvicorn

from src.config import settings
from src.models import UserQuery, RecommendationResponse, UserLocation, CrowdLevel
from src.services.weather_service import weather_service
from src.services.google_search_service import google_search_service
from src.services.conversation_service import conversation_service
from src.services.recommendation_engine import recommendation_engine
from src.services.crowd_analysis_service import crowd_analysis_service

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
        
        # 如果對話解析失敗，使用默認偏好
        if not parsed_preferences:
            from src.models import UserPreferences, PriceLevel, CrowdLevel
            parsed_preferences = UserPreferences(
                budget_range=[PriceLevel.MODERATE],
                cuisine_types=["中式", "日式", "韓式"],
                crowd_preference=CrowdLevel.MODERATE,
                weather_sensitive=True,
                distance_tolerance=500,
                dietary_restrictions=[]
            )
        
        # 2. 取得天氣資訊
        weather = await weather_service.get_current_weather(query.location)
        
        # 3. 搜尋附近餐廳
        restaurants = await google_search_service.search_nearby_restaurants(query.location)
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"推薦系統發生錯誤: {str(e)}")

@app.get("/restaurants/search")
async def search_restaurants(lat: float, lng: float, radius: int = 500):
    """搜尋附近餐廳"""
    try:
        location = UserLocation(latitude=lat, longitude=lng)
        restaurants = await google_search_service.search_nearby_restaurants(location, radius)
        return {"restaurants": restaurants, "count": len(restaurants)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"餐廳搜尋失敗: {str(e)}")

@app.get("/weather")
async def get_weather(lat: float, lng: float):
    """取得天氣資訊"""
    try:
        location = UserLocation(latitude=lat, longitude=lng)
        weather = await weather_service.get_current_weather(location)
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

@app.get("/crowd/analysis")
async def analyze_crowd(lat: float, lng: float, place_id: str = None):
    """分析特定餐廳的人潮狀況"""
    try:
        location = UserLocation(latitude=lat, longitude=lng)
        weather = await weather_service.get_current_weather(location)
        
        if place_id:
            # 如果有特定餐廳 ID，分析該餐廳
            restaurants = await google_search_service.search_nearby_restaurants(location)
            target_restaurant = next((r for r in restaurants if r.place_id == place_id), None)
            
            if not target_restaurant:
                raise HTTPException(status_code=404, detail="餐廳不存在")
            
            crowd_level, confidence, reason = crowd_analysis_service.estimate_crowd_level(
                target_restaurant, weather
            )
            
            # 人潮趨勢預測
            trend_prediction = crowd_analysis_service.get_crowd_trend_prediction(
                target_restaurant, weather
            )
            
            # 最佳造訪時間建議
            best_times = crowd_analysis_service.get_best_visit_times(
                target_restaurant, weather
            )
            
            return {
                "restaurant": {
                    "name": target_restaurant.name,
                    "place_id": target_restaurant.place_id,
                    "rating": target_restaurant.rating
                },
                "current_crowd": {
                    "level": crowd_level.value,
                    "confidence": confidence,
                    "reason": reason
                },
                "trend_prediction": {
                    time: level.value for time, level in trend_prediction.items()
                },
                "best_visit_times": [
                    {"time": time, "crowd_level": level.value} 
                    for time, level in best_times
                ]
            }
        else:
            # 分析附近所有餐廳的人潮概況
            restaurants = await google_search_service.search_nearby_restaurants(location)
            crowd_analysis = []
            
            for restaurant in restaurants[:10]:  # 限制分析前10間
                crowd_level, confidence, reason = crowd_analysis_service.estimate_crowd_level(
                    restaurant, weather
                )
                
                crowd_analysis.append({
                    "restaurant": {
                        "name": restaurant.name,
                        "place_id": restaurant.place_id,
                        "rating": restaurant.rating,
                        "cuisine_type": restaurant.cuisine_type
                    },
                    "crowd": {
                        "level": crowd_level.value,
                        "confidence": confidence,
                        "reason": reason
                    }
                })
            
            return {
                "location": f"({lat:.4f}, {lng:.4f})",
                "weather_info": {
                    "temperature": weather.temperature,
                    "rain_probability": weather.rain_probability,
                    "description": weather.description
                },
                "restaurants_crowd_analysis": crowd_analysis
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"人潮分析失敗: {str(e)}")

@app.get("/crowd/quiet-restaurants")
async def get_quiet_restaurants(lat: float, lng: float):
    """取得附近人潮較少的餐廳推薦"""
    try:
        location = UserLocation(latitude=lat, longitude=lng)
        weather = await weather_service.get_current_weather(location)
        restaurants = await google_search_service.search_nearby_restaurants(location)
        
        quiet_restaurants = []
        
        for restaurant in restaurants:
            crowd_level, confidence, reason = crowd_analysis_service.estimate_crowd_level(
                restaurant, weather
            )
            
            # 只推薦人潮較少的餐廳
            if crowd_level in [CrowdLevel.QUIET, CrowdLevel.MODERATE]:
                quiet_restaurants.append({
                    "restaurant": {
                        "name": restaurant.name,
                        "place_id": restaurant.place_id,
                        "rating": restaurant.rating,
                        "cuisine_type": restaurant.cuisine_type,
                        "price_level": restaurant.price_level.value if restaurant.price_level else None
                    },
                    "crowd": {
                        "level": crowd_level.value,
                        "confidence": confidence,
                        "reason": reason
                    }
                })
        
        # 依人潮由少到多排序
        crowd_order = {
            "quiet": 0, "moderate": 1, "busy": 2, "very_busy": 3
        }
        quiet_restaurants.sort(key=lambda x: crowd_order[x["crowd"]["level"]])
        
        return {
            "total_found": len(quiet_restaurants),
            "quiet_restaurants": quiet_restaurants[:8]  # 返回前8間
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安靜餐廳搜尋失敗: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
