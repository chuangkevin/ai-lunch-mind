# modules/sqlite_cache_manager.py
"""
SQLite 持久化快取管理系統 - 提升搜尋性能並支援跨會話快取

主要功能：
1. SQLite 持久化快取餐廳搜尋結果
2. 天氣資料快取
3. AI分析結果快取
4. 自動過期機制
5. 快取統計與清理
"""

import sqlite3
import time
import hashlib
import json
import threading
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import os

class SQLiteCacheManager:
    def __init__(self, db_path="cache.db", max_size=10000):
        self.db_path = db_path
        self.max_size = max_size
        self._lock = threading.Lock()
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "restaurant_hits": 0,
            "weather_hits": 0,
            "ai_hits": 0
        }
        
        # 初始化資料庫
        self._init_database()
        
        # 啟動時清理過期項目
        self._cleanup_expired_items()
    
    def _init_database(self):
        """初始化 SQLite 資料庫結構"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 建立快取表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_items (
                    cache_key TEXT PRIMARY KEY,
                    cache_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 建立統計表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_stats (
                    stat_name TEXT PRIMARY KEY,
                    stat_value INTEGER DEFAULT 0
                )
            ''')
            
            # 建立索引以提升查詢性能
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_cache_type_expires 
                ON cache_items(cache_type, expires_at)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_expires_at 
                ON cache_items(expires_at)
            ''')
            
            # 初始化統計數據
            stats_to_init = ["hits", "misses", "restaurant_hits", "weather_hits", "ai_hits"]
            for stat in stats_to_init:
                cursor.execute('''
                    INSERT OR IGNORE INTO cache_stats (stat_name, stat_value) 
                    VALUES (?, 0)
                ''', (stat,))
            
            conn.commit()
    
    def _generate_cache_key(self, *args) -> str:
        """生成快取鍵值"""
        cache_string = "|".join(str(arg) for arg in args)
        return hashlib.md5(cache_string.encode()).hexdigest()
    
    def _update_stats(self, stat_name: str, increment: int = 1):
        """更新統計數據"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE cache_stats SET stat_value = stat_value + ? 
                WHERE stat_name = ?
            ''', (increment, stat_name))
            conn.commit()
        
        # 同步更新記憶體統計
        if stat_name in self.cache_stats:
            self.cache_stats[stat_name] += increment
    
    def _get_cache_item(self, cache_key: str) -> Optional[Dict]:
        """從資料庫獲取快取項目"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT data, metadata, expires_at, access_count 
                FROM cache_items 
                WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP
            ''', (cache_key,))
            
            result = cursor.fetchone()
            if result:
                # 更新訪問次數和時間
                cursor.execute('''
                    UPDATE cache_items 
                    SET access_count = access_count + 1, 
                        last_accessed = CURRENT_TIMESTAMP 
                    WHERE cache_key = ?
                ''', (cache_key,))
                conn.commit()
                
                return {
                    "data": json.loads(result[0]),
                    "metadata": json.loads(result[1]) if result[1] else {},
                    "expires_at": result[2],
                    "access_count": result[3] + 1
                }
            return None
    
    def _set_cache_item(self, cache_key: str, cache_type: str, data: Any, 
                       metadata: Dict, ttl_minutes: int):
        """設置快取項目到資料庫"""
        expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO cache_items 
                (cache_key, cache_type, data, metadata, expires_at) 
                VALUES (?, ?, ?, ?, ?)
            ''', (
                cache_key,
                cache_type,
                json.dumps(data, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                expires_at.isoformat()
            ))
            conn.commit()
        
        # 清理過期項目以控制資料庫大小
        self._cleanup_expired_items()
        self._enforce_size_limit()
    
    def _cleanup_expired_items(self):
        """清理過期的快取項目"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM cache_items 
                WHERE expires_at <= CURRENT_TIMESTAMP
            ''')
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                print(f"清理了 {deleted_count} 個過期快取項目")
    
    def _enforce_size_limit(self):
        """強制執行快取大小限制"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 檢查當前項目數量
            cursor.execute('SELECT COUNT(*) FROM cache_items')
            current_count = cursor.fetchone()[0]
            
            if current_count > self.max_size:
                # 刪除最舊且最少使用的項目
                items_to_delete = current_count - self.max_size
                cursor.execute('''
                    DELETE FROM cache_items 
                    WHERE cache_key IN (
                        SELECT cache_key FROM cache_items 
                        ORDER BY access_count ASC, last_accessed ASC 
                        LIMIT ?
                    )
                ''', (items_to_delete,))
                conn.commit()
                print(f"清理了 {items_to_delete} 個最少使用的快取項目")
    
    # 餐廳搜尋快取
    def get_restaurant_cache(self, keyword: str, location: str, max_results: int, 
                           max_distance: float = None) -> Optional[Dict]:
        """獲取餐廳搜尋快取"""
        with self._lock:
            cache_key = self._generate_cache_key("restaurant", keyword, location, max_results, max_distance)
            
            cached_item = self._get_cache_item(cache_key)
            if cached_item:
                self._update_stats("hits")
                self._update_stats("restaurant_hits")
                print(f"快取命中：餐廳搜尋 {keyword} @ {location}")
                return cached_item["data"]
            
            self._update_stats("misses")
            return None
    
    def set_restaurant_cache(self, keyword: str, location: str, max_results: int, 
                           restaurants: list, max_distance: float = None):
        """設置餐廳搜尋快取"""
        with self._lock:
            cache_key = self._generate_cache_key("restaurant", keyword, location, max_results, max_distance)
            
            metadata = {
                "keyword": keyword,
                "location": location,
                "max_results": max_results,
                "max_distance": max_distance,
                "result_count": len(restaurants)
            }
            
            # 餐廳資料快取30分鐘
            self._set_cache_item(cache_key, "restaurant", restaurants, metadata, ttl_minutes=30)
            print(f"快取設置：餐廳搜尋 {keyword} @ {location} ({len(restaurants)} 家)")
    
    # 天氣資料快取
    def get_weather_cache(self, location: str) -> Optional[Dict]:
        """獲取天氣快取"""
        with self._lock:
            cache_key = self._generate_cache_key("weather", location)
            
            cached_item = self._get_cache_item(cache_key)
            if cached_item:
                self._update_stats("hits")
                self._update_stats("weather_hits")
                print(f"快取命中：天氣資料 {location}")
                return cached_item["data"]
            
            self._update_stats("misses")
            return None
    
    def set_weather_cache(self, location: str, weather_data: Dict):
        """設置天氣快取"""
        with self._lock:
            cache_key = self._generate_cache_key("weather", location)
            
            metadata = {
                "location": location,
                "data_type": "weather"
            }
            
            # 天氣資料快取15分鐘
            self._set_cache_item(cache_key, "weather", weather_data, metadata, ttl_minutes=15)
            print(f"快取設置：天氣資料 {location}")
    
    # AI分析快取
    def get_ai_cache(self, user_input: str, analysis_type: str = "general") -> Optional[Dict]:
        """獲取AI分析快取"""
        with self._lock:
            cache_key = self._generate_cache_key("ai", user_input, analysis_type)
            
            cached_item = self._get_cache_item(cache_key)
            if cached_item:
                self._update_stats("hits")
                self._update_stats("ai_hits")
                print(f"快取命中：AI分析 '{user_input[:30]}...'")
                return cached_item["data"]
            
            self._update_stats("misses")
            return None
    
    def set_ai_cache(self, user_input: str, analysis_result: Dict, analysis_type: str = "general"):
        """設置AI分析快取"""
        with self._lock:
            cache_key = self._generate_cache_key("ai", user_input, analysis_type)
            
            metadata = {
                "input_preview": user_input[:50],
                "analysis_type": analysis_type,
                "input_length": len(user_input)
            }
            
            # AI分析快取60分鐘
            self._set_cache_item(cache_key, "ai", analysis_result, metadata, ttl_minutes=60)
            print(f"快取設置：AI分析 '{user_input[:30]}...'")
    
    def get_cache_stats(self) -> Dict:
        """獲取快取統計"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 從資料庫獲取統計數據
            cursor.execute('SELECT stat_name, stat_value FROM cache_stats')
            db_stats = dict(cursor.fetchall())
            
            # 獲取快取大小統計
            cursor.execute('''
                SELECT cache_type, COUNT(*) 
                FROM cache_items 
                WHERE expires_at > CURRENT_TIMESTAMP 
                GROUP BY cache_type
            ''')
            cache_sizes = dict(cursor.fetchall())
            
            # 計算命中率
            total_requests = db_stats.get("hits", 0) + db_stats.get("misses", 0)
            hit_rate = (db_stats.get("hits", 0) / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **db_stats,
                "total_requests": total_requests,
                "hit_rate": f"{hit_rate:.1f}%",
                "restaurant_cache_size": cache_sizes.get("restaurant", 0),
                "weather_cache_size": cache_sizes.get("weather", 0),
                "ai_cache_size": cache_sizes.get("ai", 0),
                "total_cache_size": sum(cache_sizes.values()),
                "db_file_size": os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            }
    
    def clear_cache(self, cache_type: str = "all"):
        """清空快取"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if cache_type == "all":
                    cursor.execute('DELETE FROM cache_items')
                    cursor.execute('UPDATE cache_stats SET stat_value = 0')
                    self.cache_stats = {k: 0 for k in self.cache_stats}
                else:
                    cursor.execute('DELETE FROM cache_items WHERE cache_type = ?', (cache_type,))
                
                conn.commit()
                print(f"快取已清空：{cache_type}")
    
    def vacuum_database(self):
        """壓縮資料庫以回收空間"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('VACUUM')
            print("資料庫已壓縮")
    
    def close(self):
        """關閉快取管理器（清理資源）"""
        # SQLite 連接會自動關閉，這裡可以執行最終清理
        pass

