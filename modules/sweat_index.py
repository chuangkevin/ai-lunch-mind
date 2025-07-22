# 流汗指數計算模組
# 基於溫度、濕度、風速等氣象條件計算體感溫度與流汗指數
# 整合真實天氣API查詢功能

import math
import requests
import os
from typing import Dict, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()

def get_location_coordinates(location: str) -> Optional[Tuple[float, float, str]]:
    """
    將地址或地標轉換為經緯度座標
    :param location: 地址、地標名稱或經緯度字串
    :return: (緯度, 經度, 處理後的地點名稱) 或 None
    """
    try:
        # 檢查是否為經緯度格式 (lat,lng)
        if ',' in location and len(location.split(',')) == 2:
            parts = location.split(',')
            try:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    return (lat, lng, f"座標({lat},{lng})")
            except ValueError:
                pass
        
        # TODO: 將硬編碼的台灣地點座標庫改用資料庫存儲 (如 SQLite)
        # 應包含：地點名稱、緯度、經度、顯示名稱、類型(景點/車站/夜市等)、更新時間等欄位
        # 可考慮支援地點別名、多語言名稱等功能，並定期從API更新座標資料
        # 台灣常見地點座標庫
        taiwan_locations = {
            # 原有測試地點
            "台北101": (25.0340, 121.5645, "台北101"),
            "台北市敦化南路二段77號": (25.0271, 121.5493, "台北市敦化南路二段77號"),
            "新北市泰山區貴子路2號": (25.0597, 121.4313, "新北市泰山區貴子路2號"),
            "900屏東縣屏東市青島街106號": (22.6690, 120.4818, "屏東縣屏東市青島街106號"),
            "六十石山": (23.3081, 121.2833, "六十石山"),
            
            # 車站機場
            "台北車站": (25.0478, 121.5170, "台北車站"),
            "高雄車站": (22.6391, 120.3022, "高雄車站"),
            "台中車站": (24.1369, 120.6856, "台中車站"),
            "台南車站": (22.9969, 120.2127, "台南車站"),
            "桃園機場": (25.0777, 121.2328, "桃園國際機場"),
            "高雄機場": (22.5771, 120.3498, "高雄國際機場"),
            
            # 自然景點
            "阿里山": (23.5112, 120.8128, "阿里山"),
            "日月潭": (23.8569, 120.9150, "日月潭"),
            "太魯閣": (24.1580, 121.4906, "太魯閣國家公園"),
            "墾丁": (22.0072, 120.7473, "墾丁"),
            "九份": (25.1095, 121.8439, "九份老街"),
            "淡水": (25.1677, 121.4408, "淡水老街"),
            
            # 都市地標
            "西門町": (25.0421, 121.5066, "西門町"),
            "信義區": (25.0336, 121.5645, "台北市信義區"),
            "彰化大佛": (24.0838, 120.5397, "彰化大佛"),
            
            # 新增常見地點（基於測試結果）
            "中正紀念堂": (25.0346, 121.5218, "中正紀念堂"),
            "士林夜市": (25.0883, 121.5251, "士林夜市"),
            "愛河": (22.6516, 120.2998, "愛河"),
            "逢甲夜市": (24.1774, 120.6466, "逢甲夜市"),
            "安平古堡": (23.0016, 120.1606, "安平古堡"),
            "清水斷崖": (24.2101, 121.6781, "清水斷崖"),
            "野柳地質公園": (25.2113, 121.6964, "野柳地質公園"),
            "鹿港老街": (24.0571, 120.4321, "鹿港老街"),
            "溪頭森林遊樂區": (23.6667, 120.7833, "溪頭森林遊樂區"),
            "金城武樹": (23.0974, 121.2044, "金城武樹"),
            
            # 其他夜市
            "饒河夜市": (25.0516, 121.5771, "饒河夜市"),
            "華西街夜市": (25.0371, 121.5010, "華西街夜市"),
            "南機場夜市": (25.0297, 121.5069, "南機場夜市"),
            "寧夏夜市": (25.0565, 121.5158, "寧夏夜市"),
            "六合夜市": (22.6318, 120.3014, "六合夜市"),
            "瑞豐夜市": (22.6589, 120.3116, "瑞豐夜市"),
            "一中街": (24.1465, 120.6845, "一中街"),
            "花園夜市": (22.9928, 120.2269, "花園夜市"),
            
            # 知名景點
            "故宮博物院": (25.1013, 121.5481, "故宮博物院"),
            "龍山寺": (25.0368, 121.4999, "龍山寺"),
            "總統府": (25.0404, 121.5090, "總統府"),
            "國父紀念館": (25.0403, 121.5603, "國父紀念館"),
            "中山紀念林": (25.0735, 121.5200, "中山紀念林"),
            "陽明山": (25.1561, 121.5284, "陽明山"),
            "貓空": (24.9738, 121.5766, "貓空"),
            "烏來": (24.8638, 121.5496, "烏來"),
            "平溪": (25.0261, 121.7428, "平溪"),
            "十分瀑布": (25.0448, 121.7693, "十分瀑布"),
        }
        
        # 檢查預設地點庫
        for key, (lat, lng, display_name) in taiwan_locations.items():
            if key in location or location in key:
                return (lat, lng, display_name)
        
        # 嘗試使用地理編碼服務（加上SSL驗證跳過）
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': location,
                'format': 'json',
                'limit': 1,
                'countrycodes': 'tw',
                'addressdetails': 1
            }
            
            headers = {
                'User-Agent': 'AI-Lunch-Mind/1.0 (lunch-recommendation-app)'
            }
            
            response = requests.get(url, params=params, headers=headers, 
                                  timeout=10, verify=False)
            response.raise_for_status()
            data = response.json()
            
            if data:
                result = data[0]
                lat = float(result['lat'])
                lng = float(result['lon'])
                display_name = result.get('display_name', location)
                return (lat, lng, display_name)
        except:
            pass  # 如果線上服務失敗，繼續用其他方法
        
        # 如果都找不到，嘗試從地址中推測縣市
        # TODO: 將縣市座標資料改用資料庫存儲 (如 SQLite)
        # 應包含：縣市名稱、中心座標、邊界資料、行政代碼等，並支援縣市別名匹配
        city_coords = {
            "台北": (25.0330, 121.5654, "台北市"),
            "新北": (25.0118, 121.4652, "新北市"),
            "桃園": (24.9936, 121.3010, "桃園市"),
            "台中": (24.1477, 120.6736, "台中市"),
            "台南": (22.9999, 120.2269, "台南市"),
            "高雄": (22.6273, 120.3014, "高雄市"),
            "基隆": (25.1276, 121.7391, "基隆市"),
            "新竹": (24.8138, 120.9675, "新竹市"),
            "苗栗": (24.5602, 120.8214, "苗栗縣"),
            "彰化": (24.0518, 120.5161, "彰化縣"),
            "南投": (23.9609, 120.9718, "南投縣"),
            "雲林": (23.7092, 120.4313, "雲林縣"),
            "嘉義": (23.4800, 120.4491, "嘉義市"),
            "屏東": (22.6690, 120.4818, "屏東縣"),
            "宜蘭": (24.7021, 121.7378, "宜蘭縣"),
            "花蓮": (23.9871, 121.6015, "花蓮縣"),
            "台東": (22.7972, 121.1713, "台東縣"),
        }
        
        for city_name, (lat, lng, display_name) in city_coords.items():
            if city_name in location:
                return (lat, lng, f"{display_name}(推估)")
        
        return None
        
    except Exception as e:
        print(f"地理編碼失敗: {e}")
        return None

