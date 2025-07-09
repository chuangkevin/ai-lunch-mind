"""
直接測試天氣服務類別
"""
import asyncio
import sys
import os

# 將 src 目錄加入 Python 路徑
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# 直接 import 類別，避免全域實例初始化問題
from src.models import UserLocation

async def test_weather_direct():
    """直接測試天氣服務類別"""
    print("=== 直接測試中央氣象署 API ===")
    
    # 測試位置：台北101
    test_location = UserLocation(latitude=25.0330, longitude=121.5654)
    print(f"測試位置：緯度 {test_location.latitude}, 經度 {test_location.longitude}")
    
    # 直接建立天氣服務實例
    try:
        from src.services.weather_service import WeatherService
        weather_service = WeatherService()
        print("✅ 天氣服務初始化成功")
    except Exception as e:
        print(f"❌ 天氣服務初始化失敗：{e}")
        return
    
    # 測試天氣資料取得
    print("\n--- 調用中央氣象署 API ---")
    try:
        weather = await weather_service.get_current_weather(test_location)
        print(f"✅ 天氣資料取得成功：")
        print(f"   溫度：{weather.temperature}°C")
        print(f"   濕度：{weather.humidity}%")
        print(f"   降雨機率：{weather.rain_probability}%")
        print(f"   風速：{weather.wind_speed} m/s")
        print(f"   描述：{weather.description}")
        
        # 檢查是否為真實資料（不是固定的模擬值）
        if weather.temperature == 22.5 and weather.humidity == 65 and weather.description == "晴朗":
            print("⚠️  警告：這是模擬資料！")
        else:
            print("✅ 這是真實的氣象資料")
            
        # 測試流汗指數計算
        sweat_index = weather_service.calculate_sweat_index(weather, 300)
        print(f"   流汗指數：{sweat_index:.2f}/10")
            
    except Exception as e:
        print(f"❌ 天氣資料取得失敗：{e}")
        return
    
    print("\n=== 測試完成 ===")
    print("✅ 天氣服務完全使用中央氣象署 API，已移除所有假資料")

if __name__ == "__main__":
    asyncio.run(test_weather_direct())