# 創建全域 SQLite 快取管理器實例
sqlite_cache_manager = SQLiteCacheManager(db_path="cache.db", max_size=10000)

# 便捷函數 - 保持與原有記憶體快取相同的API
def get_restaurant_cache(keyword: str, location: str, max_results: int, max_distance: float = None):
    return sqlite_cache_manager.get_restaurant_cache(keyword, location, max_results, max_distance)

def set_restaurant_cache(keyword: str, location: str, max_results: int, restaurants: list, max_distance: float = None):
    sqlite_cache_manager.set_restaurant_cache(keyword, location, max_results, restaurants, max_distance)

def get_weather_cache(location: str):
    return sqlite_cache_manager.get_weather_cache(location)

def set_weather_cache(location: str, weather_data: dict):
    sqlite_cache_manager.set_weather_cache(location, weather_data)

def get_ai_cache(user_input: str, analysis_type: str = "general"):
    return sqlite_cache_manager.get_ai_cache(user_input, analysis_type)

def set_ai_cache(user_input: str, analysis_result: dict, analysis_type: str = "general"):
    sqlite_cache_manager.set_ai_cache(user_input, analysis_result, analysis_type)

def get_cache_stats():
    return sqlite_cache_manager.get_cache_stats()

def clear_cache(cache_type: str = "all"):
    sqlite_cache_manager.clear_cache(cache_type)

def vacuum_cache_database():
    sqlite_cache_manager.vacuum_database()