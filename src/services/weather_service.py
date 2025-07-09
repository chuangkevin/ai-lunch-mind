"""
天氣服務模組
整合中央氣象署開放資料平台 API
"""
import httpx
from typing import Dict, List, Optional
from src.config import settings
from src.models import WeatherCondition, UserLocation
import math
import asyncio

class WeatherService:
    """天氣服務 - 使用中央氣象署 API"""
    
    def __init__(self):
        self.api_key = settings.cwb_api_key
        self.base_url = "https://opendata.cwa.gov.tw/api"
        
        if not self.api_key or not self.api_key.startswith("CWB-"):
            raise ValueError("中央氣象署 API Key 未設定或格式錯誤，請檢查 .env 檔案中的 CWB_API_KEY 設定")
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """計算兩點之間的距離（公里）"""
        R = 6371  # 地球半徑（公里）
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _has_valid_temperature(self, station: Dict) -> bool:
        """檢查氣象站是否有有效的溫度資料"""
        weather_elements = station.get("weatherElement", [])
        for element in weather_elements:
            if element.get("elementName") == "TEMP":
                temp_value = element.get("elementValue")
                if temp_value and temp_value != "-99" and temp_value != "":
                    try:
                        float(temp_value)
                        return True
                    except ValueError:
                        continue
        return False

    def _find_nearest_station(self, user_location: UserLocation, stations: List[Dict]) -> Optional[Dict]:
        """找到最近且有有效溫度資料的氣象站"""
        if not stations:
            return None
            
        # 先過濾出有有效溫度資料的氣象站
        valid_stations = []
        for station in stations:
            # 檢查氣象站是否有座標資料
            if 'lat' not in station or 'lon' not in station:
                continue
            
            # 檢查氣象站是否有有效溫度資料
            if not self._has_valid_temperature(station):
                continue
                
            valid_stations.append(station)
        
        if not valid_stations:
            print("警告：沒有找到有效的氣象站資料")
            return None
            
        print(f"找到 {len(valid_stations)} 個有效氣象站")
        
        # 在有效氣象站中找到最近的
        nearest_station = None
        min_distance = float('inf')
        
        for station in valid_stations:
            try:
                distance = self._calculate_distance(
                    user_location.latitude, user_location.longitude,
                    float(station['lat']), float(station['lon'])
                )
                print(f"氣象站 {station.get('locationName', '未知')}: 距離 {distance:.2f} 公里")
                
                if distance < min_distance:
                    min_distance = distance
                    nearest_station = station
            except (ValueError, TypeError) as e:
                print(f"氣象站座標資料有誤: {e}")
                continue
        
        if nearest_station:
            print(f"選擇氣象站: {nearest_station.get('locationName', '未知')}, 距離: {min_distance:.2f} 公里")
        
        return nearest_station
    
    async def get_current_weather(self, location: UserLocation) -> WeatherCondition:
        """取得當前天氣"""
        try:
            # 取得自動氣象站現況觀測資料
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/v1/rest/datastore/O-A0003-001"
                params = {
                    "Authorization": self.api_key,
                    "format": "JSON"
                }
                
                print(f"調用 API: {url}")
                print(f"參數: {params}")
                
                response = await client.get(url, params=params, timeout=30.0)
                print(f"回應狀態碼: {response.status_code}")
                
                response.raise_for_status()
                data = response.json()
                
                print(f"API 回應: {data.get('success')}")
                print(f"完整回應結構: {list(data.keys())}")
                
                if "records" in data:
                    records = data["records"]
                    print(f"Records 結構: {list(records.keys())}")
                    
                    if "location" in records:
                        locations = records["location"]
                        print(f"Location 數量: {len(locations)}")
                        if len(locations) > 0:
                            print(f"第一個 location 的 keys: {list(locations[0].keys())}")
                    else:
                        print("Records 中沒有 location 欄位")
                        print(f"Records 內容: {records}")
                
                if not data.get("success"):
                    print(f"錯誤訊息: {data}")
                    raise Exception(f"API 回應錯誤: {data.get('message', '未知錯誤')}")
                
                stations = data.get("records", {}).get("location", [])
                print(f"找到 {len(stations)} 個氣象站")
                
                if not stations:
                    raise Exception("無氣象站資料")
                
                # 找到最近的氣象站
                nearest_station = self._find_nearest_station(location, stations)
                if not nearest_station:
                    raise Exception("找不到最近的氣象站")
                
                print(f"使用氣象站: {nearest_station.get('locationName', '未知')}")
                
                # 解析天氣資料
                weather_elements = nearest_station.get("weatherElement", [])
                weather_data = {}
                
                for element in weather_elements:
                    element_name = element.get("elementName")
                    element_value = element.get("elementValue")
                    
                    if element_name == "TEMP":  # 溫度
                        if element_value and element_value != "-99":
                            try:
                                weather_data["temperature"] = float(element_value)
                            except ValueError:
                                weather_data["temperature"] = 22.0
                        else:
                            weather_data["temperature"] = 22.0
                    elif element_name == "HUMD":  # 濕度
                        if element_value and element_value != "-99":
                            try:
                                weather_data["humidity"] = float(element_value)
                            except ValueError:
                                weather_data["humidity"] = 60.0
                        else:
                            weather_data["humidity"] = 60.0
                    elif element_name == "WDSD":  # 風速
                        if element_value and element_value != "-99":
                            try:
                                weather_data["wind_speed"] = float(element_value)
                            except ValueError:
                                weather_data["wind_speed"] = 2.0
                        else:
                            weather_data["wind_speed"] = 2.0
                    elif element_name == "24R":  # 24小時累積雨量
                        if element_value and element_value != "-99":
                            try:
                                rain_24h = float(element_value)
                                # 簡單估算降雨機率：雨量越多機率越高
                                weather_data["rain_probability"] = min(rain_24h * 10, 100.0)
                            except ValueError:
                                weather_data["rain_probability"] = 10.0
                        else:
                            weather_data["rain_probability"] = 10.0
                
                # 設定預設值
                temperature = weather_data.get("temperature", 22.0)
                humidity = weather_data.get("humidity", 65.0)
                rain_probability = weather_data.get("rain_probability", 10.0)
                wind_speed = weather_data.get("wind_speed", 2.0)
                
                # 根據雨量和其他條件判斷天氣描述
                if rain_probability > 70:
                    description = "有雨"
                elif rain_probability > 30:
                    description = "多雲時陰"
                elif rain_probability > 10:
                    description = "多雲"
                else:
                    description = "晴朗"
                
                print(f"天氣資料：溫度={temperature}°C, 濕度={humidity}%, 降雨機率={rain_probability}%, 風速={wind_speed}m/s, 描述={description}")
                
                return WeatherCondition(
                    temperature=temperature,
                    humidity=humidity,
                    rain_probability=rain_probability,
                    wind_speed=wind_speed,
                    description=description
                )
                
        except Exception as e:
            print(f"中央氣象署天氣資料取得失敗: {e}")
            raise Exception(f"無法取得天氣資料: {e}")
    
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
    
    # 台灣主要城市座標
    CITY_COORDINATES = {
        "台北": (25.0330, 121.5654),
        "新北": (25.0120, 121.4654),
        "桃園": (24.9937, 121.2654),
        "台中": (24.1477, 120.6736),
        "台南": (22.9908, 120.2133),
        "高雄": (22.6273, 120.3014),
        "基隆": (25.1276, 121.7392),
        "新竹": (24.8138, 120.9675),
        "苗栗": (24.5601, 120.8214),
        "彰化": (24.0518, 120.5161),
        "南投": (23.9609, 120.9719),
        "雲林": (23.7092, 120.4313),
        "嘉義": (23.4801, 120.4491),
        "屏東": (22.5519, 120.5487),
        "宜蘭": (24.7021, 121.7378),
        "花蓮": (23.9933, 121.6015),
        "台東": (22.7972, 121.1713),
    }

    def get_weather(self, city_name: str) -> Optional[Dict]:
        """
        取得指定城市的天氣資料（同步方法）
        
        Args:
            city_name: 城市名稱，如 "台北"、"高雄" 等
            
        Returns:
            天氣資料字典，包含 temperature, condition, humidity, wind_speed, source
            如果失敗則返回 None
        """
        try:
            # 檢查城市是否支援
            if city_name not in self.CITY_COORDINATES:
                print(f"不支援的城市：{city_name}")
                return None
            
            # 取得城市座標
            lat, lon = self.CITY_COORDINATES[city_name]
            location = UserLocation(latitude=lat, longitude=lon, address=city_name)
            
            # 使用 asyncio 執行異步方法
            import asyncio
            
            try:
                # 在新的事件迴圈中執行
                weather = asyncio.run(self.get_current_weather(location))
                
                # 轉換為字典格式
                return {
                    'temperature': f"{weather.temperature}°C",
                    'condition': weather.description,
                    'humidity': f"{weather.humidity}%",
                    'wind_speed': f"{weather.wind_speed} m/s",
                    'source': '中央氣象署 API',
                    'rain_probability': f"{weather.rain_probability}%"
                }
                
            except RuntimeError as e:
                if "asyncio.run() cannot be called from a running loop" in str(e):
                    # 如果已經在事件迴圈中，使用不同的方法
                    loop = asyncio.get_event_loop()
                    weather = loop.run_until_complete(self.get_current_weather(location))
                    
                    return {
                        'temperature': f"{weather.temperature}°C",
                        'condition': weather.description,
                        'humidity': f"{weather.humidity}%",
                        'wind_speed': f"{weather.wind_speed} m/s",
                        'source': '中央氣象署 API',
                        'rain_probability': f"{weather.rain_probability}%"
                    }
                else:
                    raise
                
        except Exception as e:
            print(f"取得 {city_name} 天氣失敗：{e}")
            return None

# 全域天氣服務實例
weather_service = WeatherService()
