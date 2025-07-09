"""
天氣服務模組
整合 OpenWeatherMap API
"""
import httpx
from typing import Optional
from src.config import settings
from src.models import WeatherCondition, UserLocation

class WeatherService:
    """天氣服務"""
    
    def __init__(self):
        self.api_key = settings.openweather_api_key
        self.base_url = "http://api.openweathermap.org/data/2.5"
    
    async def get_current_weather(self, location: UserLocation) -> Optional[WeatherCondition]:
        """取得當前天氣"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/weather",
                    params={
                        "lat": location.latitude,
                        "lon": location.longitude,
                        "appid": self.api_key,
                        "units": "metric",
                        "lang": "zh_tw"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                return WeatherCondition(
                    temperature=data["main"]["temp"],
                    humidity=data["main"]["humidity"],
                    rain_probability=data.get("rain", {}).get("1h", 0) * 100,
                    wind_speed=data["wind"]["speed"],
                    description=data["weather"][0]["description"]
                )
        except Exception as e:
            print(f"天氣資料取得失敗: {e}")
            return None
    
    def calculate_sweat_index(self, weather: WeatherCondition, distance: float) -> float:
        """計算流汗指數 (0-10)"""
        # 基礎溫度影響
        temp_factor = min(weather.temperature / 35.0, 1.0) * 4
        
        # 濕度影響
        humidity_factor = weather.humidity / 100.0 * 3
        
        # 距離影響 (步行時間)
        walk_time = distance / 80  # 假設每分鐘走80公尺
        distance_factor = min(walk_time / 10, 1.0) * 2
        
        # 風速減緩效果
        wind_reduction = min(weather.wind_speed / 5.0, 1.0) * 0.5
        
        sweat_score = temp_factor + humidity_factor + distance_factor - wind_reduction
        return max(0, min(10, sweat_score))

# 全域天氣服務實例
weather_service = WeatherService()
