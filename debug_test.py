#!/usr/bin/env python3
"""
直接測試推薦系統組件
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.models import UserQuery, UserLocation
from src.services.weather_service import weather_service
from src.services.google_maps_service import google_maps_service
from src.services.conversation_service import conversation_service
from src.services.recommendation_engine import recommendation_engine

async def test_components():
    """測試各個組件"""
    print("=== 測試各組件 ===\n")
    
    # 1. 測試天氣服務
    print("1. 測試天氣服務...")
    try:
        location = UserLocation(
            latitude=25.0330,
            longitude=121.5654,
            address="台北市信義區"
        )
        weather = await weather_service.get_current_weather(location)
        print(f"   天氣: {weather.temperature}°C, {weather.description}")
        print("   ✓ 天氣服務正常")
    except Exception as e:
        print(f"   ✗ 天氣服務錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 2. 測試地圖服務
    print("2. 測試地圖服務...")
    try:
        restaurants = await google_maps_service.search_nearby_restaurants(location)
        print(f"   找到 {len(restaurants)} 間餐廳")
        if restaurants:
            print(f"   第一間: {restaurants[0].name}")
        print("   ✓ 地圖服務正常")
    except Exception as e:
        print(f"   ✗ 地圖服務錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 3. 測試對話服務
    print("3. 測試對話服務...")
    try:
        parsed = await conversation_service.parse_user_query("我想找附近好吃的中式餐廳")
        print(f"   解析結果: {parsed}")
        print("   ✓ 對話服務正常")
    except Exception as e:
        print(f"   ✗ 對話服務錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    
    # 4. 測試推薦引擎
    print("4. 測試推薦引擎...")
    try:
        from src.models import UserPreferences, PriceLevel, CrowdLevel
        preferences = UserPreferences(
            budget_range=[PriceLevel.MODERATE],
            cuisine_types=["中式"],
            crowd_preference=CrowdLevel.MODERATE
        )
        
        recommendations = await recommendation_engine.generate_recommendations(
            restaurants=restaurants,  # 使用前面得到的餐廳列表
            user_location=location,
            weather=weather,
            user_preferences=preferences
        )
        print(f"   推薦 {len(recommendations)} 間餐廳")
        if recommendations:
            print(f"   推薦: {recommendations[0].restaurant.name}")
        print("   ✓ 推薦引擎正常")
    except Exception as e:
        print(f"   ✗ 推薦引擎錯誤: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== 測試完成 ===")

if __name__ == "__main__":
    asyncio.run(test_components())
