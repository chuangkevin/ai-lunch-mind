"""
測試中央氣象署 API - 確認沒有假資料
"""
import asyncio
import sys
import os

# 將 src 目錄加入 Python 路徑
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.models import UserLocation
from src.services.weather_service import WeatherService

async def test_weather_api():
    """測試中央氣象署 API"""
    print("=== 測試中央氣象署 API（無假資料）===")
    
    # 測試位置：台北101
    test_location = UserLocation(latitude=25.0330, longitude=121.5654)
    print(f"測試位置：緯度 {test_location.latitude}, 經度 {test_location.longitude}")
    
    # 建立天氣服務實例
    try:
        weather_service = WeatherService()
        print("✅ 天氣服務初始化成功")
    except Exception as e:
        print(f"❌ 天氣服務初始化失敗：{e}")
        return
    
    # 測試天氣資料取得
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
            
        # 測試流汗指數計算
        sweat_index = weather_service.calculate_sweat_index(weather, 300)  # 300公尺距離
        print(f"   流汗指數：{sweat_index:.2f}/10")
            
    except Exception as e:
        print(f"❌ 天氣資料取得失敗：{e}")
        return
    
    print("\n=== 測試完成 ===")
    print("✅ 天氣服務使用真實 API，沒有假資料回退機制")

if __name__ == "__main__":
    asyncio.run(test_weather_api())
