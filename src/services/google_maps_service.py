"""
Google Maps 服務模組
整合 Places API
"""
import googlemaps
from typing import List, Optional, Dict, Any
from src.config import settings
from src.models import Restaurant, Review, UserLocation, PriceLevel

class GoogleMapsService:
    """Google Maps 服務"""
    
    def __init__(self):
        self.client = googlemaps.Client(key=settings.google_maps_api_key)
        self.price_level_map = {
            0: PriceLevel.BUDGET,
            1: PriceLevel.BUDGET,
            2: PriceLevel.MODERATE,
            3: PriceLevel.EXPENSIVE,
            4: PriceLevel.LUXURY
        }
    
    async def search_nearby_restaurants(
        self, 
        location: UserLocation, 
        radius: int = None
    ) -> List[Restaurant]:
        """搜尋附近餐廳"""
        radius = radius or settings.search_radius
        
        try:
            # 使用 Places API 搜尋餐廳
            places_result = self.client.places_nearby(
                location=(location.latitude, location.longitude),
                radius=radius,
                type='restaurant',
                language='zh-TW'
            )
            
            restaurants = []
            for place in places_result['results']:
                restaurant = self._parse_place_to_restaurant(place)
                if restaurant:
                    restaurants.append(restaurant)
            
            return restaurants[:settings.max_restaurants]
            
        except Exception as e:
            print(f"餐廳搜尋失敗: {e}")
            return []
    
    async def get_restaurant_details(self, place_id: str) -> Optional[Restaurant]:
        """取得餐廳詳細資訊"""
        try:
            place_details = self.client.place(
                place_id=place_id,
                fields=[
                    'name', 'formatted_address', 'geometry', 'rating',
                    'price_level', 'types', 'formatted_phone_number',
                    'website', 'opening_hours', 'photos', 'reviews'
                ],
                language='zh-TW'
            )
            
            place = place_details['result']
            return self._parse_place_to_restaurant(place, detailed=True)
            
        except Exception as e:
            print(f"餐廳詳情取得失敗: {e}")
            return None
    
    async def get_restaurant_reviews(self, place_id: str) -> List[Review]:
        """取得餐廳評論"""
        try:
            place_details = self.client.place(
                place_id=place_id,
                fields=['reviews'],
                language='zh-TW'
            )
            
            reviews = []
            if 'reviews' in place_details['result']:
                for review_data in place_details['result']['reviews']:
                    review = Review(
                        author_name=review_data.get('author_name', ''),
                        rating=review_data.get('rating', 0),
                        text=review_data.get('text', ''),
                        time=review_data.get('time', 0)
                    )
                    reviews.append(review)
            
            return reviews
            
        except Exception as e:
            print(f"評論取得失敗: {e}")
            return []
    
    def _parse_place_to_restaurant(self, place: Dict[str, Any], detailed: bool = False) -> Optional[Restaurant]:
        """解析 Google Place 資料為 Restaurant 物件"""
        try:
            geometry = place.get('geometry', {}).get('location', {})
            
            restaurant = Restaurant(
                place_id=place['place_id'],
                name=place.get('name', ''),
                address=place.get('formatted_address', place.get('vicinity', '')),
                latitude=geometry.get('lat', 0),
                longitude=geometry.get('lng', 0),
                rating=place.get('rating'),
                price_level=self.price_level_map.get(place.get('price_level')),
                cuisine_type=self._extract_cuisine_types(place.get('types', [])),
                phone=place.get('formatted_phone_number'),
                website=place.get('website')
            )
            
            # 詳細資訊處理
            if detailed:
                # 營業時間
                if 'opening_hours' in place:
                    restaurant.opening_hours = {
                        'periods': place['opening_hours'].get('periods', []),
                        'weekday_text': place['opening_hours'].get('weekday_text', [])
                    }
                
                # 照片
                if 'photos' in place:
                    restaurant.photos = [
                        f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo['photo_reference']}&key={settings.google_maps_api_key}"
                        for photo in place['photos'][:5]  # 最多5張照片
                    ]
            
            return restaurant
            
        except Exception as e:
            print(f"餐廳資料解析失敗: {e}")
            return None
    
    def _extract_cuisine_types(self, types: List[str]) -> List[str]:
        """擷取料理類型"""
        cuisine_mapping = {
            'chinese_restaurant': '中式',
            'japanese_restaurant': '日式',
            'korean_restaurant': '韓式',
            'italian_restaurant': '義式',
            'american_restaurant': '美式',
            'thai_restaurant': '泰式',
            'vietnamese_restaurant': '越式',
            'indian_restaurant': '印度菜',
            'mexican_restaurant': '墨西哥菜',
            'fast_food': '速食',
            'cafe': '咖啡廳',
            'bakery': '烘焙坊',
            'bar': '酒吧'
        }
        
        cuisines = []
        for place_type in types:
            if place_type in cuisine_mapping:
                cuisines.append(cuisine_mapping[place_type])
        
        return cuisines if cuisines else ['餐廳']

# 全域服務實例
google_maps_service = GoogleMapsService()
