# 取得鄉鎮天氣預報（含降雨機率 PoP）
import requests
import os
from dotenv import load_dotenv
load_dotenv()

def get_township_weather_data(town_name, city_name=None):
    """
    查詢中央氣象署 F-D0047-089 鄉鎮天氣預報，取得溫度、濕度、降雨機率。
    :param town_name: 鄉鎮市區名稱
    :param city_name: 縣市名稱（可選，若有助於精確比對）
    :return: dict, 包含溫度、濕度、降雨機率
    """
    api_key = os.getenv("CWB_API_KEY")
    # TODO: 將縣市代碼對應表改用資料庫存儲 (如 SQLite)
    # 建議資料表：city_weather_codes (city_name, api_code, region, active_status)
    # 優點：支援動態更新、區域分組、啟用狀態管理等
    # 依縣市自動選擇 API 代碼（如 F-D0047-001~093），預設用宜蘭縣（001）
    city_code_map = {
        "宜蘭縣": "001", "桃園市": "005", "新竹縣": "009", "苗栗縣": "013", "彰化縣": "017", "南投縣": "021", "雲林縣": "025", "嘉義縣": "029", "屏東縣": "033", "臺東縣": "037", "花蓮縣": "041", "澎湖縣": "045", "基隆市": "049", "新竹市": "053", "嘉義市": "057", "臺北市": "061", "台北市": "061", "高雄市": "065", "新北市": "069", "臺中市": "073", "台中市": "073", "臺南市": "077", "台南市": "077", "連江縣": "081", "金門縣": "085"
    }
    # city_name 必須正確，否則 fallback 用宜蘭縣
    code = city_code_map.get(city_name, "001")
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-{code}?Authorization={api_key}&format=JSON"
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
        #print(f"[DEBUG] records: {data.get('records')}")
        # 正確 key: 'Locations' -> [0] -> 'Location'
        locations = data.get('records', {}).get('Locations', [{}])[0].get('Location', [])
        all_names = [loc.get('LocationName') for loc in locations]
        #print(f"[DEBUG] {city_name} 可用鄉鎮市區: {all_names}")
        for loc in locations:
            name = loc.get('LocationName')
            if name == town_name:
                # 取出各項天氣元素
                weather_elements = {e['ElementName']: e for e in loc.get('WeatherElement', [])}
                # 取溫度（ElementName: '溫度'）
                temp = 'N/A'
                if '溫度' in weather_elements:
                    temp_times = weather_elements['溫度'].get('Time', [])
                    if temp_times:
                        temp = temp_times[0].get('ElementValue', [{}])[0].get('Temperature', 'N/A')
                # 取濕度（ElementName: '相對濕度'）
                humd = 'N/A'
                if '相對濕度' in weather_elements:
                    humd_times = weather_elements['相對濕度'].get('Time', [])
                    if humd_times:
                        humd = humd_times[0].get('ElementValue', [{}])[0].get('RelativeHumidity', 'N/A')
                # 取降雨機率（ElementName: '3小時降雨機率'）
                # 選擇最接近當前時間的降雨機率預報
                pop = 'N/A'
                if '3小時降雨機率' in weather_elements:
                    pop_times = weather_elements['3小時降雨機率'].get('Time', [])
                    if pop_times:
                        from datetime import datetime, timezone, timedelta
                        
                        # 建立台北時區 (UTC+8)
                        taipei_tz = timezone(timedelta(hours=8))
                        current_time = datetime.now(taipei_tz)
                        closest_time_entry = None
                        min_time_diff = float('inf')
                        
                        for time_entry in pop_times:
                            start_time_str = time_entry.get('StartTime', '')
                            if start_time_str:
                                try:
                                    # 解析時間格式：2025-07-22T12:00:00+08:00
                                    start_time = datetime.fromisoformat(start_time_str)
                                    time_diff = abs((start_time - current_time).total_seconds())
                                    if time_diff < min_time_diff:
                                        min_time_diff = time_diff
                                        closest_time_entry = time_entry
                                except (ValueError, TypeError):
                                    continue
                        
                        if closest_time_entry:
                            pop = closest_time_entry.get('ElementValue', [{}])[0].get('ProbabilityOfPrecipitation', 'N/A')
                return {
                    'locationName': name,
                    'temperature': temp,
                    'humidity': humd,
                    'pop': pop
                }
        return {'locationName': town_name, 'temperature': 'N/A', 'humidity': 'N/A', 'pop': 'N/A'}
    except Exception as e:
        print(f"查詢鄉鎮天氣預報失敗: {e}")
        return {'locationName': town_name, 'temperature': 'N/A', 'humidity': 'N/A', 'pop': 'N/A'}
