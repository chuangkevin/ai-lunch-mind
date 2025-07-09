#!/usr/bin/env python3
"""
測試中央氣象署天氣服務
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.models import UserLocation
from src.services.weather_service import WeatherService

async def test_cwb_weather():
    """測試中央氣象署天氣服務"""
    print("=== 測試中央氣象署天氣服務 ===\n")
    
    weather_service = WeatherService()
    
    # 測試幾個台灣的地點
    test_locations = [
        UserLocation(latitude=25.0330, longitude=121.5654, address="台北市信義區"),
        UserLocation(latitude=22.6273, longitude=120.3014, address="高雄市"),
        UserLocation(latitude=24.1477, longitude=120.6736, address="台中市"),
        UserLocation(latitude=25.0408, longitude=121.5674, address="台北101")
    ]
    
    for location in test_locations:
        print(f"測試地點: {location.address}")
        print(f"座標: ({location.latitude}, {location.longitude})")
        
        try:
            weather = await weather_service.get_current_weather(location)
            if weather:
                print(f"  溫度: {weather.temperature}°C")
                print(f"  濕度: {weather.humidity}%")
                print(f"  降雨機率: {weather.rain_probability}%")
                print(f"  風速: {weather.wind_speed} m/s")
                print(f"  天氣狀況: {weather.description}")
                print("  ✓ 成功取得天氣資料")
            else:
                print("  ✗ 無法取得天氣資料")
        except Exception as e:
            print(f"  ✗ 錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        print()

if __name__ == "__main__":
    asyncio.run(test_cwb_weather())
