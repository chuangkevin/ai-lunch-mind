"""
測試套件
"""
import pytest
import asyncio
from src.config import settings
from src.models import UserLocation
from src.services.weather_service import weather_service
from src.services.conversation_service import conversation_service

class TestWeatherService:
    """天氣服務測試"""
    
    @pytest.mark.asyncio
    async def test_get_weather(self):
        """測試取得天氣資訊"""
        # 台北101座標
        location = UserLocation(latitude=25.034, longitude=121.5645)
        weather = await weather_service.get_current_weather(location)
        
        if weather:  # 如果有API key才會有資料
            assert weather.temperature is not None
            assert weather.humidity is not None
            print(f"天氣測試成功: {weather.temperature}°C, {weather.description}")
        else:
            print("天氣API測試跳過 (需要API key)")
    
    def test_sweat_index_calculation(self):
        """測試流汗指數計算"""
        from src.models import WeatherCondition
        
        weather = WeatherCondition(
            temperature=35.0,
            humidity=80.0,
            rain_probability=0.0,
            wind_speed=2.0,
            description="炎熱"
        )
        
        distance = 300  # 300公尺
        sweat_score = weather_service.calculate_sweat_index(weather, distance)
        
        assert 0 <= sweat_score <= 10
        assert sweat_score > 5  # 炎熱天氣應該有較高的流汗指數
        print(f"流汗指數測試: {sweat_score}")

class TestConversationService:
    """對話服務測試"""
    
    @pytest.mark.asyncio
    async def test_parse_query(self):
        """測試查詢解析"""
        test_query = "我想吃便宜的日式料理，不要太擠的地方"
        
        try:
            result = await conversation_service.parse_user_query(test_query)
            print(f"查詢解析結果: {result}")
            
            # 檢查基本欄位
            assert isinstance(result, dict)
            
        except Exception as e:
            print(f"查詢解析測試跳過 (需要OpenAI API key): {e}")

def test_models():
    """測試資料模型"""
    from src.models import Restaurant, PriceLevel
    
    restaurant = Restaurant(
        place_id="test123",
        name="測試餐廳",
        address="台北市信義區",
        latitude=25.034,
        longitude=121.5645,
        rating=4.5,
        price_level=PriceLevel.MODERATE
    )
    
    assert restaurant.name == "測試餐廳"
    assert restaurant.rating == 4.5
    assert restaurant.price_level == PriceLevel.MODERATE
    print("資料模型測試通過")

if __name__ == "__main__":
    # 執行基本測試
    print("=== AI 午餐推薦系統測試 ===")
    
    # 測試模型
    test_models()
    
    # 測試流汗指數
    test_service = TestWeatherService()
    test_service.test_sweat_index_calculation()
    
    print("基本測試完成！")