# 天氣模組
# 使用中央氣象署 API 查詢天氣資料

import requests
import os
import re
from dotenv import load_dotenv

# 加載 .env 檔案中的環境變數
load_dotenv()

def get_weather_data(latitude_or_input, longitude=None):
    """
    根據經緯度或地址/關鍵字查詢最近的氣象站天氣資料，包含降雨機率。
    支援多種輸入格式：
    1. 經緯度座標：get_weather_data(25.0340, 121.5645)
    2. 地址字串：get_weather_data("台北市信義區信義路五段7號")
    3. 關鍵字：get_weather_data("台北101")
    4. Google Maps 短網址：get_weather_data("https://goo.gl/maps/...")
    
    :param latitude_or_input: float/str, 緯度或地址/關鍵字/網址
    :param longitude: float, 經度 (當第一個參數是緯度時使用)
    :return: dict, 包含氣溫、濕度、降雨機率的天氣資料
    """
    api_key = os.getenv("CWB_API_KEY")
    if not api_key:
        raise ValueError("中央氣象署 API 金鑰未設置")

    # 解析輸入並獲取座標
    try:
        latitude, longitude, location_info = parse_location_input(latitude_or_input, longitude)
    except Exception as e:
        return {"error": f"位置解析失敗: {str(e)}"}

    try:
        # 先嘗試獲取即時觀測資料 (溫度、濕度)
        obs_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001?Authorization={api_key}&elementName=TEMP,HUMD,WDSD&parameterName=LAT,LON"
        obs_response = requests.get(obs_url, timeout=10, verify=False)
        obs_response.raise_for_status()
        obs_data = obs_response.json()
        
        # 根據經緯度找最近的觀測站
        nearest_station = find_nearest_observation_station(latitude, longitude, obs_data)
        
        if not nearest_station:
            return {"error": "找不到附近的氣象觀測站"}
        
        # 嘗試獲取該地區的降雨機率預報
        try:
            rain_probability = get_rain_probability_for_location(latitude, longitude, api_key)
            if not rain_probability or not isinstance(rain_probability, dict):
                rain_probability = {"probability": "N/A", "source": "無法取得降雨資料"}
        except Exception as e:
            print(f"獲取降雨機率失敗: {e}")
            rain_probability = {"probability": "N/A", "source": "降雨資料查詢失敗"}
        
        # 合併觀測資料和預報資料
        weather_data = {
            **nearest_station,
            "rain_probability": rain_probability,
            "location_info": location_info  # 添加位置資訊
        }
        
        return weather_data
        
    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return {"error": f"網路請求失敗: {str(e)}"}

def parse_location_input(latitude_or_input, longitude=None):
    """
    解析各種位置輸入格式並返回座標
    :param latitude_or_input: 緯度或地址/關鍵字/網址
    :param longitude: 經度（如果第一個參數是緯度）
    :return: (latitude, longitude, location_info)
    """
    # 情況1: 已經是數字座標
    if isinstance(latitude_or_input, (int, float)) and longitude is not None:
        city = get_city_from_coordinates(latitude_or_input, longitude)
        location_info = {
            "type": "coordinates",
            "input": f"({latitude_or_input}, {longitude})",
            "city": city
        }
        return latitude_or_input, longitude, location_info
    
    # 情況2: 字串輸入（地址、關鍵字、網址）
    if isinstance(latitude_or_input, str):
        input_str = latitude_or_input.strip()
        
        # 檢查是否為 Google Maps 網址
        if 'maps' in input_str.lower() or 'goo.gl' in input_str or 'google' in input_str.lower():
            return parse_google_maps_url(input_str)
        
        # 檢查是否包含座標格式
        coord_match = re.search(r'(\d{2}\.\d+)[,\s]+(\d{2,3}\.\d+)', input_str)
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
            city = get_city_from_coordinates(lat, lng)
            location_info = {
                "type": "coordinates_string",
                "input": input_str,
                "city": city
            }
            return lat, lng, location_info
        
        # 使用 Google Maps 模組進行地址解析
        return parse_address_or_keyword(input_str)
    
    raise ValueError("無法解析的輸入格式")