def get_real_weather_data(latitude: float, longitude: float) -> Dict:
    """
    根據經緯度獲取真實的天氣資料
    :param latitude: 緯度
    :param longitude: 經度
    :return: 包含溫度、濕度等資訊的字典，如果無法獲取真實資料則返回錯誤
    """
    try:
        api_key = os.getenv("CWB_API_KEY")
        if not api_key:
            return {
                "error": "中央氣象署 API 金鑰未設置",
                "message": "請設置 CWB_API_KEY 環境變數以獲取真實天氣資料"
            }
        
        # 使用中央氣象署自動氣象站資料
        url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
        params = {
            'Authorization': api_key,
            'elementName': 'TEMP,HUMD,WDSD',
            'parameterName': 'LAT,LON'
        }
        
        response = requests.get(url, params=params, timeout=15, verify=False)
        response.raise_for_status()
        data = response.json()
        
        # 檢查API回應狀態
        if data.get('success') != 'true':
            return {
                "error": "中央氣象署API回應錯誤",
                "message": f"API狀態: {data.get('result', {}).get('resource_id', 'unknown')}"
            }
        
        # 找到最近的氣象站
        nearest_station = find_nearest_weather_station(latitude, longitude, data)
        
        if nearest_station:
            nearest_station['is_real_data'] = True
            
            # 加入降雨機率查詢
            try:
                from modules.weather import get_rain_probability_for_location
                rain_prob = get_rain_probability_for_location(latitude, longitude, api_key)
                nearest_station['rain_probability'] = rain_prob
            except Exception as e:
                print(f"獲取降雨機率失敗: {e}")
                nearest_station['rain_probability'] = {"probability": "N/A", "source": "查詢失敗"}
            
            return nearest_station
        else:
            return {
                "error": "找不到附近的氣象站",
                "message": f"座標 ({latitude}, {longitude}) 附近200公里內無可用氣象站資料"
            }
            
    except requests.exceptions.Timeout:
        return {
            "error": "API請求超時",
            "message": "中央氣象署API請求超過15秒未回應"
        }
    except requests.exceptions.RequestException as e:
        return {
            "error": "網路連線錯誤",
            "message": f"無法連接到中央氣象署API: {str(e)}"
        }
    except Exception as e:
        return {
            "error": "獲取天氣資料失敗",
            "message": f"未知錯誤: {str(e)}"
        }

