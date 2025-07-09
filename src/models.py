"""
資料模型定義
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class PriceLevel(Enum):
    """價格等級"""
    BUDGET = "budget"      # 平價 ($)
    MODERATE = "moderate"  # 中等 ($$)
    EXPENSIVE = "expensive" # 昂貴 ($$$)
    LUXURY = "luxury"      # 奢華 ($$$$)

class CrowdLevel(Enum):
    """人潮等級"""
    QUIET = "quiet"
    MODERATE = "moderate"
    BUSY = "busy"
    VERY_BUSY = "very_busy"

class WeatherCondition(BaseModel):
    """天氣狀況"""
    temperature: float
    humidity: float
    rain_probability: float
    wind_speed: float
    description: str
    
class UserLocation(BaseModel):
    """使用者位置"""
    latitude: float
    longitude: float
    address: Optional[str] = None

class UserPreferences(BaseModel):
    """使用者偏好"""
    budget_range: List[PriceLevel]
    cuisine_types: List[str]
    crowd_preference: CrowdLevel
    weather_sensitive: bool = True
    distance_tolerance: int = 500  # meters
    dietary_restrictions: List[str] = []

class UserQuery(BaseModel):
    """使用者查詢"""
    text: str
    location: UserLocation
    preferences: Optional[UserPreferences] = None
    timestamp: datetime = datetime.now()

class Restaurant(BaseModel):
    """餐廳資訊"""
    place_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    rating: Optional[float] = None
    price_level: Optional[PriceLevel] = None
    cuisine_type: List[str] = []
    phone: Optional[str] = None
    website: Optional[str] = None
    opening_hours: Optional[Dict[str, str]] = None
    photos: List[str] = []
    
class RestaurantFeatures(BaseModel):
    """餐廳特徵分析"""
    place_id: str
    has_strong_ac: bool = False
    has_outdoor_seating: bool = False
    good_for_date: bool = False
    family_friendly: bool = False
    quick_service: bool = False
    parking_available: bool = False
    noise_level: CrowdLevel = CrowdLevel.MODERATE
    
class Review(BaseModel):
    """評論資訊"""
    author_name: str
    rating: int
    text: str
    time: datetime
    
class SweatIndex(BaseModel):
    """流汗指數"""
    score: float  # 0-10
    factors: Dict[str, float]
    recommendation: str

class Recommendation(BaseModel):
    """推薦結果"""
    restaurant: Restaurant
    features: RestaurantFeatures
    score: float
    reasons: List[str]
    distance: float
    estimated_crowd: CrowdLevel
    sweat_index: SweatIndex
    
class RecommendationResponse(BaseModel):
    """推薦回應"""
    recommendations: List[Recommendation]
    explanation: str
    weather_info: WeatherCondition
    total_count: int
