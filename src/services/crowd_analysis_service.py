"""
人潮分析服務模組 - 增強版
結合多種因子進行人潮預測
"""
import datetime
from typing import Dict, List, Optional, Tuple
from src.models import Restaurant, WeatherCondition, CrowdLevel, UserLocation
from src.config import settings

class CrowdAnalysisService:
    """人潮分析服務 - 增強版"""
    
    def __init__(self):
        # 時段人潮權重 (24小時制)
        self.hourly_crowd_weights = {
            # 早餐時段 (6-10)
            6: 0.3, 7: 0.5, 8: 0.7, 9: 0.6, 10: 0.4,
            # 午餐時段 (11-14) - 高峰
            11: 0.7, 12: 1.0, 13: 0.9, 14: 0.6,
            # 下午茶 (15-17)
            15: 0.4, 16: 0.5, 17: 0.6,
            # 晚餐時段 (18-21) - 高峰
            18: 0.8, 19: 1.0, 20: 0.9, 21: 0.7,
            # 宵夜時段 (22-24)
            22: 0.5, 23: 0.3, 0: 0.2, 1: 0.1
        }
        
        # 星期權重 (週一=0, 週日=6)
        self.weekday_weights = {
            0: 0.7, 1: 0.8, 2: 0.8, 3: 0.8, 4: 0.9,  # 週一到週五
            5: 1.2, 6: 1.0  # 週六、週日
        }
        
        # 天氣影響權重
        self.weather_impact = {
            'rain_high': 0.6,      # 大雨
            'rain_medium': 0.8,    # 中雨
            'rain_low': 0.9,       # 小雨
            'hot_weather': 0.7,    # 炎熱天氣
            'cold_weather': 0.8,   # 寒冷天氣
            'comfortable': 1.0     # 舒適天氣
        }
    
    def estimate_crowd_level(
        self, 
        restaurant: Restaurant, 
        weather: WeatherCondition,
        query_time: Optional[datetime.datetime] = None
    ) -> Tuple[CrowdLevel, float, str]:
        """
        估算餐廳人潮等級
        
        Returns:
            Tuple[CrowdLevel, confidence_score, reason]
        """
        if query_time is None:
            query_time = datetime.datetime.now()
        
        # 基礎人潮分數 (0-1)
        base_score = 0.5
        reasons = []
        
        # 1. 餐廳評分影響 (25%)
        rating_score = self._calculate_rating_impact(restaurant)
        base_score += rating_score * 0.25
        if rating_score > 0.2:
            reasons.append(f"高評分餐廳 ({restaurant.rating:.1f}⭐)")
        
        # 2. 時間因子影響 (30%)
        time_score = self._calculate_time_impact(query_time)
        base_score *= time_score
        if time_score > 0.8:
            reasons.append("用餐高峰時段")
        elif time_score < 0.4:
            reasons.append("非用餐時段")
        
        # 3. 天氣影響 (20%)
        weather_score = self._calculate_weather_impact(weather)
        base_score *= weather_score
        if weather_score < 0.8:
            reasons.append("天氣影響人潮")
        
        # 4. 餐廳類型影響 (15%)
        cuisine_score = self._calculate_cuisine_impact(restaurant)
        base_score += cuisine_score * 0.15
        
        # 5. 價位影響 (10%)
        price_score = self._calculate_price_impact(restaurant)
        base_score += price_score * 0.1
        
        # 轉換為等級
        crowd_level = self._score_to_level(base_score)
        confidence = min(0.85, 0.6 + len(reasons) * 0.1)  # 信心度
        
        reason_text = " | ".join(reasons) if reasons else "基於綜合因子估算"
        
        return crowd_level, confidence, reason_text
    
    def _calculate_rating_impact(self, restaurant: Restaurant) -> float:
        """計算評分對人潮的影響"""
        if not restaurant.rating:
            return 0.0
        
        # 評分越高，人潮越多
        if restaurant.rating >= 4.5:
            return 0.4  # 高評分 = 高人潮
        elif restaurant.rating >= 4.0:
            return 0.2
        elif restaurant.rating >= 3.5:
            return 0.0
        else:
            return -0.1  # 低評分 = 低人潮
    
    def _calculate_time_impact(self, query_time: datetime.datetime) -> float:
        """計算時間對人潮的影響"""
        hour = query_time.hour
        weekday = query_time.weekday()
        
        # 時段權重
        hour_weight = self.hourly_crowd_weights.get(hour, 0.3)
        
        # 星期權重
        weekday_weight = self.weekday_weights.get(weekday, 0.8)
        
        return hour_weight * weekday_weight
    
    def _calculate_weather_impact(self, weather: WeatherCondition) -> float:
        """計算天氣對人潮的影響"""
        # 降雨影響
        if weather.rain_probability > 70:
            return self.weather_impact['rain_high']
        elif weather.rain_probability > 40:
            return self.weather_impact['rain_medium']
        elif weather.rain_probability > 20:
            return self.weather_impact['rain_low']
        
        # 溫度影響
        if weather.temperature > 35:
            return self.weather_impact['hot_weather']
        elif weather.temperature < 5:
            return self.weather_impact['cold_weather']
        
        return self.weather_impact['comfortable']
    
    def _calculate_cuisine_impact(self, restaurant: Restaurant) -> float:
        """計算料理類型對人潮的影響"""
        cuisine_popularity = {
            '火鍋': 0.3,      # 火鍋店通常人較多
            '燒烤': 0.3,      # 燒烤店聚餐熱門
            '日式': 0.2,      # 日式料理較受歡迎
            '韓式': 0.2,      # 韓式料理較受歡迎
            '速食': -0.1,     # 速食翻桌快
            '咖啡廳': 0.1,    # 咖啡廳適中
            '中式': 0.0,      # 中式料理基準
        }
        
        if not restaurant.cuisine_type:
            return 0.0
        
        for cuisine in restaurant.cuisine_type:
            if cuisine in cuisine_popularity:
                return cuisine_popularity[cuisine]
        
        return 0.0
    
    def _calculate_price_impact(self, restaurant: Restaurant) -> float:
        """計算價位對人潮的影響"""
        price_impact = {
            'budget': 0.1,      # 平價餐廳人潮多
            'moderate': 0.0,    # 中等價位基準
            'expensive': -0.1,  # 高價餐廳人較少
            'luxury': -0.2      # 奢華餐廳人更少
        }
        
        if restaurant.price_level:
            return price_impact.get(restaurant.price_level.value, 0.0)
        
        return 0.0
    
    def _score_to_level(self, score: float) -> CrowdLevel:
        """將分數轉換為人潮等級"""
        if score >= 0.8:
            return CrowdLevel.VERY_BUSY
        elif score >= 0.6:
            return CrowdLevel.BUSY
        elif score >= 0.4:
            return CrowdLevel.MODERATE
        else:
            return CrowdLevel.QUIET
    
    def get_crowd_trend_prediction(
        self, 
        restaurant: Restaurant, 
        weather: WeatherCondition
    ) -> Dict[str, CrowdLevel]:
        """預測接下來幾個時段的人潮趨勢"""
        now = datetime.datetime.now()
        predictions = {}
        
        for i in range(4):  # 預測接下來4小時
            future_time = now + datetime.timedelta(hours=i)
            crowd_level, _, _ = self.estimate_crowd_level(restaurant, weather, future_time)
            time_label = future_time.strftime("%H:%M")
            predictions[time_label] = crowd_level
        
        return predictions
    
    def get_best_visit_times(
        self, 
        restaurant: Restaurant, 
        weather: WeatherCondition
    ) -> List[Tuple[str, CrowdLevel]]:
        """建議最佳造訪時間"""
        now = datetime.datetime.now()
        time_options = []
        
        # 檢查今天剩餘時間和明天
        for day_offset in [0, 1]:
            base_date = now.date() + datetime.timedelta(days=day_offset)
            
            # 營業時間內的每個小時
            for hour in range(11, 22):  # 11:00 - 21:00
                check_time = datetime.datetime.combine(base_date, datetime.time(hour, 0))
                
                # 跳過已過去的時間
                if check_time <= now:
                    continue
                
                crowd_level, _, _ = self.estimate_crowd_level(restaurant, weather, check_time)
                
                day_label = "今天" if day_offset == 0 else "明天"
                time_label = f"{day_label} {hour:02d}:00"
                time_options.append((time_label, crowd_level))
        
        # 按人潮由少到多排序
        crowd_order = {
            CrowdLevel.QUIET: 0,
            CrowdLevel.MODERATE: 1,
            CrowdLevel.BUSY: 2,
            CrowdLevel.VERY_BUSY: 3
        }
        
        time_options.sort(key=lambda x: crowd_order[x[1]])
        return time_options[:6]  # 返回最佳6個時段

# 全域服務實例
crowd_analysis_service = CrowdAnalysisService()