def find_nearest_weather_station(lat: float, lng: float, weather_data: Dict) -> Optional[Dict]:
    """
    找到最近的氣象站並提取天氣資料
    """
    try:
        stations = weather_data.get('records', {}).get('Station', [])
        min_distance = float('inf')
        nearest_station_data = None
        
        print(f"🔍 搜尋氣象站... (共找到 {len(stations)} 個測站)")
        
        for station in stations:
            # 獲取氣象站座標 (使用WGS84格式)
            station_lat = None
            station_lng = None
            
            geo_info = station.get('GeoInfo', {})
            coordinates = geo_info.get('Coordinates', [])
            
            # 找WGS84座標
            for coord in coordinates:
                if coord.get('CoordinateName') == 'WGS84':
                    try:
                        station_lat = float(coord.get('StationLatitude', 0))
                        station_lng = float(coord.get('StationLongitude', 0))
                        break
                    except (ValueError, TypeError):
                        continue
            
            # 如果沒有WGS84，使用第一個可用的座標
            if station_lat is None and coordinates:
                try:
                    station_lat = float(coordinates[0].get('StationLatitude', 0))
                    station_lng = float(coordinates[0].get('StationLongitude', 0))
                except (ValueError, TypeError):
                    continue
            
            if station_lat is None or station_lng is None:
                continue
            
            # 使用更精確的距離計算 (Haversine公式)
            distance_km = calculate_distance(lat, lng, station_lat, station_lng)
            
            # 提取天氣要素
            weather_element = station.get('WeatherElement', {})
            temp = None
            humidity = None
            wind_speed = 0
            
            try:
                # 溫度
                temp_str = weather_element.get('AirTemperature')
                if temp_str and temp_str != '-990.0' and temp_str != '-99.0':
                    temp = float(temp_str)
                
                # 濕度
                humidity_str = weather_element.get('RelativeHumidity')
                if humidity_str and humidity_str != '-990' and humidity_str != '-99':
                    humidity = float(humidity_str)
                
                # 風速
                wind_str = weather_element.get('WindSpeed')
                if wind_str and wind_str != '-990.0' and wind_str != '-99.0':
                    wind_speed = float(wind_str)
                else:
                    wind_speed = 0
                    
            except (ValueError, TypeError):
                continue
            
            # 只有當有效的溫度和濕度資料時才考慮這個測站
            if temp is not None and humidity is not None and distance_km < min_distance:
                min_distance = distance_km
                
                station_name = station.get('StationName', '未知測站')
                obs_time = station.get('ObsTime', {}).get('DateTime', '')
                
                nearest_station_data = {
                    'station_name': station_name,
                    'temperature': temp,
                    'humidity': humidity,
                    'wind_speed': wind_speed,
                    'distance_km': distance_km,
                    'data_time': obs_time,
                    'is_real_data': True
                }
                print(f"📡 找到有效測站: {station_name} (距離 {distance_km:.1f}公里, {temp}°C, {humidity}%)")
        
        # 檢查是否在合理範圍內 (200公里)
        if nearest_station_data and nearest_station_data['distance_km'] <= 200:
            print(f"✅ 使用最近測站: {nearest_station_data['station_name']}")
            return nearest_station_data
        else:
            if nearest_station_data:
                print(f"❌ 最近測站距離 {nearest_station_data['distance_km']:.1f}公里，超過200公里限制")
            else:
                print("❌ 沒有找到有有效天氣資料的測站")
            return None
        
    except Exception as e:
        print(f"處理氣象站資料失敗: {e}")
        return None

