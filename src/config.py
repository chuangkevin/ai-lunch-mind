"""
AI 午餐推薦系統 - 核心配置
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """應用程式設定"""
    
    # API Keys
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    google_maps_api_key: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    cwb_api_key: str = os.getenv("CWB_API_KEY", "")  # 中央氣象署 API Key
    
    # Database
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ai_lunch_mind.db")
    
    # App Configuration
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    
    # AI Configuration
    max_tokens: int = int(os.getenv("MAX_TOKENS", "1000"))
    temperature: float = float(os.getenv("TEMPERATURE", "0.7"))
    
    # Search Configuration
    search_radius: int = int(os.getenv("SEARCH_RADIUS", "500"))
    max_restaurants: int = int(os.getenv("MAX_RESTAURANTS", "20"))
    
    class Config:
        env_file = ".env"

# 全域設定實例
settings = Settings()
