"""
服務模組初始化
"""
# 延遲載入服務，避免初始化時的錯誤
def get_weather_service():
    from .weather_service import weather_service
    return weather_service

def get_google_maps_service():
    from .google_maps_service import google_maps_service
    return google_maps_service

def get_conversation_service():
    from .conversation_service import conversation_service
    return conversation_service

def get_recommendation_engine():
    from .recommendation_engine import recommendation_engine
    return recommendation_engine

__all__ = [
    "get_weather_service",
    "get_google_maps_service", 
    "get_conversation_service",
    "get_recommendation_engine"
]