def parse_google_maps_url(url):
    """
    解析 Google Maps 網址並提取座標
    :param url: Google Maps 網址
    :return: (latitude, longitude, location_info)
    """
    try:
        from modules.google_maps import resolve_short_url, extract_location_from_url
        
        # 解析短網址
        full_url = resolve_short_url(url)
        
        # 提取座標資訊
        location_data = extract_location_from_url(full_url)
        if location_data:
            lat, lng, place_name = location_data
            city = get_city_from_coordinates(lat, lng)
            location_info = {
                "type": "google_maps_url",
                "input": url,
                "place_name": place_name,
                "city": city,
                "full_url": full_url
            }
            return lat, lng, location_info
        else:
            raise ValueError("無法從 Google Maps 網址提取位置資訊")
            
    except ImportError:
        raise ValueError("Google Maps 模組未安裝")
    except Exception as e:
        raise ValueError(f"Google Maps 網址解析失敗: {str(e)}")

def parse_address_or_keyword(address_or_keyword):
    """
    解析地址或關鍵字並獲取座標
    :param address_or_keyword: 地址或關鍵字
    :return: (latitude, longitude, location_info)
    """
    try:
        from modules.google_maps import geocode_address
        
        # 使用地理編碼獲取座標
        coordinates = geocode_address(address_or_keyword)
        if coordinates:
            lat, lng = coordinates
            city = get_city_from_coordinates(lat, lng)
            location_info = {
                "type": "address_or_keyword",
                "input": address_or_keyword,
                "city": city
            }
            return lat, lng, location_info
        else:
            raise ValueError("無法解析該地址或關鍵字")
            
    except ImportError:
        raise ValueError("Google Maps 模組未安裝")
    except Exception as e:
        raise ValueError(f"地址解析失敗: {str(e)}")

# TODO: 添加更多天氣分析功能

def find_nearest_observation_station(target_lat, target_lng, obs_data):
    """
    從觀測資料中找到最近的氣象站
    :param target_lat: 目標緯度
    :param target_lng: 目標經度
    :param obs_data: 中央氣象署觀測資料
    :return: dict, 包含最近測站的天氣資料
    """
    import math
    
    try:
        stations = obs_data.get('records', {}).get('Station', [])
        min_distance = float('inf')
        nearest_station_data = None
        
        for station in stations:
            # 獲取測站座標
            geo_info = station.get('GeoInfo', {})
            coordinates = geo_info.get('Coordinates', [])
            
            station_lat = None
            station_lng = None
            
            # 找WGS84座標
            for coord in coordinates:
                if coord.get('CoordinateName') == 'WGS84':
                    try:
                        station_lat = float(coord.get('StationLatitude', 0))
                        station_lng = float(coord.get('StationLongitude', 0))
                        break
                    except (ValueError, TypeError):
                        continue
            
            if station_lat is None or station_lng is None:
                continue
            
            # 計算距離 (簡化版 Haversine 公式)
            distance = calculate_distance_simple(target_lat, target_lng, station_lat, station_lng)
            
            # 提取天氣資料
            weather_element = station.get('WeatherElement', {})
            temp = humidity = wind_speed = None
            
            try:
                # 溫度
                temp_str = weather_element.get('AirTemperature')
                if temp_str and temp_str not in ['-990.0', '-99.0', '']:
                    temp = float(temp_str)
                
                # 濕度
                humidity_str = weather_element.get('RelativeHumidity')
                if humidity_str and humidity_str not in ['-990', '-99', '']:
                    humidity = float(humidity_str)
                
                # 風速
                wind_str = weather_element.get('WindSpeed')
                if wind_str and wind_str not in ['-990.0', '-99.0', '']:
                    wind_speed = float(wind_str)
                else:
                    wind_speed = 0
                    
            except (ValueError, TypeError):
                continue
            
            # 只有當有有效資料且距離最近時才更新
            if temp is not None and humidity is not None and distance < min_distance:
                min_distance = distance
                station_name = station.get('StationName', '未知測站')
                obs_time = station.get('ObsTime', {}).get('DateTime', '')
                
                nearest_station_data = {
                    'station_name': station_name,
                    'temperature': temp,
                    'humidity': humidity,
                    'wind_speed': wind_speed or 0,
                    'distance_km': round(distance, 1),
                    'data_time': obs_time
                }
        
        return nearest_station_data if nearest_station_data and min_distance <= 200 else None
        
    except Exception as e:
        print(f"處理觀測站資料失敗: {e}")
        return None

