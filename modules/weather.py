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
        "宜蘭縣": "001", "桃園市": "005", "新竹縣": "009", "苗栗縣": "013", "彰化縣": "017", "南投縣": "021", "雲林縣": "025", "嘉義縣": "029", "屏東縣": "033", "臺東縣": "037", "花蓮縣": "041", "澎湖縣": "045", "基隆市": "049", "新竹市": "053", "嘉義市": "057", "臺北市": "061", "高雄市": "065", "新北市": "069", "臺中市": "073", "臺南市": "077", "連江縣": "081", "金門縣": "085", "臺北市": "061", "高雄市": "065"
    }
    # city_name 必須正確，否則 fallback 用宜蘭縣
    code = city_code_map.get(city_name, "001")
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-{code}?Authorization={api_key}&format=JSON"
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.raise_for_status()
        data = resp.json()
        print(f"[DEBUG] records: {data.get('records')}")
        # 正確 key: 'Locations' -> [0] -> 'Location'
        locations = data.get('records', {}).get('Locations', [{}])[0].get('Location', [])
        all_names = [loc.get('LocationName') for loc in locations]
        print(f"[DEBUG] {city_name} 可用鄉鎮市區: {all_names}")
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
                pop = 'N/A'
                if '3小時降雨機率' in weather_elements:
                    pop_times = weather_elements['3小時降雨機率'].get('Time', [])
                    if pop_times:
                        pop = pop_times[0].get('ElementValue', [{}])[0].get('ProbabilityOfPrecipitation', 'N/A')
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
from dotenv import load_dotenv

# 加載 .env 檔案中的環境變數
load_dotenv()

def get_weather_data(latitude, longitude):
    """
    根據經緯度查詢最近的氣象站天氣資料。
    :param latitude: float, 緯度
    :param longitude: float, 經度
    :return: dict, 包含氣溫、濕度、降雨機率的天氣資料
    """
    api_key = os.getenv("CWB_API_KEY")
    if not api_key:
        raise ValueError("中央氣象署 API 金鑰未設置")

    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001?Authorization={api_key}&locationName=&elementName=TEMP,HUMD,RAIN&parameterName=LAT,LON"
    try:
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        # TODO: 根據經緯度篩選最近的氣象站資料
        return data
    except requests.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return {}

# TODO: 添加更多天氣分析功能
