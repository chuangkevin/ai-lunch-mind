#!/usr/bin/env python3
"""
簡化的推薦系統測試
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.models import UserLocation, WeatherCondition, Restaurant, UserPreferences, PriceLevel, CrowdLevel
from src.services.recommendation_engine import recommendation_engine

async def test_direct_recommendation():
    """直接測試推薦系統"""
    print("=== 直接測試推薦引擎 ===\n")
    
    # 創建測試資料
    location = UserLocation(
        latitude=25.0330,
        longitude=121.5654,
        address="台北市信義區"
    )
    
    weather = WeatherCondition(
        temperature=22.5,
        humidity=65,
        rain_probability=10.0,
        wind_speed=3.2,
        description="晴朗"
    )
    
    restaurants = [
        Restaurant(
            place_id="demo_1",
            name="測試餐廳 A",
            address="台北市信義區測試路1號",
            phone="02-1234-5678",
            rating=4.5,
            price_level="moderate",
            cuisine_type=["中式料理"],
            latitude=location.latitude + 0.001,
            longitude=location.longitude + 0.001,
            distance=100.0,
            opening_hours={"monday": "11:00-21:00"}
        ),
        Restaurant(
            place_id="demo_2",
            name="測試餐廳 B",
            address="台北市信義區測試路2號",
            phone="02-2345-6789",
            rating=4.2,
            price_level="expensive",
            cuisine_type=["日式料理"],
            latitude=location.latitude - 0.001,
            longitude=location.longitude - 0.001,
            distance=150.0,
            opening_hours={"monday": "12:00-22:00"}
        )
    ]
    
    # 使用字典形式的偏好（模擬對話服務的輸出）
    preferences_dict = {
        "budget": "moderate",
        "cuisine_preferences": ["中式", "日式"],
        "crowd_preference": "moderate",
        "weather_sensitive": True
    }
    
    try:
        print("呼叫推薦引擎...")
        recommendations = await recommendation_engine.generate_recommendations(
            restaurants=restaurants,
            user_location=location,
            weather=weather,
            user_preferences=preferences_dict
        )
        
        print(f"成功！得到 {len(recommendations)} 個推薦")
        for i, rec in enumerate(recommendations, 1):
            print(f"{i}. {rec.restaurant.name}")
            print(f"   分數: {rec.score:.2f}")
            print(f"   理由: {', '.join(rec.reasons)}")
            print()
            
    except Exception as e:
        print(f"錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_recommendation())
