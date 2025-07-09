"""
測試中央氣象署天氣服務
"""
import asyncio
import sys
import os

# 添加 src 目錄到 Python 路徑
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.weather_service import weather_service
from models import UserLocation

async def test_weather_service():
    """測試天氣服務"""
    print("=== 測試中央氣象署天氣服務 ===")
    
    # 測試地點：台北市政府
    location = UserLocation(
        latitude=25.0375,
        longitude=121.5647,
        address="台北市信義區市府路1號"
    )
    
    print(f"測試地點: {location.address}")
    print(f"座標: ({location.latitude}, {location.longitude})")
    print()
    
    try:
        # 取得天氣資料
        weather = await weather_service.get_current_weather(location)
        
        if weather:
            print("✅ 天氣資料取得成功！")
            print(f"溫度: {weather.temperature}°C")
            print(f"濕度: {weather.humidity}%")
            print(f"降雨機率: {weather.rain_probability}%")
            print(f"風速: {weather.wind_speed} m/s")
            print(f"天氣描述: {weather.description}")
            
            # 測試流汗指數計算
            sweat_index = weather_service.calculate_sweat_index(weather, 300)  # 300公尺距離
            print(f"流汗指數 (300公尺步行): {sweat_index:.1f}/10")
            
        else:
            print("❌ 天氣資料取得失敗")
            
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_weather_service())