def calculate_distance_simple(lat1, lng1, lat2, lng2):
    """
    簡化版距離計算 (Haversine 公式)
    :return: 距離 (公里)
    """
    import math
    
    # 轉換為弧度
    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)
    
    # Haversine 公式
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad
    
    a = (math.sin(dlat/2)**2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2)
    c = 2 * math.asin(math.sqrt(a))
    
    # 地球半徑 (公里)
    r = 6371
    return r * c

def get_rain_probability_for_location(latitude, longitude, api_key):
    """
    根據經緯度獲取該地區的降雨機率預報
    :param latitude: 緯度
    :param longitude: 經度
    :param api_key: API 金鑰
    :return: dict, 包含降雨機率資訊
    """
    try:
        # 根據經緯度判斷所屬縣市
        city_name = get_city_from_coordinates(latitude, longitude)
        
        if not city_name:
            return {"probability": "N/A", "source": "無法判斷地區"}
        
        # 使用鄉鎮天氣預報獲取降雨機率
        # 這裡簡化為使用縣市主要城市
        main_towns = {
            "台北市": "中正區", "新北市": "板橋區", "桃園市": "桃園區",
            "台中市": "西屯區", "台南市": "中西區", "高雄市": "三民區",
            "基隆市": "仁愛區", "新竹市": "東區", "嘉義市": "東區",
            "宜蘭縣": "宜蘭市", "新竹縣": "竹北市", "苗栗縣": "苗栗市",
            "彰化縣": "彰化市", "南投縣": "南投市", "雲林縣": "斗六市",
            "嘉義縣": "太保市", "屏東縣": "屏東市", "花蓮縣": "花蓮市",
            "台東縣": "台東市", "澎湖縣": "馬公市", "金門縣": "金城鎮",
            "連江縣": "南竿鄉"
        }
        
        town_name = main_towns.get(city_name)
        if not town_name:
            return {"probability": "N/A", "source": f"未支援的地區: {city_name}"}
        
        # 調用現有的鄉鎮天氣預報函數
        weather_data = get_township_weather_data(town_name, city_name)
        
        return {
            "probability": weather_data.get('pop', 'N/A'),
            "source": f"{city_name}{town_name}",
            "location": weather_data.get('locationName', town_name)
        }
        
    except Exception as e:
        print(f"獲取降雨機率失敗: {e}")
        return {"probability": "N/A", "source": "查詢失敗", "error": str(e)}

