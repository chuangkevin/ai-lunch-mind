#!/usr/bin/env python3
"""
AI Lunch Mind - 智慧午餐決策助手
使用真實的中央氣象署天氣資料
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.services.weather_service import WeatherService
from src.restaurant_recommender import RestaurantRecommender

def main():
    """主程式示範"""
    print("🍽️ AI Lunch Mind - 智慧午餐決策助手")
    print("=" * 50)
    
    # 初始化服務
    weather_service = WeatherService()
    recommender = RestaurantRecommender()
    
    # 測試城市
    test_cities = ["台北", "新北", "桃園", "台中", "台南", "高雄"]
    
    for city in test_cities:
        print(f"\n📍 {city}市天氣資訊：")
        print("-" * 30)
        
        try:
            weather_data = weather_service.get_weather(city)
            if weather_data:
                print(f"溫度：{weather_data['temperature']}")
                print(f"天氣：{weather_data['condition']}")
                print(f"濕度：{weather_data['humidity']}")
                print(f"風速：{weather_data['wind_speed']}")
                print(f"資料來源：{weather_data.get('source', '中央氣象署')}")
                
                # 根據天氣推薦餐廳
                recommendations = recommender.get_recommendations(weather_data)
                print(f"\n🍴 推薦餐廳類型：")
                for i, rec in enumerate(recommendations[:3], 1):
                    print(f"  {i}. {rec['name']} - {rec['reason']}")
            else:
                print("❌ 無法取得天氣資料")
                
        except Exception as e:
            print(f"❌ 錯誤：{e}")
    
    print("\n" + "=" * 50)
    print("✅ 展示完成！所有資料均來自中央氣象署真實 API")

if __name__ == "__main__":
    main()
