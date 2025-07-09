"""
推薦引擎 - 核心推薦邏輯
"""
from typing import List, Dict, Any
import math
from src.models import (
    Restaurant, Recommendation, UserLocation, WeatherCondition, 
    CrowdLevel, PriceLevel, RestaurantFeatures, SweatIndex
)
from src.services.weather_service import weather_service
from src.services.google_maps_service import google_maps_service
from src.services.conversation_service import conversation_service

class RecommendationEngine:
    """推薦引擎"""
    
    def __init__(self):
        self.weights = {
            "distance": 0.25,
            "rating": 0.20,
            "weather_suitability": 0.15,
            "price_match": 0.15,
            "crowd_preference": 0.10,
            "cuisine_preference": 0.10,
            "special_features": 0.05
        }
    
    async def generate_recommendations(
        self,
        restaurants: List[Restaurant],
        user_location: UserLocation,
        weather: WeatherCondition,
        user_preferences: Dict[str, Any]
    ) -> List[Recommendation]:
        """產生推薦清單"""
        
        recommendations = []
        
        for restaurant in restaurants:
            # 計算距離
            distance = self._calculate_distance(user_location, restaurant)
            
            # 取得餐廳評論並分析特徵
            reviews = await google_maps_service.get_restaurant_reviews(restaurant.place_id)
            review_analysis = await conversation_service.analyze_review_sentiment(reviews)
            
            # 建立餐廳特徵
            features = self._build_restaurant_features(restaurant, review_analysis)
            
            # 計算流汗指數
            sweat_score = weather_service.calculate_sweat_index(weather, distance)
            sweat_index = SweatIndex(
                score=sweat_score,
                factors={
                    "temperature": weather.temperature,
                    "humidity": weather.humidity,
                    "distance": distance,
                    "wind_speed": weather.wind_speed
                },
                recommendation=self._get_sweat_recommendation(sweat_score)
            )
            
            # 計算推薦分數
            score, reasons = self._calculate_score(
                restaurant, features, distance, weather, 
                user_preferences, sweat_index
            )
            
            # 估算人潮
            estimated_crowd = self._estimate_crowd_level(restaurant, weather)
            
            recommendation = Recommendation(
                restaurant=restaurant,
                features=features,
                score=score,
                reasons=reasons,
                distance=distance,
                estimated_crowd=estimated_crowd,
                sweat_index=sweat_index
            )
            
            recommendations.append(recommendation)
        
        # 依分數排序
        recommendations.sort(key=lambda x: x.score, reverse=True)
        
        return recommendations[:10]  # 返回前10個推薦
    
    def _calculate_distance(self, user_location: UserLocation, restaurant: Restaurant) -> float:
        """計算距離 (公尺)"""
        lat1, lon1 = math.radians(user_location.latitude), math.radians(user_location.longitude)
        lat2, lon2 = math.radians(restaurant.latitude), math.radians(restaurant.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # 地球半徑 (公尺)
        r = 6371000
        
        return c * r
    
    def _build_restaurant_features(
        self, 
        restaurant: Restaurant, 
        review_analysis: Dict[str, Any]
    ) -> RestaurantFeatures:
        """建立餐廳特徵"""
        features_data = review_analysis.get("features", {})
        
        return RestaurantFeatures(
            place_id=restaurant.place_id,
            has_strong_ac=features_data.get("air_conditioning") == "strong",
            good_for_date=features_data.get("good_for_date", False),
            family_friendly=features_data.get("family_friendly", False),
            quick_service=features_data.get("quick_service", False),
            noise_level=self._map_noise_level(features_data.get("noise_level", "moderate"))
        )
    
    def _map_noise_level(self, noise_str: str) -> CrowdLevel:
        """對應噪音等級到人潮等級"""
        mapping = {
            "quiet": CrowdLevel.QUIET,
            "moderate": CrowdLevel.MODERATE,
            "noisy": CrowdLevel.BUSY,
            "very_noisy": CrowdLevel.VERY_BUSY
        }
        return mapping.get(noise_str, CrowdLevel.MODERATE)
    
    def _calculate_score(
        self,
        restaurant: Restaurant,
        features: RestaurantFeatures,
        distance: float,
        weather: WeatherCondition,
        user_preferences: Dict[str, Any],
        sweat_index: SweatIndex
    ) -> tuple[float, List[str]]:
        """計算推薦分數"""
        score = 0.0
        reasons = []
        
        # 1. 距離分數 (越近越好)
        distance_score = max(0, 1 - (distance / 1000))  # 1公里內滿分
        score += self.weights["distance"] * distance_score
        if distance <= 300:
            reasons.append(f"距離很近 ({int(distance)}公尺)")
        
        # 2. 評分分數
        if restaurant.rating:
            rating_score = restaurant.rating / 5.0
            score += self.weights["rating"] * rating_score
            if restaurant.rating >= 4.0:
                reasons.append(f"評價很好 ({restaurant.rating}★)")
        
        # 3. 天氣適合度
        weather_score = self._calculate_weather_suitability(weather, features, sweat_index)
        score += self.weights["weather_suitability"] * weather_score
        if weather_score > 0.7:
            reasons.append("天氣條件很適合")
        
        # 4. 價格匹配度
        budget_pref = user_preferences.get("budget")
        if budget_pref and restaurant.price_level:
            price_score = 1.0 if budget_pref == restaurant.price_level.value else 0.5
            score += self.weights["price_match"] * price_score
            if price_score == 1.0:
                reasons.append("符合預算範圍")
        
        # 5. 人潮偏好
        crowd_pref = user_preferences.get("crowd_preference")
        if crowd_pref:
            crowd_score = self._match_crowd_preference(crowd_pref, features.noise_level)
            score += self.weights["crowd_preference"] * crowd_score
        
        # 6. 料理偏好
        cuisine_prefs = user_preferences.get("cuisine_preferences", [])
        if cuisine_prefs:
            cuisine_score = self._match_cuisine_preference(cuisine_prefs, restaurant.cuisine_type)
            score += self.weights["cuisine_preference"] * cuisine_score
            if cuisine_score > 0:
                reasons.append("符合料理偏好")
        
        # 7. 特殊功能加分
        special_reqs = user_preferences.get("special_requirements", [])
        special_score = self._calculate_special_features_score(special_reqs, features)
        score += self.weights["special_features"] * special_score
        
        return min(score, 1.0), reasons
    
    def _calculate_weather_suitability(
        self,
        weather: WeatherCondition,
        features: RestaurantFeatures,
        sweat_index: SweatIndex
    ) -> float:
        """計算天氣適合度"""
        score = 1.0
        
        # 高溫情況下，冷氣強的餐廳加分
        if weather.temperature > 28 and features.has_strong_ac:
            score += 0.3
        
        # 流汗指數高的時候，距離近的餐廳加分
        if sweat_index.score > 6:
            score *= 0.8  # 稍微扣分
        
        # 下雨機率高，室內餐廳較佳
        if weather.rain_probability > 70:
            score += 0.2
        
        return min(score, 1.0)
    
    def _match_crowd_preference(self, preference: str, actual: CrowdLevel) -> float:
        """匹配人潮偏好"""
        pref_map = {
            "quiet": CrowdLevel.QUIET,
            "moderate": CrowdLevel.MODERATE,
            "busy": CrowdLevel.BUSY,
            "very_busy": CrowdLevel.VERY_BUSY
        }
        
        preferred = pref_map.get(preference, CrowdLevel.MODERATE)
        return 1.0 if preferred == actual else 0.5
    
    def _match_cuisine_preference(self, preferences: List[str], restaurant_types: List[str]) -> float:
        """匹配料理偏好"""
        if not preferences or not restaurant_types:
            return 0.5
        
        matches = len(set(preferences) & set(restaurant_types))
        return min(matches / len(preferences), 1.0)
    
    def _calculate_special_features_score(
        self, 
        requirements: List[str], 
        features: RestaurantFeatures
    ) -> float:
        """計算特殊需求分數"""
        score = 0.0
        
        for req in requirements:
            if req == "約會" and features.good_for_date:
                score += 0.5
            elif req == "家庭聚餐" and features.family_friendly:
                score += 0.5
            elif req == "快速用餐" and features.quick_service:
                score += 0.5
        
        return min(score, 1.0)
    
    def _estimate_crowd_level(self, restaurant: Restaurant, weather: WeatherCondition) -> CrowdLevel:
        """估算人潮等級"""
        # 簡化的人潮估算邏輯
        base_level = CrowdLevel.MODERATE
        
        # 評分高的餐廳通常人較多
        if restaurant.rating and restaurant.rating >= 4.5:
            if base_level == CrowdLevel.MODERATE:
                base_level = CrowdLevel.BUSY
        
        # 天氣不好時人潮較少
        if weather.rain_probability > 50 or weather.temperature < 10:
            if base_level == CrowdLevel.BUSY:
                base_level = CrowdLevel.MODERATE
            elif base_level == CrowdLevel.MODERATE:
                base_level = CrowdLevel.QUIET
        
        return base_level
    
    def _get_sweat_recommendation(self, sweat_score: float) -> str:
        """取得流汗指數建議"""
        if sweat_score <= 3:
            return "天氣舒適，適合步行用餐"
        elif sweat_score <= 6:
            return "稍微會流汗，建議選擇較近的餐廳"
        elif sweat_score <= 8:
            return "容易流汗，建議選擇有冷氣的餐廳"
        else:
            return "天氣炎熱，建議外送或選擇最近的冷氣餐廳"

# 全域推薦引擎實例
recommendation_engine = RecommendationEngine()
