#!/usr/bin/env python3
"""
簡單測試推薦功能
"""
import requests
import json

def test_recommend():
    """測試推薦端點"""
    test_data = {
        "text": "我想找附近好吃的中式餐廳",
        "location": {
            "latitude": 25.0330,
            "longitude": 121.5654,
            "address": "台北市信義區"
        }
    }
    
    try:
        print("發送請求到 /recommend...")
        response = requests.post(
            "http://localhost:8000/recommend",
            headers={"Content-Type": "application/json"},
            json=test_data
        )
        print(f"狀態碼: {response.status_code}")
        print(f"回應內容: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n成功！推薦結果:")
            print(f"- 找到 {len(result.get('recommendations', []))} 間餐廳")
            print(f"- AI 說明: {result.get('explanation', '無說明')}")
            if 'weather_info' in result:
                weather = result['weather_info']
                print(f"- 天氣: {weather.get('temperature')}°C, {weather.get('description')}")
        else:
            print(f"\n錯誤: {response.text}")
            
    except Exception as e:
        print(f"請求失敗: {e}")

if __name__ == "__main__":
    test_recommend()
