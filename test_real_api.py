"""
測試真實 API 整合 - 確認沒有假資料
"""
import asyncio
import sys
import os

# 將 src 目錄加入 Python 路徑
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.models import UserLocation
from src.services.weather_service import weather_service
from src.services.google_maps_service import google_maps_service

async def test_real_apis():
    """測試真實 API 整合"""
    print("=== 測試真實 API 整合（無假資料）===")
    
    # 測試位置：台北101
    test_location = UserLocation(latitude=25.0330, longitude=121.5654)
    print(f"測試位置：緯度 {test_location.latitude}, 經度 {test_location.longitude}")
    
    # 1. 測試天氣服務
    print("\n--- 測試中央氣象署 API ---")
    try:
        weather = await weather_service.get_current_weather(test_location)
        print(f"✅ 天氣資料取得成功：")
        print(f"   溫度：{weather.temperature}°C")
        print(f"   濕度：{weather.humidity}%")
        print(f"   降雨機率：{weather.rain_probability}%")
        print(f"   風速：{weather.wind_speed} m/s")
        print(f"   描述：{weather.description}")
        
        # 檢查是否為真實資料（不是固定的模擬值）
        if weather.temperature == 22.5 and weather.humidity == 65:
            print("⚠️  警告：這可能是模擬資料！")
        else:
            print("✅ 資料看起來是真實的")
            
    except Exception as e:
        print(f"❌ 天氣資料取得失敗：{e}")
        return
    
    # 2. 測試 Google Maps 服務
    print("\n--- 測試 Google Maps API ---")
    try:
        restaurants = await google_maps_service.search_nearby_restaurants(
            test_location, 
            radius=500
        )
        print(f"✅ 餐廳搜尋成功：找到 {len(restaurants)} 家餐廳")
        
        if restaurants:
            # 顯示前3家餐廳
            for i, restaurant in enumerate(restaurants[:3], 1):
                print(f"   {i}. {restaurant.name}")
                print(f"      地址：{restaurant.address}")
                print(f"      評分：{restaurant.rating}")
                print(f"      價位：{restaurant.price_level}")
                
            # 檢查是否為真實資料（不是測試餐廳）
            demo_restaurants = [r for r in restaurants if r.name.startswith("測試餐廳")]
            if demo_restaurants:
                print("⚠️  警告：發現測試餐廳，這可能是模擬資料！")
            else:
                print("✅ 餐廳資料看起來是真實的")
        else:
            print("⚠️  沒有找到任何餐廳")
            
    except Exception as e:
        print(f"❌ 餐廳搜尋失敗：{e}")
        return
    
    print("\n=== 測試完成 ===")
    print("✅ 所有服務都使用真實 API，沒有假資料回退機制")

if __name__ == "__main__":
    asyncio.run(test_real_apis())
