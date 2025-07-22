#!/usr/bin/env python3
"""
流汗指數查詢工具
使用方法：python query_sweat_index.py "地點名稱"
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.sweat_index import query_sweat_index_by_location

def print_colored_text(text, color_code):
    """在終端機中列印彩色文字"""
    colors = {
        'green': '\033[92m',
        'yellow': '\033[93m',
        'orange': '\033[91m',
        'red': '\033[91m',
        'reset': '\033[0m',
        'blue': '\033[94m',
        'cyan': '\033[96m'
    }
    print(f"{colors.get(color_code, '')}{text}{colors['reset']}")

def main():
    if len(sys.argv) < 2:
        print("🌡️  流汗指數查詢工具")
        print("=" * 50)
        print("使用方法：python query_sweat_index.py \"地點名稱\"")
        print("\n範例：")
        print("  python query_sweat_index.py \"台北101\"")
        print("  python query_sweat_index.py \"25.034,121.5645\"")
        print("  python query_sweat_index.py \"高雄車站\"")
        return
    
    location = " ".join(sys.argv[1:])
    
    print(f"🌡️  查詢地點：{location}")
    print("=" * 60)
    
    try:
        result = query_sweat_index_by_location(location)
        
        if result is None:
            print_colored_text("❌ 找不到該地點或查詢失敗", 'red')
            return
        
        # 解析結果
        data = result
        
        # 檢查是否有錯誤
        if 'error' in data:
            print_colored_text(f"❌ {data['error']}", 'red')
            if 'details' in data:
                if isinstance(data['details'], dict):
                    print_colored_text(f"   詳細資訊: {data['details'].get('message', '未知錯誤')}", 'red')
                else:
                    print_colored_text(f"   詳細資訊: {data['details']}", 'red')
            
            if 'coordinates' in data:
                coords = data['coordinates']
                print_colored_text(f"📍 座標：{coords['latitude']}, {coords['longitude']}", 'blue')
            
            print()
            print_colored_text("💡 解決方案:", 'cyan')
            print("   1. 執行 'python setup_api_key.py' 設置中央氣象署API金鑰")
            print("   2. 確認網路連線正常")
            print("   3. 確認API金鑰有效且已授權「自動氣象站」資料")
            return
        
        comfort_level = data['comfort_level']
        
        # 處理舒適度資料格式
        if isinstance(comfort_level, dict):
            comfort_level_text = comfort_level.get('level', '未知')
        else:
            comfort_level_text = comfort_level
            
        color_map = {
            '非常舒適': 'green',
            '舒適': 'green',
            '普通': 'yellow', 
            '不舒適': 'orange',
            '非常不舒適': 'red'
        }
        color = color_map.get(comfort_level_text, 'reset')
        
        # 顯示天氣資訊
        print_colored_text("🌤️  天氣條件：", 'cyan')
        print(f"   📍 地點：{data['location']}")
        print(f"   🌡️  溫度：{data['temperature']}°C")
        print(f"   💧 濕度：{data['humidity']}%")
        print(f"   🌬️  風速：{data['wind_speed']} m/s")
        print(f"   🔥 體感溫度：{data['heat_index']:.1f}°C")
        
        if data.get('weather_source', {}).get('is_real_data', False):
            station_name = data['weather_source'].get('station_name', '未知測站')
            distance = data['weather_source'].get('distance_km', 0)
            print_colored_text(f"   📡 資料來源：{station_name} (距離約 {distance:.1f}公里)", 'green')
        else:
            print_colored_text("   ⚠️  無法獲取真實天氣資料", 'yellow')
        
        print()
        
        # 顯示流汗指數
        print_colored_text("💧 流汗指數分析：", 'cyan')
        print(f"   📊 流汗指數：{data['sweat_index']:.1f}/10")
        print_colored_text(f"   😊 舒適度：{comfort_level_text}", color)
        print(f"   🏃 戶外舒適度：{data['outdoor_comfort_score']:.1f}/10")
        
        print()
        
        # 顯示用餐建議
        print_colored_text("🍽️  用餐建議：", 'cyan')
        print(f"   🪑 座位偏好：{data['venue_preference']}")
        print(f"   🏢 場所建議：{data['venue_advice']}")
        print(f"   🥤 飲品建議：{data['drink_advice']}")
        
        print()
        if 'coordinates' in data:
            coords = data['coordinates']
            print_colored_text(f"📍 座標：{coords['latitude']}, {coords['longitude']}", 'blue')
        
    except Exception as e:
        print_colored_text(f"❌ 查詢失敗：{str(e)}", 'red')

if __name__ == "__main__":
    main()
