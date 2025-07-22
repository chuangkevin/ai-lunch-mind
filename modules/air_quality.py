# 流汗指數計算模組
# 基於溫度、濕度、風速等氣象條件計算體感溫度與流汗指數

import math
from typing import Dict, Optional
from datetime import datetime

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
        # 使用簡化的體感溫度公式
        if temp < 27:
            heat_index = temp
        else:
            # Rothfusz regression (適用於溫度 >= 27°C)
            hi = (-42.379 + 
                  2.04901523 * temp + 
                  10.14333127 * humidity - 
                  0.22475541 * temp * humidity - 
                  6.83783e-3 * temp**2 - 
                  5.481717e-2 * humidity**2 + 
                  1.22874e-3 * temp**2 * humidity + 
                  8.5282e-4 * temp * humidity**2 - 
                  1.99e-6 * temp**2 * humidity**2)
            
            heat_index = (hi - 32) * 5/9  # 轉換回攝氏度
        
        # 風速修正（風速越大，體感溫度越低）
        wind_chill_factor = max(0, wind_speed * 2)  # 風速降溫效應
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

def calculate_dining_recommendation(temp: float, humidity: float, wind_speed: float = 0, location: str = "") -> Dict:
    """
    基於天氣條件計算用餐建議
    :param temp: 溫度 (攝氏度)
    :param humidity: 相對濕度 (%)
    :param wind_speed: 風速 (m/s)
    :param location: 地點名稱
    :return: 用餐建議資訊
    """
    try:
        # 計算流汗指數
        sweat_index = estimate_sweat_index(temp, humidity, wind_speed)
        
        # 計算體感溫度
        heat_index = calculate_heat_index(temp, humidity)
        
        # 獲取舒適度等級
        comfort = get_comfort_level(sweat_index)
        
        # 生成用餐場所建議
        if sweat_index <= 3:
            venue_preference = "戶外座位優先"
            venue_advice = "推薦露天餐廳、陽台座位或庭園餐廳"
        elif sweat_index <= 5:
            venue_preference = "戶外室內皆可"
            venue_advice = "可選擇有遮蔭的戶外座位或通風良好的室內"
        elif sweat_index <= 7:
            venue_preference = "室內座位建議"
            venue_advice = "建議室內用餐，如選擇戶外需有冷氣或風扇"
        else:
            venue_preference = "室內座位強烈建議"
            venue_advice = "強烈建議冷氣房用餐，避免戶外座位"
        
        # 生成飲品建議
        if sweat_index <= 3:
            drink_advice = "溫熱飲品或常溫飲料"
        elif sweat_index <= 6:
            drink_advice = "冰涼飲品，注意補充水分"
        else:
            drink_advice = "大量冰涼飲品，加強補水"
        
        # 計算戶外舒適度評分 (0-10分，10分最舒適)
        outdoor_comfort_score = max(0, 10 - sweat_index)
        
        return {
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
        
    except Exception as e:
        return {
            "error": f"計算用餐建議失敗: {e}",
            "location": location,
            "temperature": temp,
            "humidity": humidity
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
