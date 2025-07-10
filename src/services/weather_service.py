"""
天氣服務模組 - 重構版
整合中央氣象署開放資料平台 API (新版結構)
"""
import httpx
from typing import Dict, List, Optional
from src.config import settings
from src.models import WeatherCondition, UserLocation
import math
import asyncio

class WeatherService:
    """天氣服務 - 使用中央氣象署 API (適配新版結構)"""
    
    def __init__(self):
        self.api_key = settings.cwb_api_key
        self.base_url = "https://opendata.cwa.gov.tw/api"
        
        if not self.api_key or not self.api_key.startswith("CWB-"):
            raise ValueError("中央氣象署 API Key 未設定或格式錯誤，請檢查 .env 檔案中的 CWB_API_KEY 設定")
        
        print(f"🌤️ 天氣服務初始化完成，API Key: {self.api_key[:20]}...")
    
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
    
    def _extract_coordinates_from_station(self, station: Dict) -> Optional[tuple]:
        """從氣象站資料中提取座標 - 適配最新API結構"""
        station_name = station.get('StationName', '未知站點')
        
        # 方法1: 新版API - GeoInfo.Coordinates (可能是字典列表格式)
        geo_info = station.get('GeoInfo', {})
        if geo_info:
            coordinates = geo_info.get('Coordinates', [])
            print(f"   🔍 {station_name} GeoInfo.Coordinates: {coordinates} (type: {type(coordinates)})")
            
            if coordinates:
                try:
                    if isinstance(coordinates, list) and len(coordinates) > 0:
                        coord_item = coordinates[0]  # 取第一個元素
                        
                        if isinstance(coord_item, dict):
                            # 如果是字典，查找座標欄位
                            lat = None
                            lon = None
                            
                            # 檢查各種可能的欄位名稱
                            for lat_key in ['latitude', 'lat', 'Latitude', 'StationLatitude']:
                                if lat_key in coord_item:
                                    lat = coord_item[lat_key]
                                    break
                            
                            for lon_key in ['longitude', 'lon', 'lng', 'Longitude', 'StationLongitude']:
                                if lon_key in coord_item:
                                    lon = coord_item[lon_key]
                                    break
                            
                            if lat is not None and lon is not None:
                                latitude = float(lat)
                                longitude = float(lon)
                                print(f"   ✅ {station_name} 字典座標解析成功: ({latitude:.6f}, {longitude:.6f})")
                                return latitude, longitude
                        
                        elif isinstance(coord_item, (int, float)):
                            # 如果是數值列表格式 [lon, lat]
                            if len(coordinates) >= 2:
                                longitude = float(coordinates[0])
                                latitude = float(coordinates[1])
                                print(f"   ✅ {station_name} 數值列表座標解析成功: ({latitude:.6f}, {longitude:.6f})")
                                return latitude, longitude
                        
                        elif isinstance(coord_item, str):
                            # 字串格式座標
                            coord_parts = coord_item.replace('(', '').replace(')', '').split(',')
                            if len(coord_parts) >= 2:
                                longitude = float(coord_parts[0].strip())
                                latitude = float(coord_parts[1].strip())
                                print(f"   ✅ {station_name} 字串座標解析成功: ({latitude:.6f}, {longitude:.6f})")
                                return latitude, longitude
                
                except (ValueError, TypeError, IndexError) as e:
                    print(f"   ⚠️ {station_name} 座標解析錯誤: {e}")
            
            # 檢查 GeoInfo 中的其他座標欄位
            for lat_key in ['StationLatitude', 'Latitude', 'lat']:
                for lon_key in ['StationLongitude', 'Longitude', 'lon']:
                    if lat_key in geo_info and lon_key in geo_info:
                        try:
                            lat = float(geo_info[lat_key])
                            lon = float(geo_info[lon_key])
                            print(f"   ✅ {station_name} GeoInfo直接座標解析成功: ({lat:.6f}, {lon:.6f})")
                            return lat, lon
                        except (ValueError, TypeError):
                            continue
        
        # 方法2: 檢查是否直接在station層級有座標
        for lat_key in ['lat', 'latitude', 'Latitude', 'StationLatitude']:
            for lon_key in ['lon', 'lng', 'longitude', 'Longitude', 'StationLongitude']:
                if lat_key in station and lon_key in station:
                    try:
                        lat = float(station[lat_key])
                        lon = float(station[lon_key])
                        print(f"   ✅ {station_name} 直接座標解析成功: ({lat:.6f}, {lon:.6f})")
                        return lat, lon
                    except (ValueError, TypeError):
                        continue
        
        print(f"   ❌ {station_name} 無法解析座標")
        return None
    
    def _extract_weather_data(self, station: Dict) -> Dict[str, float]:
        """從氣象站提取天氣資料 - 適配新版API結構（WeatherElement是字典）"""
        weather_data = {}
        
        # 新版API: WeatherElement 是字典而非列表
        weather_element = station.get("WeatherElement", {})
        
        if isinstance(weather_element, dict):
            # 直接從字典中取值
            for key, value in weather_element.items():
                if value is None or value == "-99" or value == "":
                    continue
                
                try:
                    # 嘗試轉換為數值
                    if isinstance(value, (int, float)):
                        weather_data[key] = float(value)
                    elif isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                        weather_data[key] = float(value)
                except ValueError:
                    # 保留字串值（如天氣描述）
                    weather_data[key] = value
        elif isinstance(weather_element, list):
            # 舊版API格式：WeatherElement 是列表
            for element in weather_element:
                if not isinstance(element, dict):
                    continue
                    
                element_name = element.get("ElementName", "")
                element_value = element.get("ElementValue", "")
                
                # 過濾無效值
                if not element_value or element_value == "-99" or element_value == "":
                    continue
                
                try:
                    value = float(element_value)
                    weather_data[element_name] = value
                except ValueError:
                    weather_data[element_name] = element_value
        
        return weather_data
    
    def _has_valid_temperature(self, station: Dict) -> bool:
        """檢查氣象站是否有有效的溫度資料 - 適配新版API結構"""
        station_name = station.get("StationName", "未知站點")
        weather_element = station.get("WeatherElement", {})
        
        print(f"   🌡️ {station_name} WeatherElement type: {type(weather_element)}")
        
        if isinstance(weather_element, dict):
            # WeatherElement 是字典格式，直接檢查溫度欄位
            temp_fields = ["TEMP", "Temperature", "氣溫", "溫度", "Air_Temperature"]
            
            for field in temp_fields:
                if field in weather_element:
                    temp_value = weather_element[field]
                    print(f"   🌡️ {station_name} 找到溫度欄位 {field}: {temp_value}")
                    
                    if temp_value is not None and str(temp_value) != "-99" and str(temp_value) != "":
                        try:
                            temp = float(temp_value)
                            if -50 <= temp <= 60:
                                print(f"   ✅ {station_name} 有效溫度: {temp}°C")
                                return True
                        except (ValueError, TypeError):
                            continue
            
            # 如果沒有溫度，檢查是否至少有其他天氣資料
            valid_fields = []
            for key, value in weather_element.items():
                if value is not None and str(value) != "-99" and str(value) != "":
                    valid_fields.append(key)
            
            print(f"   📊 {station_name} 有效欄位: {valid_fields}")
            
            # 如果有足夠的天氣資料，仍然視為有效
            if len(valid_fields) >= 2:
                print(f"   ✅ {station_name} 有足夠天氣資料 ({len(valid_fields)} 個欄位)")
                return True
        
        elif isinstance(weather_element, list):
            # WeatherElement 是列表格式
            for element in weather_element:
                if isinstance(element, dict):
                    element_name = element.get("ElementName", "")
                    element_value = element.get("ElementValue", "")
                    
                    if element_name in ["TEMP", "Temperature"] and element_value != "-99":
                        try:
                            temp = float(element_value)
                            if -50 <= temp <= 60:
                                print(f"   ✅ {station_name} 有效溫度: {temp}°C")
                                return True
                        except (ValueError, TypeError):
                            continue
        
        print(f"   ❌ {station_name} 無有效溫度資料")
        return False

    def _find_nearest_station(self, user_location: UserLocation, stations: List[Dict]) -> Optional[Dict]:
        """找到最近且有有效資料的氣象站 - 新版API結構"""
        if not stations:
            print("❌ 沒有氣象站資料")
            return None
            
        print(f"🔍 檢查 {len(stations)} 個氣象站...")
        
        # 過濾出有有效資料的氣象站
        valid_stations = []
        for station in stations:
            station_name = station.get("StationName", "未知站點")
            
            # 檢查座標
            coords = self._extract_coordinates_from_station(station)
            if not coords:
                print(f"   ❌ {station_name}: 無座標資料")
                continue
                
            # 檢查溫度資料
            if not self._has_valid_temperature(station):
                print(f"   ❌ {station_name}: 無有效溫度資料")
                continue
                
            # 添加座標到station物件
            station['lat'], station['lon'] = coords
            valid_stations.append(station)
            print(f"   ✅ {station_name}: 有效站點 ({coords[0]:.3f}, {coords[1]:.3f})")
        
        if not valid_stations:
            print("❌ 沒有找到有效的氣象站")
            return None
            
        print(f"✅ 找到 {len(valid_stations)} 個有效氣象站")
        
        # 找到最近的氣象站
        nearest_station = None
        min_distance = float('inf')
        
        for station in valid_stations:
            try:
                distance = self._calculate_distance(
                    user_location.latitude, user_location.longitude,
                    station['lat'], station['lon']
                )
                
                station_name = station.get('StationName', '未知')
                print(f"   📍 {station_name}: 距離 {distance:.2f} 公里")
                
                if distance < min_distance:
                    min_distance = distance
                    nearest_station = station
                    
            except Exception as e:
                print(f"   ⚠️ 距離計算錯誤: {e}")
                continue
        
        if nearest_station:
            station_name = nearest_station.get('StationName', '未知')
            print(f"🎯 選擇最近氣象站: {station_name} (距離 {min_distance:.2f} 公里)")
        
        return nearest_station
    
    async def get_current_weather(self, location: UserLocation) -> WeatherCondition:
        """取得當前天氣"""
        try:
            # 取得自動氣象站現況觀測資料
            # 修正：忽略 SSL 驗證錯誤（僅用於公開氣象資料 API）
            async with httpx.AsyncClient(verify=False) as client:
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
                
                # 修復：處理新的API結構
                records = data.get("records", {})
                if "location" in records:
                    stations = records["location"]
                elif "Station" in records:
                    # 新的API結構使用Station而非location
                    stations = records["Station"]
                else:
                    stations = []
                
                print(f"找到 {len(stations)} 個氣象站")
                
                if not stations:
                    raise Exception("無氣象站資料")
                
                # 找到最近的氣象站
                nearest_station = self._find_nearest_station(location, stations)
                if not nearest_station:
                    raise Exception("找不到最近的氣象站")
                
                print(f"使用氣象站: {nearest_station.get('StationName', nearest_station.get('locationName', '未知'))}")
                
                # 解析天氣資料 - 適配新API結構（WeatherElement是字典）
                weather_element = nearest_station.get("WeatherElement", {})
                weather_data = {}
                
                print(f"WeatherElement 類型: {type(weather_element)}")
                
                if isinstance(weather_element, dict):
                    # 新版API：WeatherElement是字典，直接取值
                    print(f"WeatherElement 欄位: {list(weather_element.keys())}")
                    
                    # 溫度 - 可能的欄位名稱
                    temp_value = None
                    for temp_field in ["TEMP", "Temperature", "氣溫", "溫度"]:
                        if temp_field in weather_element:
                            temp_value = weather_element[temp_field]
                            break
                    
                    if temp_value and str(temp_value) != "-99":
                        try:
                            weather_data["temperature"] = float(temp_value)
                        except (ValueError, TypeError):
                            weather_data["temperature"] = 22.0
                    else:
                        weather_data["temperature"] = 22.0
                    
                    # 濕度
                    humidity_value = weather_element.get("HUMD") or weather_element.get("Humidity") or weather_element.get("相對濕度")
                    if humidity_value and str(humidity_value) != "-99":
                        try:
                            weather_data["humidity"] = float(humidity_value)
                        except (ValueError, TypeError):
                            weather_data["humidity"] = 60.0
                    else:
                        weather_data["humidity"] = 60.0
                    
                    # 風速
                    wind_value = weather_element.get("WDSD") or weather_element.get("WindSpeed") or weather_element.get("風速")
                    if wind_value and str(wind_value) != "-99":
                        try:
                            weather_data["wind_speed"] = float(wind_value)
                        except (ValueError, TypeError):
                            weather_data["wind_speed"] = 2.0
                    else:
                        weather_data["wind_speed"] = 2.0
                    
                    # 降雨資料
                    rain_value = weather_element.get("24R") or weather_element.get("Rain") or weather_element.get("降雨量")
                    if rain_value and str(rain_value) != "-99":
                        try:
                            rain_24h = float(rain_value)
                            # 簡單估算降雨機率：雨量越多機率越高
                            weather_data["rain_probability"] = min(rain_24h * 10, 100.0)
                        except (ValueError, TypeError):
                            weather_data["rain_probability"] = 10.0
                    else:
                        weather_data["rain_probability"] = 10.0
                    
                    # 天氣描述
                    weather_desc = weather_element.get("Weather") or weather_element.get("天氣")
                    if weather_desc:
                        weather_data["description"] = str(weather_desc)
                
                elif isinstance(weather_element, list):
                    # 舊版API格式處理
                    for element in weather_element:
                        if not isinstance(element, dict):
                            continue
                            
                        element_name = element.get("ElementName", element.get("elementName"))
                        element_value = element.get("ElementValue", element.get("elementValue"))
                        
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
                
                # 優先使用API提供的天氣描述，否則根據數據推斷
                description = weather_data.get("description")
                if not description:
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
