# modules/cache_manager.py
"""
記憶體快取管理系統 - 提升搜尋性能

主要功能：
1. LRU快取餐廳搜尋結果
2. 天氣資料快取
3. AI分析結果快取
4. 智能過期機制
"""

import time
import hashlib
import json
from typing import Dict, Any, Optional, Tuple
from functools import lru_cache
from datetime import datetime, timedelta

class CacheManager:
    def __init__(self, max_size=1000):
        self.restaurant_cache = {}  # 餐廳搜尋快取
        self.weather_cache = {}     # 天氣資料快取
        self.ai_cache = {}          # AI分析快取
        self.max_size = max_size
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "restaurant_hits": 0,
            "weather_hits": 0,
            "ai_hits": 0
        }
    
    def _generate_cache_key(self, *args) -> str:
        """生成快取鍵值"""
        cache_string = "|".join(str(arg) for arg in args)
        return hashlib.md5(cache_string.encode()).hexdigest()
    
    def _is_expired(self, cached_item: Dict, ttl_minutes: int) -> bool:
        """檢查快取是否過期"""
        if "timestamp" not in cached_item:
            return True
        
        cache_time = datetime.fromisoformat(cached_item["timestamp"])
        expiry_time = cache_time + timedelta(minutes=ttl_minutes)
        return datetime.now() > expiry_time
    
    def _cleanup_cache(self, cache_dict: Dict, max_entries: int = None):
        """清理過期快取項目"""
        if max_entries is None:
            max_entries = self.max_size // 3
            
        if len(cache_dict) > max_entries:
            # 移除最舊的項目
            sorted_items = sorted(cache_dict.items(), 
                                key=lambda x: x[1].get("timestamp", ""))
            
            remove_count = len(cache_dict) - max_entries
            for i in range(remove_count):
                del cache_dict[sorted_items[i][0]]
    
    # 餐廳搜尋快取
    def get_restaurant_cache(self, keyword: str, location: str, max_results: int, 
                           max_distance: float = None) -> Optional[Dict]:
        """獲取餐廳搜尋快取"""
        cache_key = self._generate_cache_key(keyword, location, max_results, max_distance)
        
        if cache_key in self.restaurant_cache:
            cached_item = self.restaurant_cache[cache_key]
            
            # 餐廳資料快取30分鐘
            if not self._is_expired(cached_item, ttl_minutes=30):
                self.cache_stats["hits"] += 1
                self.cache_stats["restaurant_hits"] += 1
                print(f"快取命中：餐廳搜尋 {keyword} @ {location}")
                return cached_item["data"]
            else:
                # 過期則刪除
                del self.restaurant_cache[cache_key]
        
        self.cache_stats["misses"] += 1
        return None
    
    def set_restaurant_cache(self, keyword: str, location: str, max_results: int, 
                           restaurants: list, max_distance: float = None):
        """設置餐廳搜尋快取"""
        cache_key = self._generate_cache_key(keyword, location, max_results, max_distance)
        
        self.restaurant_cache[cache_key] = {
            "data": restaurants,
            "timestamp": datetime.now().isoformat(),
            "keyword": keyword,
            "location": location
        }
        
        # 清理過期快取
        self._cleanup_cache(self.restaurant_cache)
        print(f"快取設置：餐廳搜尋 {keyword} @ {location} ({len(restaurants)} 家)")
    
    # 天氣資料快取
    def get_weather_cache(self, location: str) -> Optional[Dict]:
        """獲取天氣快取"""
        cache_key = self._generate_cache_key("weather", location)
        
        if cache_key in self.weather_cache:
            cached_item = self.weather_cache[cache_key]
            
            # 天氣資料快取15分鐘
            if not self._is_expired(cached_item, ttl_minutes=15):
                self.cache_stats["hits"] += 1
                self.cache_stats["weather_hits"] += 1
                print(f"快取命中：天氣資料 {location}")
                return cached_item["data"]
            else:
                del self.weather_cache[cache_key]
        
        self.cache_stats["misses"] += 1
        return None
    
    def set_weather_cache(self, location: str, weather_data: Dict):
        """設置天氣快取"""
        cache_key = self._generate_cache_key("weather", location)
        
        self.weather_cache[cache_key] = {
            "data": weather_data,
            "timestamp": datetime.now().isoformat(),
            "location": location
        }
        
        self._cleanup_cache(self.weather_cache, max_entries=200)
        print(f"快取設置：天氣資料 {location}")
    
    # AI分析快取
    def get_ai_cache(self, user_input: str, analysis_type: str = "general") -> Optional[Dict]:
        """獲取AI分析快取"""
        cache_key = self._generate_cache_key("ai", user_input, analysis_type)
        
        if cache_key in self.ai_cache:
            cached_item = self.ai_cache[cache_key]
            
            # AI分析快取60分鐘（相同輸入結果穩定）
            if not self._is_expired(cached_item, ttl_minutes=60):
                self.cache_stats["hits"] += 1
                self.cache_stats["ai_hits"] += 1
                print(f"快取命中：AI分析 '{user_input[:30]}...'")
                return cached_item["data"]
            else:
                del self.ai_cache[cache_key]
        
        self.cache_stats["misses"] += 1
        return None
    
    def set_ai_cache(self, user_input: str, analysis_result: Dict, analysis_type: str = "general"):
        """設置AI分析快取"""
        cache_key = self._generate_cache_key("ai", user_input, analysis_type)
        
        self.ai_cache[cache_key] = {
            "data": analysis_result,
            "timestamp": datetime.now().isoformat(),
            "input": user_input[:50],  # 存儲部分輸入用於除錯
            "type": analysis_type
        }
        
        self._cleanup_cache(self.ai_cache, max_entries=500)
        print(f"快取設置：AI分析 '{user_input[:30]}...'")
    
    def get_cache_stats(self) -> Dict:
        """獲取快取統計"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.cache_stats,
            "total_requests": total_requests,
            "hit_rate": f"{hit_rate:.1f}%",
            "restaurant_cache_size": len(self.restaurant_cache),
            "weather_cache_size": len(self.weather_cache),
            "ai_cache_size": len(self.ai_cache)
        }
    
    def clear_cache(self, cache_type: str = "all"):
        """清空快取"""
        if cache_type in ["all", "restaurant"]:
            self.restaurant_cache.clear()
        if cache_type in ["all", "weather"]:
            self.weather_cache.clear()
        if cache_type in ["all", "ai"]:
            self.ai_cache.clear()
        
        if cache_type == "all":
            self.cache_stats = {k: 0 for k in self.cache_stats}
        
        print(f"快取已清空：{cache_type}")

# 創建全域快取管理器實例
cache_manager = CacheManager(max_size=1000)

# 便捷函數
def get_restaurant_cache(keyword: str, location: str, max_results: int, max_distance: float = None):
    return cache_manager.get_restaurant_cache(keyword, location, max_results, max_distance)

def set_restaurant_cache(keyword: str, location: str, max_results: int, restaurants: list, max_distance: float = None):
    cache_manager.set_restaurant_cache(keyword, location, max_results, restaurants, max_distance)

def get_weather_cache(location: str):
    return cache_manager.get_weather_cache(location)

def set_weather_cache(location: str, weather_data: dict):
    cache_manager.set_weather_cache(location, weather_data)

def get_ai_cache(user_input: str, analysis_type: str = "general"):
    return cache_manager.get_ai_cache(user_input, analysis_type)

def set_ai_cache(user_input: str, analysis_result: dict, analysis_type: str = "general"):
    cache_manager.set_ai_cache(user_input, analysis_result, analysis_type)

def get_cache_stats():
    return cache_manager.get_cache_stats()