def get_city_from_coordinates(latitude, longitude):
    """
    根據經緯度簡單判斷所屬縣市
    基於台灣縣市中心點座標，設定合理的範圍來判斷所屬縣市
    :param latitude: 緯度
    :param longitude: 經度
    :return: 縣市名稱
    """
    # 基於台灣縣市中心點座標 (參考 Power Query + Power Map 資料) 設定範圍
    # 省轄市 (優先判斷，避免被直轄市覆蓋)
    if 25.05 <= latitude <= 25.15 and 121.65 <= longitude <= 121.75:  # 基隆市中心: 121.7081, 25.10898 (縮小範圍避免衝突)
        return "基隆市"
    elif 24.75 <= latitude <= 24.85 and 120.85 <= longitude <= 121.05:  # 新竹市中心: 120.9647, 24.80395 (調整經度範圍確保涵蓋巨城百貨)
        return "新竹市"
    elif 23.4 <= latitude <= 23.55 and 120.4 <= longitude <= 120.5:  # 嘉義市中心: 120.4473, 23.47545 (縮小範圍避免衝突)
        return "嘉義市"
    
    # 直轄市 (精確劃分邊界)
    elif 25.0 <= latitude <= 25.25 and 121.45 <= longitude <= 121.65:  # 台北市中心: 121.5598, 25.09108 (縮小東西範圍)
        return "台北市"
    elif ((24.8 <= latitude <= 25.2 and 121.3 <= longitude <= 121.45) or  # 新北市西部 (淡水區域)
          (24.9 <= latitude <= 25.15 and 121.65 <= longitude <= 121.9)):  # 新北市東部 (九份區域)
        return "新北市"
    elif 24.8 <= latitude <= 25.1 and 121.15 <= longitude <= 121.4:  # 桃園市中心: 121.2168, 24.93759 (調整經度範圍避免與新竹市衝突)
        return "桃園市"
    elif 24.0 <= latitude <= 24.45 and 120.4 <= longitude <= 121.2:  # 台中市中心: 120.9417, 24.23321 (縮小東邊範圍避免與花蓮衝突)
        return "台中市"
    elif 22.95 <= latitude <= 23.35 and 120.05 <= longitude <= 120.45:  # 台南市中心: 120.2513, 23.1417
        return "台南市"
    elif 22.55 <= latitude <= 23.15 and 120.25 <= longitude <= 120.85:  # 高雄市中心: 120.666, 23.01087
        return "高雄市"
    
    # 縣 (精確劃分避免重疊)
    elif 24.55 <= latitude <= 24.74 and 121.1 <= longitude <= 121.3:  # 新竹縣中心: 121.1252, 24.70328 (調整避免與新竹市重疊)
        return "新竹縣"
    elif 24.35 <= latitude <= 24.65 and 120.7 <= longitude <= 120.84:  # 苗栗縣中心: 120.9417, 24.48927 (調整避免與新竹市衝突)
        return "苗栗縣"
    elif 23.85 <= latitude <= 24.15 and 120.35 <= longitude <= 120.65:  # 彰化縣中心: 120.4818, 23.99297 (縮小範圍)
        return "彰化縣"
    elif 23.7 <= latitude <= 24.0 and 120.85 <= longitude <= 121.15:  # 南投縣中心: 120.9876, 23.83876 (調整避免衝突)
        return "南投縣"
    elif 23.6 <= latitude <= 23.85 and 120.25 <= longitude <= 120.55:  # 雲林縣中心: 120.3897, 23.75585 (調整避免衝突)
        return "雲林縣"
    elif 23.25 <= latitude <= 23.65 and 120.45 <= longitude <= 120.75:  # 嘉義縣中心: 120.574, 23.45889 (調整避免與嘉義市衝突)
        return "嘉義縣"
    elif 22.4 <= latitude <= 22.75 and 120.45 <= longitude <= 120.85:  # 屏東縣中心: 120.62, 22.54951
        return "屏東縣"
    elif 24.55 <= latitude <= 24.85 and 121.6 <= longitude <= 121.85:  # 宜蘭縣中心: 121.7195, 24.69295
        return "宜蘭縣"
    elif 23.6 <= latitude <= 24.3 and 121.25 <= longitude <= 121.55:  # 花蓮縣中心: 121.3542, 23.7569 (調整範圍包含太魯閣但不與台中衝突)
        return "花蓮縣"
    elif 22.65 <= latitude <= 23.15 and 120.85 <= longitude <= 121.15:  # 台東縣中心: 120.9876, 22.98461 (擴大南邊範圍包含知本溫泉)
        return "台東縣"
    elif 23.4 <= latitude <= 23.8 and 119.4 <= longitude <= 119.9:  # 澎湖縣中心: 119.6151, 23.56548
        return "澎湖縣"
    elif 24.2 <= latitude <= 24.7 and 118.1 <= longitude <= 118.5:  # 金門縣中心: 118.3186, 24.43679
        return "金門縣"
    elif 26.0 <= latitude <= 26.4 and 119.3 <= longitude <= 119.8:  # 連江縣中心: 119.5397, 26.19737
        return "連江縣"
    else:
        # 無法識別的座標，返回 None 而不是隨意猜測
        return None