def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    使用Haversine公式計算兩點間距離（公里）
    """
    import math
    
    # 轉換為弧度
    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)
    
    # Haversine公式
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad
    
    a = (math.sin(dlat/2)**2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2)
    c = 2 * math.asin(math.sqrt(a))
    
    # 地球半徑（公里）
    r = 6371
    
    return r * c

def get_simulated_weather(latitude: float, longitude: float) -> Dict:
    """
    根據地理位置和季節提供合理的模擬天氣資料
    """
    import random
    from datetime import datetime
    
    current_month = datetime.now().month
    
    # 根據緯度和月份調整溫度
    base_temp = 25
    if latitude > 25.5:  # 北部
        base_temp = 22
    elif latitude < 23.5:  # 南部
        base_temp = 28
    
    # 季節調整
    if current_month in [12, 1, 2]:  # 冬季
        base_temp -= 8
    elif current_month in [6, 7, 8]:  # 夏季
        base_temp += 5
    elif current_month in [3, 4, 5]:  # 春季
        base_temp += 2
    else:  # 秋季
        base_temp -= 2
    
    # 添加隨機變化
    temp = base_temp + random.uniform(-3, 3)
    humidity = random.uniform(60, 85)
    wind_speed = random.uniform(0.5, 3.0)
    
    return {
        'station_name': '模擬資料',
        'temperature': round(temp, 1),
        'humidity': round(humidity, 1),
        'wind_speed': round(wind_speed, 1),
        'distance_km': 0,
        'data_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'is_simulated': True
    }

def query_sweat_index_by_location(location: str) -> Dict:
    """
    根據地點查詢真實天氣資料並計算流汗指數
    :param location: 地點（地址、地標、座標等）
    :return: 完整的流汗指數分析結果或錯誤訊息
    """
    try:
        print(f"🔍 正在查詢地點: {location}")
        
        # 1. 地理編碼
        coords = get_location_coordinates(location)
        if not coords:
            return {"error": f"無法找到地點: {location}"}
        
        latitude, longitude, display_name = coords
        print(f"📍 座標: {latitude}, {longitude}")
        print(f"📍 地點: {display_name}")
        
        # 2. 獲取真實天氣資料
        weather_data = get_real_weather_data(latitude, longitude)
        
        # 檢查是否有錯誤
        if 'error' in weather_data:
            error_msg = weather_data.get('error', '未知錯誤')
            detail_msg = weather_data.get('message', weather_data.get('detail', ''))
            print(f"❌ {error_msg}: {detail_msg}")
            return {
                "error": "無法獲取真實天氣資料",
                "details": weather_data,
                "location": display_name,
                "coordinates": {"latitude": latitude, "longitude": longitude}
            }
        
        # 檢查必要的天氣資料
        if 'temperature' not in weather_data or 'humidity' not in weather_data:
            return {
                "error": "天氣資料不完整",
                "details": "缺少溫度或濕度資料",
                "location": display_name,
                "coordinates": {"latitude": latitude, "longitude": longitude}
            }
        
        temp = weather_data['temperature']
        humidity = weather_data['humidity']
        wind_speed = weather_data.get('wind_speed', 0)
        
        print(f"🌤️ 真實天氣資料: {temp}°C, {humidity}%, 風速 {wind_speed}m/s")
        print(f"📡 資料來源: {weather_data.get('station_name', '未知測站')}")
        
        # 3. 計算流汗指數和建議 (傳入降雨資料)
        rain_data = weather_data.get('rain_probability', {})
        recommendation = calculate_dining_recommendation(
            temp, humidity, wind_speed, display_name, rain_data
        )
        
        # 4. 添加原始天氣資料和座標
        recommendation['weather_source'] = weather_data
        recommendation['coordinates'] = {
            'latitude': latitude, 
            'longitude': longitude
        }
        
        return recommendation
        
    except Exception as e:
        return {"error": f"查詢流汗指數失敗: {e}"}

def estimate_sweat_index(temp: float, humidity: float, wind_speed: float = 0) -> float:
    """
    估算流汗指數（基於體感溫度和濕度）
    :param temp: 溫度 (攝氏度)
    :param humidity: 相對濕度 (%)
    :param wind_speed: 風速 (m/s)，預設為0
    :return: 流汗指數 (0-10分)
    """
    try:
        # 計算體感溫度 (Heat Index)
        if temp < 27:
            heat_index = temp
        else:
            # 使用美國國家氣象局標準熱指數公式 (Rothfusz regression)
            # 注意：原公式使用華氏度，需要轉換
            temp_f = temp * 9/5 + 32  # 轉換為華氏度
            
            hi_f = (-42.379 + 
                    2.04901523 * temp_f + 
                    10.14333127 * humidity - 
                    0.22475541 * temp_f * humidity - 
                    6.83783e-3 * temp_f**2 - 
                    5.481717e-2 * humidity**2 + 
                    1.22874e-3 * temp_f**2 * humidity + 
                    8.5282e-4 * temp_f * humidity**2 - 
                    1.99e-6 * temp_f**2 * humidity**2)
            
            heat_index = (hi_f - 32) * 5/9  # 轉換回攝氏度
        
        # 風速修正（基於風寒效應）
        # 參考：風速每增加1m/s約降低體感溫度1-2度
        wind_chill_factor = wind_speed * 1.5  # 更保守的風速修正
        adjusted_temp = heat_index - wind_chill_factor
        
        # 計算流汗指數 (0-10分)
        if adjusted_temp <= 20:
            sweat_index = 0
        elif adjusted_temp <= 25:
            sweat_index = 1 + (adjusted_temp - 20) * 0.4  # 1-3分
        elif adjusted_temp <= 30:
            sweat_index = 3 + (adjusted_temp - 25) * 0.6  # 3-6分
        elif adjusted_temp <= 35:
            sweat_index = 6 + (adjusted_temp - 30) * 0.6  # 6-9分
        else:
            sweat_index = min(10, 9 + (adjusted_temp - 35) * 0.2)  # 9-10分
        
        # 濕度修正（濕度越高，流汗指數越高）
        humidity_factor = max(0, (humidity - 60) * 0.02)  # 濕度 > 60% 時增加流汗指數
        sweat_index += humidity_factor
        
        return round(min(10, max(0, sweat_index)), 1)
        
    except Exception as e:
        print(f"計算流汗指數失敗: {e}")
        return 0.0

def calculate_heat_index(temp: float, humidity: float) -> float:
    """
    計算體感溫度（熱指數）
    :param temp: 溫度 (攝氏度)
    :param humidity: 相對濕度 (%)
    :return: 體感溫度 (攝氏度)
    """
    try:
        if temp < 27:
            return temp
        
        # 使用美國國家氣象局的熱指數公式
        temp_f = temp * 9/5 + 32  # 轉換為華氏度
        
        hi_f = (-42.379 + 
                2.04901523 * temp_f + 
                10.14333127 * humidity - 
                0.22475541 * temp_f * humidity - 
                6.83783e-3 * temp_f**2 - 
                5.481717e-2 * humidity**2 + 
                1.22874e-3 * temp_f**2 * humidity + 
                8.5282e-4 * temp_f * humidity**2 - 
                1.99e-6 * temp_f**2 * humidity**2)
        
        # 轉換回攝氏度
        heat_index_c = (hi_f - 32) * 5/9
        return round(heat_index_c, 1)
        
    except Exception as e:
        print(f"計算體感溫度失敗: {e}")
        return temp

def get_comfort_level(sweat_index: float) -> Dict[str, str]:
    """
    根據流汗指數判斷舒適度等級
    :param sweat_index: 流汗指數 (0-10)
    :return: 舒適度等級資訊
    """
    if sweat_index <= 2:
        return {
            "level": "非常舒適",
            "description": "不易流汗，戶外活動很舒適",
            "color": "green",
            "advice": "適合長時間戶外活動，推薦戶外用餐"
        }
    elif sweat_index <= 4:
        return {
            "level": "舒適",
            "description": "微微流汗，戶外活動舒適",
            "color": "lightgreen",
            "advice": "適合戶外活動，戶外用餐無負擔"
        }
    elif sweat_index <= 6:
        return {
            "level": "普通",
            "description": "容易流汗，戶外活動需注意",
            "color": "yellow",
            "advice": "可戶外用餐，建議選擇有遮蔽的位置"
        }
    elif sweat_index <= 8:
        return {
            "level": "不舒適",
            "description": "大量流汗，戶外活動較辛苦",
            "color": "orange",
            "advice": "建議室內用餐，戶外活動需防曬補水"
        }
    else:
        return {
            "level": "非常不舒適",
            "description": "極易流汗，不適合戶外活動",
            "color": "red",
            "advice": "強烈建議室內用餐，避免長時間戶外暴露"
        }

def calculate_dining_recommendation(temp: float, humidity: float, wind_speed: float = 0, location: str = "", rain_data: dict = None) -> Dict:
    """
    基於天氣條件計算用餐建議
    :param temp: 溫度 (攝氏度)
    :param humidity: 相對濕度 (%)
    :param wind_speed: 風速 (m/s)
    :param location: 地點名稱
    :param rain_data: 降雨資料 (包含 probability 等)
    :return: 用餐建議資訊
    """
    try:
        # 計算流汗指數
        sweat_index = estimate_sweat_index(temp, humidity, wind_speed)
        
        # 計算體感溫度
        heat_index = calculate_heat_index(temp, humidity)
        
        # 獲取舒適度等級
        comfort = get_comfort_level(sweat_index)
        
        # 分析降雨機率影響
        rain_impact = analyze_rain_impact(rain_data) if rain_data else None
        
        # 生成用餐場所建議 (考慮降雨)
        if rain_impact and rain_impact.get('high_probability', False):
            venue_preference = "室內座位強烈建議"
            venue_advice = f"預計降雨機率 {rain_impact.get('probability', 'N/A')}，強烈建議室內用餐"
        elif sweat_index <= 3:
            venue_preference = "戶外座位優先"
            venue_advice = "推薦露天餐廳、陽台座位或庭園餐廳"
            if rain_impact and rain_impact.get('moderate_probability', False):
                venue_advice += f"（注意：降雨機率 {rain_impact.get('probability', 'N/A')}，建議選擇有遮蔽的戶外座位）"
        elif sweat_index <= 5:
            venue_preference = "戶外室內皆可"
            venue_advice = "可選擇有遮蔭的戶外座位或通風良好的室內"
            if rain_impact and rain_impact.get('moderate_probability', False):
                venue_advice += f"（降雨機率 {rain_impact.get('probability', 'N/A')}，建議偏向室內）"
        elif sweat_index <= 7:
            venue_preference = "室內座位建議"
            venue_advice = "建議室內用餐，如選擇戶外需有冷氣或風扇"
        else:
            venue_preference = "室內座位強烈建議"
            venue_advice = "強烈建議冷氣房用餐，避免戶外座位"
        
        # 生成飲品建議 (考慮降雨)
        if sweat_index <= 3:
            drink_advice = "溫熱飲品或常溫飲料"
        elif sweat_index <= 6:
            drink_advice = "冰涼飲品，注意補充水分"
        else:
            drink_advice = "大量冰涼飲品，加強補水"
        
        if rain_impact and rain_impact.get('high_probability', False):
            drink_advice += "，建議準備雨具"
        
        # 計算戶外舒適度評分 (0-10分，考慮降雨)
        outdoor_comfort_score = max(0, 10 - sweat_index)
        if rain_impact:
            if rain_impact.get('high_probability', False):
                outdoor_comfort_score = max(0, outdoor_comfort_score - 4)
            elif rain_impact.get('moderate_probability', False):
                outdoor_comfort_score = max(0, outdoor_comfort_score - 2)
        
        result = {
            "location": location,
            "temperature": temp,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "heat_index": heat_index,
            "sweat_index": sweat_index,
            "comfort_level": comfort,
            "outdoor_comfort_score": outdoor_comfort_score,
            "venue_preference": venue_preference,
            "venue_advice": venue_advice,
            "drink_advice": drink_advice,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 添加降雨資訊
        if rain_impact:
            result["rain_info"] = rain_impact
        
        return result
        
    except Exception as e:
        return {
            "error": f"計算用餐建議失敗: {e}",
            "location": location,
            "temperature": temp,
            "humidity": humidity
        }

def analyze_rain_impact(rain_data: dict) -> dict:
    """
    分析降雨機率對用餐的影響
    :param rain_data: 降雨資料
    :return: 降雨影響分析
    """
    try:
        probability_str = rain_data.get('probability', 'N/A')
        
        if probability_str == 'N/A' or probability_str == '':
            return {
                "probability": 'N/A',
                "level": "未知",
                "impact": "無降雨資料",
                "advice": "建議查看最新天氣預報"
            }
        
        # 轉換百分比字串為數字
        try:
            if isinstance(probability_str, str) and '%' in probability_str:
                probability = int(probability_str.replace('%', ''))
            else:
                probability = int(float(probability_str))
        except (ValueError, TypeError):
            return {
                "probability": probability_str,
                "level": "未知",
                "impact": "降雨機率格式無法解析",
                "advice": "建議查看最新天氣預報"
            }
        
        # 判斷降雨機率等級
        if probability >= 70:
            return {
                "probability": f"{probability}%",
                "level": "高",
                "impact": "很可能下雨",
                "advice": "強烈建議室內用餐，準備雨具",
                "high_probability": True
            }
        elif probability >= 40:
            return {
                "probability": f"{probability}%",
                "level": "中等",
                "impact": "可能會下雨",
                "advice": "建議選擇有遮蔽的座位，攜帶雨具",
                "moderate_probability": True
            }
        elif probability >= 20:
            return {
                "probability": f"{probability}%",
                "level": "低",
                "impact": "降雨機率較低",
                "advice": "可安心戶外用餐，建議攜帶輕便雨具"
            }
        else:
            return {
                "probability": f"{probability}%",
                "level": "極低",
                "impact": "幾乎不會下雨",
                "advice": "適合戶外活動"
            }
        
    except Exception as e:
        return {
            "probability": 'N/A',
            "level": "錯誤",
            "impact": f"分析失敗: {e}",
            "advice": "建議查看最新天氣預報"
        }

def get_sweat_risk_alerts(temp: float, humidity: float, wind_speed: float = 0) -> list:
    """
    根據天氣條件生成流汗風險警報
    :param temp: 溫度 (攝氏度)
    :param humidity: 相對濕度 (%)
    :param wind_speed: 風速 (m/s)
    :return: 警報列表
    """
    try:
        alerts = []
        sweat_index = estimate_sweat_index(temp, humidity, wind_speed)
        heat_index = calculate_heat_index(temp, humidity)
        
        # 高溫警報
        if temp >= 35:
            alerts.append({
                "type": "高溫警報",
                "level": "嚴重",
                "message": f"氣溫 {temp}°C，極端高溫，避免戶外活動",
                "value": temp,
                "threshold": 35
            })
        elif temp >= 32:
            alerts.append({
                "type": "高溫警報",
                "level": "警告",
                "message": f"氣溫 {temp}°C，高溫炎熱，戶外活動需防曬",
                "value": temp,
                "threshold": 32
            })
        
        # 體感溫度警報
        if heat_index >= 38:
            alerts.append({
                "type": "體感溫度警報",
                "level": "嚴重",
                "message": f"體感溫度 {heat_index}°C，極度危險，避免戶外暴露",
                "value": heat_index,
                "threshold": 38
            })
        elif heat_index >= 32:
            alerts.append({
                "type": "體感溫度警報",
                "level": "警告", 
                "message": f"體感溫度 {heat_index}°C，注意中暑風險",
                "value": heat_index,
                "threshold": 32
            })
        
        # 流汗指數警報
        if sweat_index >= 8:
            alerts.append({
                "type": "流汗指數警報",
                "level": "嚴重",
                "message": f"流汗指數 {sweat_index}/10，極易大量流汗，建議室內活動",
                "value": sweat_index,
                "threshold": 8
            })
        elif sweat_index >= 6:
            alerts.append({
                "type": "流汗指數警報",
                "level": "警告",
                "message": f"流汗指數 {sweat_index}/10，容易流汗，注意補水",
                "value": sweat_index,
                "threshold": 6
            })
        
        # 高濕度警報
        if humidity >= 85:
            alerts.append({
                "type": "濕度警報",
                "level": "警告",
                "message": f"相對濕度 {humidity}%，悶熱潮濕，體感溫度較高",
                "value": humidity,
                "threshold": 85
            })
        
        # 如果沒有警報，返回正常狀態
        if not alerts:
            alerts.append({
                "type": "正常",
                "level": "良好",
                "message": f"天氣舒適，流汗指數 {sweat_index}/10，適合戶外活動"
            })
        
        return alerts
        
    except Exception as e:
        return [{
            "type": "錯誤",
            "level": "錯誤",
            "message": f"計算流汗風險警報失敗: {e}"
        }]

# 保持向下相容的舊函數名稱
def calculate_sweat_index(temperature: float, humidity: float, air_quality=None) -> float:
    """
    計算流汗指數（向下相容函數）
    :param temperature: 溫度
    :param humidity: 濕度
    :param air_quality: 保留參數但不使用
    :return: 流汗指數
    """
    return estimate_sweat_index(temperature, humidity)
