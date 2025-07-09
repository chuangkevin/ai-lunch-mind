"""
餐廳推薦服務
根據天氣條件推薦合適的餐廳類型
"""

class RestaurantRecommender:
    """餐廳推薦器"""
    
    def __init__(self):
        """初始化推薦器"""
        self.recommendations = {
            "hot": [
                {"name": "涼麵店", "reason": "天氣炎熱，適合吃清爽的涼麵"},
                {"name": "冰品店", "reason": "高溫天氣，來點冰涼甜品消暑"},
                {"name": "輕食咖啡廳", "reason": "炎熱天氣適合清淡飲食"},
                {"name": "日式料理", "reason": "清爽的日式料理適合夏日"}
            ],
            "cold": [
                {"name": "火鍋店", "reason": "寒冷天氣最適合熱騰騰的火鍋"},
                {"name": "拉麵店", "reason": "冷天喝碗熱湯麵暖身又暖心"},
                {"name": "薑母鴨", "reason": "寒流來襲，進補暖身的好選擇"},
                {"name": "韓式料理", "reason": "韓式熱湯料理適合寒冷天氣"}
            ],
            "rainy": [
                {"name": "室內美食廣場", "reason": "下雨天避免外出，選擇室內用餐"},
                {"name": "便當店", "reason": "雨天適合外送或快速取餐"},
                {"name": "咖啡廳", "reason": "雨天在咖啡廳享受悠閒時光"},
                {"name": "港式飲茶", "reason": "雨天適合在室內慢慢品茶用餐"}
            ],
            "windy": [
                {"name": "室內餐廳", "reason": "風大時選擇室內用餐較舒適"},
                {"name": "地下街美食", "reason": "避開戶外強風，地下街是好選擇"},
                {"name": "百貨美食街", "reason": "風大天氣適合在室內商場用餐"},
                {"name": "速食店", "reason": "快速用餐，減少戶外停留時間"}
            ],
            "default": [
                {"name": "小吃攤", "reason": "天氣宜人，適合到戶外小吃攤覓食"},
                {"name": "公園餐廳", "reason": "好天氣適合在戶外用餐"},
                {"name": "街邊小店", "reason": "舒適的天氣適合探索街邊美食"},
                {"name": "戶外咖啡座", "reason": "天氣好時享受戶外用餐樂趣"}
            ]
        }
    
    def get_recommendations(self, weather_data):
        """
        根據天氣資料推薦餐廳
        
        Args:
            weather_data: 天氣資料字典
            
        Returns:
            list: 推薦餐廳列表
        """
        try:
            temperature = float(weather_data.get('temperature', '25').replace('°C', ''))
            condition = weather_data.get('condition', '').lower()
            wind_speed = weather_data.get('wind_speed', '0')
            
            # 根據天氣條件決定推薦類型
            if '雨' in condition or '雷' in condition:
                category = "rainy"
            elif temperature >= 30:
                category = "hot"
            elif temperature <= 15:
                category = "cold"
            elif any(keyword in str(wind_speed) for keyword in ['強風', '大風']) or \
                 (isinstance(wind_speed, str) and any(char.isdigit() for char in wind_speed) and \
                  float(''.join(filter(str.isdigit, wind_speed))) > 15):
                category = "windy"
            else:
                category = "default"
            
            return self.recommendations.get(category, self.recommendations["default"])
            
        except Exception as e:
            print(f"推薦系統錯誤: {e}")
            return self.recommendations["default"]
