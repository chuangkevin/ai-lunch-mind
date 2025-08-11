"""
Google Maps 餐廳搜尋模組 - Selenium 版本 + 多工處理優化
使用 Selenium 進行真實瀏覽器自動化搜尋，提供更準確的餐廳資訊
新增多工處理功能：並行搜尋、瀏覽器池、快取機制
"""

from typing import List, Dict, Optional, Any, Tuple
import time
import random
import re
import requests
import urllib.parse
from urllib.parse import quote, unquote, parse_qs, urlparse
import ssl
import urllib3
from bs4 import BeautifulSoup
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging
import asyncio
import concurrent.futures
import threading
from queue import Queue
from contextlib import contextmanager
import json
from datetime import datetime, timedelta

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# TODO: 將 User-Agent 清單改用資料庫存儲 (如 SQLite)
# 建議資料表：user_agents (id, agent_string, browser_type, active_status, last_used)
# 優點：支援動態更新、使用頻率追蹤、失效檢測、瀏覽器類型分類
# User-Agent 池，用於降低被偵測機率
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
]

def create_session() -> requests.Session:
    """
    建立模擬瀏覽器的 Session（備用方案）
    :return: 配置好的 requests.Session
    """
    session = requests.Session()
    
    # 隨機選擇 User-Agent
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    session.headers.update(headers)
    
    # 忽略 SSL 驗證
    session.verify = False
    
    return session

def create_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    """
    建立 Chrome 瀏覽器驅動
    :param headless: 是否無頭模式
    :return: Chrome WebDriver
    """
    options = Options()
    
    if headless:
        options.add_argument('--headless')
    
    # 基本設定
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-gpu-sandbox')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-ipc-flooding-protection')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 額外的日誌抑制設定
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--disable-logging')
    options.add_argument('--disable-gpu-logging')
    options.add_argument('--silent')
    options.add_argument('--log-level=3')
    
    # 隨機 User-Agent
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'--user-agent={user_agent}')
    
    # 語言設定
    options.add_argument('--lang=zh-TW')
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        logger.error(f"建立 Chrome 驅動失敗: {e}")
        raise

def create_chrome_driver_fast(headless: bool = True) -> webdriver.Chrome:
    """
    建立 Chrome 瀏覽器驅動 - 速度優化版本
    :param headless: 是否無頭模式
    :return: Chrome WebDriver
    """
    options = Options()
    
    if headless:
        options.add_argument('--headless')
    
    # 最精簡的設定 - 只保留必要選項
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')  # 不載入圖片加速
    options.add_argument('--disable-javascript')  # 不執行 JS 加速
    options.add_argument('--window-size=1024,768')  # 小視窗
    
    # 最快的 User-Agent
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        logger.error(f"建立快速 Chrome 驅動失敗: {e}")
        raise

class BrowserPool:
    """瀏覽器實例池，管理多個瀏覽器實例以提升效能"""
    
    def __init__(self, pool_size: int = 1):  # 減少池大小
        self.pool_size = pool_size
        self.available_browsers = Queue()
        self.all_browsers = []
        self.lock = threading.Lock()
        self._initialize_pool()
    
    def _initialize_pool(self):
        """初始化瀏覽器池"""
        logger.info(f"🚀 初始化瀏覽器池，大小: {self.pool_size}")
        for i in range(self.pool_size):
            try:
                driver = create_chrome_driver_fast()  # 使用快速版本
                self.available_browsers.put(driver)
                self.all_browsers.append(driver)
                logger.info(f"✅ 瀏覽器 {i+1} 已創建並加入池中")
            except Exception as e:
                logger.error(f"❌ 創建瀏覽器 {i+1} 失敗: {e}")
    
    @contextmanager
    def get_browser(self):
        """獲取瀏覽器實例的上下文管理器"""
        driver = None
        try:
            # 嘗試從池中獲取瀏覽器，超時 3 秒
            driver = self.available_browsers.get(timeout=3)
            yield driver
        except:
            # 如果池中沒有可用瀏覽器，創建新的
            logger.warning("⚠️ 池中無可用瀏覽器，創建新實例")
            driver = create_chrome_driver(headless=True)
            yield driver
        finally:
            if driver:
                try:
                    # 清理瀏覽器狀態
                    driver.delete_all_cookies()
                    # 將瀏覽器放回池中
                    self.available_browsers.put(driver)
                except:
                    # 如果瀏覽器已損壞，關閉它
                    try:
                        driver.quit()
                    except:
                        pass
    
    def close_all(self):
        """關閉所有瀏覽器實例"""
        logger.info("🛑 關閉所有瀏覽器實例")
        for driver in self.all_browsers:
            try:
                driver.quit()
            except:
                pass

class SearchCache:
    """搜尋結果快取，避免重複搜尋"""
    
    def __init__(self, cache_ttl: int = 300):  # 5分鐘快取
        self.cache = {}
        self.cache_ttl = cache_ttl
        self.lock = threading.Lock()
    
    def get_cache_key(self, keyword: str, location_info: Optional[Dict] = None) -> str:
        """生成快取鍵"""
        location_str = ""
        if location_info and location_info.get('address'):
            location_str = location_info['address']
        return f"{keyword}_{location_str}"
    
    def get(self, keyword: str, location_info: Optional[Dict] = None) -> Optional[List[Dict]]:
        """獲取快取結果"""
        cache_key = self.get_cache_key(keyword, location_info)
        with self.lock:
            if cache_key in self.cache:
                cached_data, timestamp = self.cache[cache_key]
                if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                    logger.info(f"📦 使用快取結果: {cache_key}")
                    return cached_data
                else:
                    # 快取過期，刪除
                    del self.cache[cache_key]
        return None
    
    def set(self, keyword: str, location_info: Optional[Dict], results: List[Dict]):
        """設置快取結果"""
        cache_key = self.get_cache_key(keyword, location_info)
        with self.lock:
            self.cache[cache_key] = (results, datetime.now())
            logger.info(f"💾 快取搜尋結果: {cache_key}")

# 全域實例
browser_pool = BrowserPool(pool_size=3)
search_cache = SearchCache()

def expand_short_url(short_url: str, max_redirects: int = 10) -> str:
    """
    展開 Google Maps 短網址 - 改進版本
    :param short_url: 短網址
    :param max_redirects: 最大重定向次數
    :return: 完整 URL
    """
    try:
        session = create_session()
        
        # 設定更詳細的請求頭
        session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        
        # 逐步跟蹤重定向
        current_url = short_url
        redirect_count = 0
        
        while redirect_count < max_redirects:
            try:
                response = session.get(current_url, allow_redirects=False, timeout=15)
                
                # 檢查是否有重定向
                if response.status_code in [301, 302, 303, 307, 308]:
                    location = response.headers.get('Location')
                    if location:
                        if location.startswith('/'):
                            # 相對路徑，需要組合完整URL
                            from urllib.parse import urljoin
                            current_url = urljoin(current_url, location)
                        else:
                            current_url = location
                        redirect_count += 1
                        logger.info(f"重定向 {redirect_count}: {current_url}")
                        continue
                
                # 如果是最終URL或無重定向
                if response.status_code == 200:
                    final_url = current_url
                    logger.info(f"短網址展開成功: {short_url} -> {final_url}")
                    return final_url
                
                break
                
            except requests.RequestException as e:
                logger.warning(f"重定向追蹤失敗: {e}")
                break
        
        # 如果追蹤失敗，嘗試直接請求並獲取最終URL
        try:
            response = session.get(short_url, allow_redirects=True, timeout=15)
            final_url = response.url
            logger.info(f"直接展開成功: {short_url} -> {final_url}")
            return final_url
        except Exception as e:
            logger.error(f"短網址展開完全失敗: {e}")
            return short_url
            
    except Exception as e:
        logger.error(f"展開短網址失敗: {e}")
        return short_url

def extract_location_from_url(url: str) -> Optional[Tuple[float, float, str]]:
    """
    從 Google Maps URL 提取位置資訊 - 改進版本
    :param url: Google Maps URL
    :return: (latitude, longitude, place_name) 或 None
    """
    try:
        original_url = url
        
        # 展開短網址
        if 'maps.app.goo.gl' in url or 'goo.gl' in url or 'g.co/kgs/' in url or len(url) < 50:
            logger.info(f"展開短網址: {url}")
            url = expand_short_url(url)
            if url == original_url:
                logger.warning("短網址展開失敗，使用原始URL")
        
        logger.info(f"處理URL: {url}")
        
        # 多種座標提取模式
        coordinate_patterns = [
            r'/@(-?\d+\.\d+),(-?\d+\.\d+)',  # 標準格式 /@lat,lng
            r'/place/[^/]*/@(-?\d+\.\d+),(-?\d+\.\d+)',  # place格式
            r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',  # 編碼格式
            r'center=(-?\d+\.\d+),(-?\d+\.\d+)',  # center參數
            r'll=(-?\d+\.\d+),(-?\d+\.\d+)',  # ll參數
            r'q=(-?\d+\.\d+),(-?\d+\.\d+)',  # q參數座標
        ]
        
        lat, lng = None, None
        for pattern in coordinate_patterns:
            coord_match = re.search(pattern, url)
            if coord_match:
                try:
                    lat = float(coord_match.group(1))
                    lng = float(coord_match.group(2))
                    
                    # 驗證座標是否在台灣範圍內
                    if 21.0 <= lat <= 26.0 and 119.0 <= lng <= 122.5:
                        logger.info(f"提取座標成功: ({lat}, {lng})")
                        break
                    else:
                        logger.warning(f"座標超出台灣範圍: ({lat}, {lng})")
                        lat, lng = None, None
                except ValueError:
                    continue
        
        # 提取地點名稱 - 多種模式
        place_name = None
        place_patterns = [
            r'/place/([^/@]+)',  # 標準place格式
            r'search/([^/@]+)',  # search格式  
            r'q=([^&@]+)',  # q參數
            r'query=([^&@]+)',  # query參數
        ]
        
        for pattern in place_patterns:
            place_match = re.search(pattern, url)
            if place_match:
                try:
                    raw_name = place_match.group(1)
                    # URL解碼
                    place_name = unquote(raw_name)
                    # 清理格式
                    place_name = place_name.replace('+', ' ').replace('%20', ' ')
                    place_name = place_name.strip()
                    
                    # 驗證地點名稱合理性
                    if len(place_name) > 1 and not place_name.isdigit():
                        logger.info(f"提取地點名稱: {place_name}")
                        break
                    else:
                        place_name = None
                except Exception:
                    continue
        
        # 如果有座標，直接返回
        if lat is not None and lng is not None:
            if not place_name:
                # 如果無法提取地點名稱，嘗試反向地理編碼
                try:
                    from geopy.geocoders import Nominatim
                    geolocator = Nominatim(user_agent="lunch-recommendation-system")
                    location = geolocator.reverse(f"{lat}, {lng}", language='zh-TW')
                    if location and location.address:
                        place_name = location.address.split(',')[0]  # 取第一部分作為地點名稱
                        logger.info(f"反向地理編碼獲得地點名稱: {place_name}")
                except Exception as e:
                    logger.warning(f"反向地理編碼失敗: {e}")
                    place_name = f"位置 ({lat:.4f}, {lng:.4f})"
            return (lat, lng, place_name)
        
        # 如果沒有座標但有地點名稱，嘗試地理編碼
        if place_name:
            logger.info(f"URL無座標，嘗試對地點名稱進行地理編碼: {place_name}")
            coords = geocode_address(place_name)
            if coords:
                lat, lng = coords
                logger.info(f"地理編碼成功: {place_name} -> ({lat:.4f}, {lng:.4f})")
                return (lat, lng, place_name)
            else:
                logger.warning(f"地理編碼失敗: {place_name}")
        
        logger.warning("無法從URL提取有效位置資訊")
        return None
        
    except Exception as e:
        logger.error(f"URL 位置提取失敗: {e}")
        return None

def normalize_taiwan_address(address: str) -> str:
    """
    標準化台灣地址格式
    :param address: 原始地址
    :return: 標準化後的地址
    """
    if not address:
        return ""
    
    # 移除多餘空白和特殊字符
    address = re.sub(r'\s+', '', address)
    
    # 補全常見縮寫 - 注意不要影響現有的完整名稱
    address_replacements = {
        '北市': '台北市',
        '桃市': '桃園市', 
        '高市': '高雄市'
    }
    
    for old, new in address_replacements.items():
        # 只有當不存在完整名稱時才替換縮寫
        if old in address and new not in address:
            address = address.replace(old, new)
    
    # 確保地址包含完整的行政區劃
    if '台北市' in address and '區' not in address and '鄉' not in address and '鎮' not in address:
        # 嘗試從常見區域名稱推斷台北市的區
        district_mapping = {
            '中山': '中山區',
            '信義': '信義區',
            '大安': '大安區',
            '松山': '松山區',
            '中正': '中正區',
            '萬華': '萬華區',
            '大同': '大同區',
            '士林': '士林區',
            '北投': '北投區',
            '內湖': '內湖區',
            '南港': '南港區',
            '文山': '文山區'
        }
        
        for district, full_district in district_mapping.items():
            if district in address and full_district not in address:
                address = address.replace(f'台北市{district}', f'台北市{full_district}')
                break
    
    return address

def smart_address_completion(address: str, search_location: Optional[str] = None) -> str:
    """
    簡化的地址處理 - 移除愚蠢的硬編碼邏輯
    直接讓 Nominatim 處理地址，它比我們的硬編碼更智能
    :param address: 原始地址
    :param search_location: 搜尋位置（僅作為上下文，不再用於硬編碼映射）
    :return: 清理後的地址
    """
    if not address:
        return address
    
    # 只做基本清理，讓專業的地理編碼服務處理其餘邏輯
    return address.strip()

def geocode_address_with_options(address: str, search_location: Optional[str] = None) -> Dict:
    """
    地理編碼，當發現模糊地名時返回多個選項供用戶選擇
    :param address: 地址字串
    :param search_location: 搜尋位置參考
    :return: {'type': 'single', 'coords': (lat, lng)} 或 {'type': 'multiple', 'options': [...]}
    """
    if not address or len(address.strip()) < 3:
        return {'type': 'error', 'message': '地址太短'}
    
    # 檢查是否為模糊地名（特別是捷運站名）
    if address.endswith('站') and not any(keyword in address for keyword in ['市', '縣', '路', '街']):
        # 可能是捷運站，提供多個選項
        options = []
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
        
        # 嘗試不同的查詢方式
        search_variants = [
            (f"台北捷運{address}", "台北捷運站"),
            (f"捷運{address}", "捷運站"), 
            (address, "一般地點"),
        ]
        
        for query, desc in search_variants:
            try:
                locations = geolocator.geocode(query, exactly_one=False, limit=3)
                if locations:
                    for loc in locations:
                        if 21.0 <= loc.latitude <= 26.0 and 119.0 <= loc.longitude <= 122.5:
                            options.append({
                                'coords': (loc.latitude, loc.longitude),
                                'address': loc.address,
                                'description': desc,
                                'query': query
                            })
            except Exception:
                continue
        
        # 如果找到多個選項，讓用戶選擇
        if len(options) > 1:
            # 去重相似的位置（距離<100m視為同一地點）
            unique_options = []
            for option in options:
                is_duplicate = False
                for unique in unique_options:
                    from geopy.distance import geodesic
                    if geodesic(option['coords'], unique['coords']).meters < 100:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_options.append(option)
            
            if len(unique_options) > 1:
                logger.info(f"發現模糊地名 '{address}'，提供 {len(unique_options)} 個選項")
                return {'type': 'multiple', 'options': unique_options, 'original_query': address}
    
    # 使用原有的單一地理編碼邏輯
    coords = geocode_address(address, search_location)
    if coords:
        return {'type': 'single', 'coords': coords}
    else:
        return {'type': 'error', 'message': f'無法找到地址: {address}'}

def geocode_address(address: str, search_location: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """
    簡化的地址轉座標功能 - 移除複雜邏輯，讓 Nominatim 自己處理
    :param address: 地址字串
    :param search_location: 搜尋位置參考（暫時不使用）
    :return: (latitude, longitude) 或 None
    """
    if not address or len(address.strip()) < 3:
        return None
    
    # 簡化的地址補全
    completed_address = smart_address_completion(address, search_location)
    logger.info(f"地址補全: {address} -> {completed_address}")
    
    # 標準化地址
    normalized_address = normalize_taiwan_address(completed_address)
    logger.info(f"標準化地址: {completed_address} -> {normalized_address}")
    
    # 使用 Nominatim 進行地理編碼
    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
        
        # 構建查詢列表，優先完整地址
        search_queries = []
        
        # 若地址包含常見「區」名但缺少「市/縣」，自動補城市（特別是台北常見情境）
        has_city_or_county = any(city in address for city in ['市', '縣'])
        district_to_city_map = {
            # 台北市
            '中正區': '台北市', '大同區': '台北市', '中山區': '台北市', '松山區': '台北市',
            '大安區': '台北市', '萬華區': '台北市', '信義區': '台北市', '士林區': '台北市',
            '北投區': '台北市', '內湖區': '台北市', '南港區': '台北市', '文山區': '台北市',
            # 新北市（常見幾個）
            '板橋區': '新北市', '新莊區': '新北市', '中和區': '新北市', '永和區': '新北市',
            '三重區': '新北市', '蘆洲區': '新北市', '汐止區': '新北市', '新店區': '新北市',
            '土城區': '新北市', '鶯歌區': '新北市', '三峽區': '新北市', '泰山區': '新北市',
            '林口區': '新北市', '淡水區': '新北市', '五股區': '新北市', '八里區': '新北市',
        }
        mapped_city_prefix = None
        if not has_city_or_county:
            for district, city in district_to_city_map.items():
                if district in normalized_address or district in completed_address or district in address:
                    mapped_city_prefix = city
                    break
        
        if mapped_city_prefix:
            # 在最前面插入帶城市前綴的查詢，強化定位
            search_queries.extend([
                f"{mapped_city_prefix}{normalized_address}, Taiwan",
                f"{mapped_city_prefix}{normalized_address}",
                f"{mapped_city_prefix}{completed_address}, Taiwan",
                f"{mapped_city_prefix}{completed_address}"
            ])
        
        # 原有通用查詢
        search_queries.extend([
            normalized_address + ", Taiwan",
            normalized_address,
            completed_address + ", Taiwan",
            completed_address,
            address + ", Taiwan",
            address
        ])
        
        # 特殊處理：如果是捷運站名，優先嘗試捷運相關查詢
        if address.endswith('站') and not any(keyword in address for keyword in ['市', '縣', '路', '街']):
            # 這可能是捷運站名
            mrt_queries = [
                f"台北捷運{address}, Taiwan",
                f"捷運{address}, Taiwan", 
                f"台北捷運{address}",
                f"捷運{address}"
            ]
            # 將捷運查詢插入到最前面
            search_queries = mrt_queries + search_queries
            logger.debug(f"檢測到可能的捷運站名，添加捷運查詢: {address}")
        
        # 如果地址沒有包含市縣但包含道路用詞，優先嘗試台北市（保持原有策略）
        if not any(city in address for city in ['市', '縣']) and any(road in address for road in ['路', '街', '大道']):
            search_queries.insert(0, f"台北市{address}, Taiwan")
            search_queries.insert(1, f"台北市{address}")
        
        logger.debug(f"完整查詢列表: {search_queries}")
        
        # 嘗試每個查詢，但優先保持原始精度
        best_result = None
        best_query_score = 0
        
        for i, query in enumerate(search_queries):
            try:
                logger.debug(f"嘗試查詢: {query}")
                location = geolocator.geocode(query, limit=1)
                
                if location and location.latitude and location.longitude:
                    # 驗證座標在台灣範圍內
                    if 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                        # 計算查詢品質分數（越早的查詢越好，包含更多細節的查詢越好）
                        query_score = 100 - i  # 基礎分數，越早越高
                        
                        # 保持完整地址的獎勵分數
                        if '巷' in query and '號' in query:
                            query_score += 50  # 完整地址大獎勵
                        elif '巷' in query or '號' in query:
                            query_score += 25  # 部分細節獎勵
                        elif '段' in query:
                            query_score += 10  # 段級別獎勵
                        
                        # 如果這是第一個結果或者分數更高，記錄為最佳結果
                        if best_result is None or query_score > best_query_score:
                            best_result = (location.latitude, location.longitude)
                            best_query_score = query_score
                            best_query = query
                        
                        # 如果找到完整地址級別的結果，立即返回
                        if '巷' in query and '號' in query:
                            logger.info(f"✅ 找到完整地址級別結果: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                            return (location.latitude, location.longitude)
                        
            except Exception as e:
                logger.debug(f"查詢失敗: {query} - {e}")
                continue
        
        # 如果有找到結果，返回最佳的
        if best_result:
            logger.info(f"✅ 地理編碼成功: {best_query} -> ({best_result[0]:.4f}, {best_result[1]:.4f})")
            return best_result
        
        # 如果完整地址都找不到，嘗試台灣特殊處理策略
        if '巷' in address or '號' in address:
            logger.warning(f"完整地址查詢失敗，嘗試台灣地址特殊處理: {address}")
            import re
            
            # 台灣地址特殊處理：逐級簡化但保持精度
            fallback_strategies = []
            
            # 策略1: 去掉門牌號但保留巷弄
            if '號' in address:
                addr_without_number = re.sub(r'\d+號.*$', '', address)
                if addr_without_number != address:
                    fallback_strategies.extend([
                        f"{addr_without_number}, Taiwan",
                        addr_without_number
                    ])
            
            # 策略2: 去掉弄但保留巷
            if '弄' in address:
                addr_without_alley = re.sub(r'\d+弄.*$', '', address)
                if addr_without_alley != address:
                    fallback_strategies.extend([
                        f"{addr_without_alley}, Taiwan", 
                        addr_without_alley
                    ])
            
            # 策略3: 保留到巷級別
            if '巷' in address:
                addr_to_lane = re.sub(r'(\d+巷).*$', r'\1', address)
                if addr_to_lane != address:
                    fallback_strategies.extend([
                        f"{addr_to_lane}, Taiwan",
                        addr_to_lane
                    ])
            
            # 策略4: 最後才簡化到路段
            road_match = re.search(r'([^市縣區鄉鎮]*[路街大道](?:一|二|三|四|五|六|七|八|九|\d+)*段?)', address)
            if road_match:
                main_road = road_match.group(1).strip()
                fallback_strategies.extend([
                    f"台北市{main_road}, Taiwan",
                    f"{main_road}, Taiwan",
                    main_road
                ])
            
            # 依次嘗試各種簡化策略
            for i, query in enumerate(fallback_strategies):
                try:
                    logger.debug(f"台灣地址簡化嘗試 {i+1}: {query}")
                    location = geolocator.geocode(query, limit=1)
                    if location and 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                        # 根據簡化程度給予不同的警告級別
                        if '巷' in query:
                            logger.info(f"✅ 巷級別簡化成功: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                        elif '段' in query:
                            logger.warning(f"⚠️ 段級別簡化成功: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                        else:
                            logger.warning(f"⚠️ 道路級別簡化成功: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                        return (location.latitude, location.longitude)
                except Exception:
                    continue
                
    except Exception as e:
        logger.error(f"地理編碼服務異常: {e}")
    
    logger.warning(f"地址解析失敗: {address}")
    return None
    
    # 方法1: 使用 Nominatim (OpenStreetMap) - 智能查詢策略
    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
        
        # 智能構建搜尋詞，不使用硬編碼
        search_queries = []
        
        # 策略1：如果是商圈/地標類，優先搜尋台灣最著名的
        landmark_keywords = ['商圈', '夜市', '老街', '車站', '機場', '大學', '博物館', '公園']
        if any(keyword in address for keyword in landmark_keywords):
            # 對地標進行多種搜尋嘗試，讓Nominatim自然排序
            search_queries = [
                f"{address}, 台北, Taiwan",  # 優先嘗試台北
                f"{address}, Taiwan",  # 讓系統自然選擇最著名的
                f"{address}, 台灣",
                address  # 原始查詢
            ]
        else:
            # 對一般地址的標準查詢
            search_queries = [
                completed_address + ", Taiwan",
                completed_address,
                address + ", Taiwan",
                address
            ]
        
        # 嘗試每個查詢，選擇第一個有效結果
        for query in search_queries:
            try:
                logger.debug(f"嘗試Nominatim查詢: {query}")
                location = geolocator.geocode(query, limit=3)  # 獲取多個結果
                
                if location and location.latitude and location.longitude:
                    # 驗證座標在台灣範圍內
                    if 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                        logger.info(f"✅ Nominatim成功: {query} -> ({location.latitude:.4f}, {location.longitude:.4f})")
                        return (location.latitude, location.longitude)
                    else:
                        logger.debug(f"座標超出台灣範圍: {query}")
                        
            except Exception as e:
                logger.debug(f"查詢失敗: {query} - {e}")
                continue
                
    except Exception as e:
        logger.error(f"Nominatim服務異常: {e}")
    
    # 方法2: 使用座標提取 (如果地址中包含座標資訊)
    try:
        coord_match = re.search(r'(\d{2}\.\d+)[,\s]+(\d{2,3}\.\d+)', address)
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
            if 21.0 <= lat <= 26.0 and 119.0 <= lng <= 122.5:
                logger.info(f"從地址中提取座標: ({lat}, {lng})")
                return (lat, lng)
    except Exception:
        pass
    
    # 方法3: 只對完整地址嘗試簡化解析
    try:
        # 檢查地址是否足夠完整 - 更靈活的判斷邏輯
        has_road = any(road in address for road in ['路', '街', '大道'])
        has_location_marker = ('號' in address or '段' in address or '巷' in address)
        has_city_county = any(city in address for city in ['市', '縣'])
        is_long_enough = len(address) > 4  # 進一步降低長度要求
        
        # 台北地址通常沒有「市」字，但有明確的路名和門牌
        if is_long_enough and has_road and has_location_marker:
            
            # 嘗試更簡化的查詢
            simplified_parts = []
            
            # 提取市/縣（如果有的話）
            city_match = re.search(r'([\u4e00-\u9fff]+[市縣])', address)
            if city_match:
                simplified_parts.append(city_match.group(1))
            else:
                # 根據搜尋位置推斷預設城市
                default_city = '台北市'  # 預設值
                if search_location:
                    if '屏東' in search_location or '海生館' in search_location or '車城' in search_location:
                        default_city = '屏東縣'
                    elif '高雄' in search_location:
                        default_city = '高雄市'
                    elif '台中' in search_location:
                        default_city = '台中市'
                    elif '台南' in search_location:
                        default_city = '台南市'
                simplified_parts.append(default_city)
            
            # 提取區/鄉/鎮 (更精確的匹配)
            district_match = re.search(r'([^市縣]+[區鄉鎮])', address)
            if district_match:
                simplified_parts.append(district_match.group(1))
            
            # 智能提取道路和地址資訊
            # 先嘗試保留完整地址（包括巷弄門牌）
            road_match = re.search(r'([^區鄉鎮市縣]*(路|街|大道)[^區鄉鎮市縣]*)', address)
            if road_match:
                road_info = road_match.group(1).strip()
                # 清理多餘的空格和特殊字符
                road_info = re.sub(r'\s+', '', road_info)
                if road_info:
                    simplified_parts.append(road_info)
                    logger.debug(f"提取道路資訊: {road_info}")
            
            # 如果簡化解析失敗，記錄詳細信息以便調試
            logger.debug(f"簡化部分: {simplified_parts}")
            
            if len(simplified_parts) >= 2:  # 至少要有2個部分才進行簡化查詢
                simplified_address = ''.join(simplified_parts) + ", Taiwan"
                geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
                location = geolocator.geocode(simplified_address)
                if location and 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                    logger.info(f"完整地址簡化解析成功: {simplified_address} -> ({location.latitude}, {location.longitude})")
                    return (location.latitude, location.longitude)
        else:
            logger.info(f"地址不夠完整，跳過簡化解析: {address} (長度:{len(address)}, 有路名:{has_road}, 有位置標記:{has_location_marker})")

    except Exception as e:
        logger.warning(f"簡化地址解析失敗: {e}")
    
    logger.warning(f"地址解析失敗: {address}")
    return None

def validate_and_select_best_address(addresses: List[str]) -> Optional[str]:
    """
    驗證地址列表並選擇最佳地址 - 重點關注完整性
    :param addresses: 地址候選列表
    :return: 最佳地址或 None
    """
    if not addresses:
        return None
    
    # 地址評分函數 - 重新設計，更注重完整性
    def score_address(addr: str) -> int:
        score = 0
        addr = addr.strip()
        
        # 基礎長度評分
        if 12 <= len(addr) <= 60:
            score += 15  # 增加對合理長度的獎勵
        elif 8 <= len(addr) <= 80:
            score += 8
        
        # 完整性評分 - 提高權重
        has_city = any(keyword in addr for keyword in ['市', '縣'])
        has_district = any(keyword in addr for keyword in ['區', '鄉', '鎮'])
        has_road = any(keyword in addr for keyword in ['路', '街', '大道', '巷', '弄'])
        has_number = bool(re.search(r'\d+號', addr))
        has_postal = bool(re.match(r'^\d{3}', addr))
        
        if has_city:
            score += 20  # 提高市/縣的權重
        if has_district:
            score += 20  # 提高區的權重
        if has_road:
            score += 15  # 路名很重要
        if has_number:
            score += 12  # 門牌號碼很重要
        if has_postal:
            score += 8   # 郵遞區號加分
        
        # 詳細資訊加分
        if '段' in addr:
            score += 5
        if '巷' in addr:
            score += 4
        if '弄' in addr:
            score += 3
        if '樓' in addr:
            score += 2
        
        # 完整性檢查 - 重要的評分項目
        completeness_count = sum([has_city, has_district, has_road, has_number])
        if completeness_count >= 4:
            score += 25  # 非常完整的地址
        elif completeness_count >= 3:
            score += 15  # 較完整的地址
        elif completeness_count >= 2:
            score += 5   # 基本完整
        
        # 懲罰明顯錯誤的格式
        if re.search(r'[a-zA-Z]{5,}', addr):  # 包含太多英文
            score -= 15
        if len(addr) < 6:  # 太短
            score -= 20
        if '電話' in addr or '評分' in addr or '營業時間' in addr:  # 包含非地址資訊
            score -= 25
        if '公里' in addr or '分鐘' in addr or '小時' in addr:  # 時間距離資訊
            score -= 20
        
        return score
    
    # 對所有地址評分並排序
    scored_addresses = [(addr, score_address(addr)) for addr in addresses]
    scored_addresses.sort(key=lambda x: x[1], reverse=True)
    
    # 記錄所有候選地址的評分（用於調試）
    logger.debug("地址候選列表評分:")
    for addr, score in scored_addresses[:5]:  # 只顯示前5個
        logger.debug(f"  {addr[:30]}... -> 評分: {score}")
    
    # 返回評分最高且分數 > 10 的地址（提高門檻）
    if scored_addresses and scored_addresses[0][1] > 10:
        best_address = scored_addresses[0][0].strip()
        logger.info(f"選擇最佳地址: {best_address} (評分: {scored_addresses[0][1]})")
        return best_address
    
    return None

def is_valid_taiwan_address(address: str) -> bool:
    """
    檢查是否為有效的台灣地址
    :param address: 地址字串
    :return: 是否有效
    """
    if not address or len(address.strip()) < 3:
        return False
    
    address = address.strip()
    
    # 必須包含台灣地址的基本元素
    has_city = any(keyword in address for keyword in ['市', '縣'])
    has_district = any(keyword in address for keyword in ['區', '鄉', '鎮'])
    has_road = any(keyword in address for keyword in ['路', '街', '大道', '巷', '弄'])
    
    # 至少要有市/縣 + (區/鄉/鎮 或 路/街) 或者 區 + 路
    if has_city and (has_district or has_road):
        return True
    
    # 或者只有區和路也可以接受（如 "中山區民權東路"）
    if has_district and has_road:
        return True
    
    # 或者包含郵遞區號
    if re.match(r'^\d{3}', address) and (has_city or has_district or has_road):
        return True
    
    # 排除明顯非地址的內容
    exclude_keywords = ['電話', '評分', '營業時間', '公里', '分鐘', '星期', '小時', '網站', 'http']
    if any(keyword in address for keyword in exclude_keywords):
        return False
    
    return False

def clean_address(address: str) -> str:
    """
    清理地址格式
    :param address: 原始地址
    :return: 清理後的地址
    """
    if not address:
        return ""
    
    # 移除前後空白
    address = address.strip()
    
    # 移除常見的非地址前綴
    prefixes_to_remove = ['地址:', '地址：', '位於:', '位於：', '地點:', '地點：']
    for prefix in prefixes_to_remove:
        if address.startswith(prefix):
            address = address[len(prefix):].strip()
    
    # 移除常見的後綴資訊
    suffixes_to_remove = ['(', '（', '·', '•', '電話', '評分', '營業時間']
    for suffix in suffixes_to_remove:
        if suffix in address:
            address = address.split(suffix)[0].strip()
    
    # 移除多餘的空白字符
    address = re.sub(r'\s+', ' ', address)
    
    return address

def is_complete_address(address: str) -> bool:
    """
    檢查地址是否足夠完整 - 放寬台北地址的要求
    :param address: 地址字串
    :return: 是否完整
    """
    if not address or len(address.strip()) < 6:  # 放寬長度要求
        return False
    
    address = address.strip()
    
    # 檢查是否包含完整地址要素
    has_city = any(keyword in address for keyword in ['市', '縣'])
    has_district = any(keyword in address for keyword in ['區', '鄉', '鎮'])
    has_road = any(keyword in address for keyword in ['路', '街', '大道', '巷', '弄'])
    has_number = bool(re.search(r'\d+號', address))
    
    # 計算完整性評分
    completeness_score = sum([has_city, has_district, has_road, has_number])
    
    # 如果有郵遞區號，可以稍微降低要求
    has_postal = bool(re.match(r'^\d{3}', address))
    if has_postal:
        return completeness_score >= 3
    
    # 台北地址特殊處理：有路名+門牌號就算完整
    if has_road and has_number:
        return True
    
    # 或者有城市+區+路即可算完整
    if has_city and has_district and has_road:
        return True
    
    # 或者需要4個要素都有
    return completeness_score >= 4

def extract_address_from_maps_url(maps_url: str) -> Optional[str]:
    """
    從 Google Maps URL 嘗試提取完整地址
    :param maps_url: Google Maps URL
    :return: 提取的地址或 None
    """
    try:
        # 如果是短網址，先展開
        if 'goo.gl' in maps_url or len(maps_url) < 50:
            maps_url = expand_short_url(maps_url)
        
        # 從 URL 中的 place 部分提取地址
        place_match = re.search(r'/place/([^/@]+)', maps_url)
        if place_match:
            encoded_place = place_match.group(1)
            decoded_place = unquote(encoded_place).replace('+', ' ')
            
            # 檢查是否像地址
            if is_valid_taiwan_address(decoded_place):
                cleaned = clean_address(decoded_place)
                if is_complete_address(cleaned):
                    return cleaned
        
        # 嘗試使用 Selenium 獲取頁面上的地址
        try:
            driver = create_chrome_driver(headless=True)
            driver.get(maps_url)
            time.sleep(3)
            
            # 在 Google Maps 頁面尋找地址
            address_selectors = [
                "button[data-item-id='address']",
                "div[data-attrid='kc:/location/location:address']",
                "span[data-attrid='kc:/location/location:address']",
                ".QSFF4-text",
                ".Io6YTe",
                "div.rogA2c",
                "button.CsEnBe"
            ]
            
            for selector in address_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        text = elem.text.strip()
                        if is_valid_taiwan_address(text) and is_complete_address(text):
                            driver.quit()
                            return clean_address(text)
                except:
                    continue
            
            driver.quit()
            
        except Exception as e:
            logger.debug(f"Selenium 提取地址失敗: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"從 Maps URL 提取地址失敗: {e}")
        return None

def parse_google_maps_url(url: str) -> Optional[Dict[str, Any]]:
    """
    解析 Google Maps URL 提取餐廳資訊
    :param url: Google Maps URL
    :return: 餐廳資訊字典或 None
    """
    try:
        # 處理短網址展開
        if 'maps.app.goo.gl' in url or 'goo.gl' in url:
            session = create_session()
            response = session.get(url, allow_redirects=True, timeout=10)
            url = response.url
        
        # 解析不同格式的 Google Maps URL
        restaurant_info = {
            'name': None,
            'address': None,
            'maps_url': url,
            'latitude': None,
            'longitude': None,
            'rating': None,
            'price_level': None
        }
        
        # 從 URL 參數提取資訊
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # 提取座標
        if '/place/' in url:
            # 格式: maps.google.com/maps/place/餐廳名/@緯度,經度,縮放z
            match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
            if match:
                restaurant_info['latitude'] = float(match.group(1))
                restaurant_info['longitude'] = float(match.group(2))
            
            # 提取餐廳名稱
            place_match = re.search(r'/place/([^/@]+)', url)
            if place_match:
                restaurant_info['name'] = unquote(place_match.group(1)).replace('+', ' ')
        
        # 嘗試從 URL 查詢參數提取
        if 'q' in query_params:
            restaurant_info['name'] = query_params['q'][0]
        
        return restaurant_info
        
    except Exception as e:
        print(f"[URL解析] 失敗: {e}")
        return None

def search_google_maps_web(keyword: str, location: str = "台灣") -> List[Dict[str, Any]]:
    """
    使用網頁搜尋 Google Maps 餐廳
    :param keyword: 搜尋關鍵字
    :param location: 地區限制
    :return: 餐廳資訊列表
    """
    try:
        session = create_session()
        
        # 構建搜尋 URL
        search_query = f"{keyword} 餐廳 {location}"
        encoded_query = quote(search_query)
        search_url = f"https://www.google.com/search?q={encoded_query}"
        
        print(f"[WebSearch] 搜尋: {search_query}")
        
        # 發送請求
        response = session.get(search_url, timeout=15)
        response.raise_for_status()
        
        # 解析 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        restaurants = []
        
        # 尋找 Google Maps 連結
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href')
            if href and ('maps.google' in href or 'maps.app.goo.gl' in href):
                # 清理 URL
                if href.startswith('/url?'):
                    url_param = parse_qs(urlparse(href).query).get('url', [None])[0]
                    if url_param:
                        href = url_param
                
                # 解析餐廳資訊
                restaurant_info = parse_google_maps_url(href)
                if restaurant_info and restaurant_info.get('name'):
                    # 避免重複
                    if not any(r['name'] == restaurant_info['name'] for r in restaurants):
                        restaurants.append(restaurant_info)
                        if len(restaurants) >= 10:  # 限制結果數量
                            break
        
        return restaurants
        
    except Exception as e:
        print(f"[WebSearch] 搜尋失敗: {e}")
        return []

def search_duckduckgo(keyword: str, location: str = "台灣") -> List[Dict[str, Any]]:
    """
    使用 DuckDuckGo 搜尋餐廳（備用方案）
    :param keyword: 搜尋關鍵字
    :param location: 地區限制
    :return: 餐廳資訊列表
    """
    try:
        session = create_session()
        
        search_query = f"{keyword} 餐廳 {location} site:maps.google.com"
        encoded_query = quote(search_query)
        search_url = f"https://duckduckgo.com/html/?q={encoded_query}"
        
        print(f"[DuckDuckGo] 搜尋: {search_query}")
        
        response = session.get(search_url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        restaurants = []
        
        # 尋找搜尋結果
        results = soup.find_all('a', class_='result__a')
        for result in results:
            href = result.get('href')
            if href and 'maps.google' in href:
                restaurant_info = parse_google_maps_url(href)
                if restaurant_info and restaurant_info.get('name'):
                    restaurants.append(restaurant_info)
                    if len(restaurants) >= 5:
                        break
        
        return restaurants
        
    except Exception as e:
        print(f"[DuckDuckGo] 搜尋失敗: {e}")
        return []

def calculate_walking_distance_from_google_maps(user_address: str, restaurant_address: str) -> Tuple[float, int, str]:
    """
    使用 Google Maps 網頁版獲取真實的步行距離和時間
    :param user_address: 使用者地址
    :param restaurant_address: 餐廳地址
    :return: (距離(公里), 步行時間(分鐘), Google Maps URL)
    """
    try:
        # 構建 Google Maps 路線查詢 URL
        base_url = "https://www.google.com/maps/dir/"
        encoded_user = urllib.parse.quote(user_address)
        encoded_restaurant = urllib.parse.quote(restaurant_address)
        url = f"{base_url}{encoded_user}/{encoded_restaurant}"
        
        print(f"🚶 正在查詢實際步行路線: {user_address} → {restaurant_address}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            content = response.text
            
            # 尋找步行距離和時間的模式
            # Google Maps 通常顯示如 "1 分 (89 公尺)" 或 "5 分鐘 (400 公尺)"
            walking_pattern = r'(\d+)\s*分[鐘]?\s*\((\d+)\s*[公]?[尺米][尺]?\)'
            walking_match = re.search(walking_pattern, content)
            
            if walking_match:
                minutes = int(walking_match.group(1))
                meters = int(walking_match.group(2))
                distance_km = meters / 1000.0
                
                print(f"✅ Google Maps 路線: {minutes}分鐘, {meters}公尺")
                return round(distance_km, 3), minutes, url
            
            # 備用模式：尋找其他可能的格式
            distance_patterns = [
                r'(\d+)\s*公尺',
                r'(\d+)\s*米',
                r'(\d+\.\d+)\s*公里',
                r'(\d+\.\d+)\s*km'
            ]
            
            for pattern in distance_patterns:
                match = re.search(pattern, content)
                if match:
                    value = float(match.group(1))
                    if '公里' in pattern or 'km' in pattern:
                        distance_km = value
                    else:
                        distance_km = value / 1000.0
                    
                    # 估算步行時間（假設每分鐘80公尺）
                    estimated_minutes = int((distance_km * 1000) / 80)
                    print(f"✅ Google Maps 距離: {distance_km:.3f}km (估算{estimated_minutes}分鐘)")
                    return round(distance_km, 3), estimated_minutes, url
        
        print(f"❌ 無法從 Google Maps 獲取步行路線資訊")
        return None, None, url  # 即使無法獲取距離，也返回URL供用戶點擊
        
    except Exception as e:
        print(f"❌ Google Maps 路線查詢失敗: {str(e)}")
        # 即使發生錯誤，也嘗試構建基本的 Google Maps URL
        try:
            base_url = "https://www.google.com/maps/dir/"
            encoded_user = urllib.parse.quote(user_address)
            encoded_restaurant = urllib.parse.quote(restaurant_address)
            url = f"{base_url}{encoded_user}/{encoded_restaurant}"
            return None, None, url
        except:
            for pattern in distance_patterns:
                match = re.search(pattern, content)
                if match:
                    value = float(match.group(1))
                    if '公里' in pattern or 'km' in pattern:
                        distance_km = value
                    else:
                        distance_km = value / 1000.0
                    
                    # 估算步行時間（假設每分鐘80公尺）
                    estimated_minutes = int((distance_km * 1000) / 80)
                    print(f"✅ Google Maps 距離: {distance_km:.3f}km (估算{estimated_minutes}分鐘)")
                    return round(distance_km, 3), estimated_minutes, url
        
        print(f"❌ 無法從 Google Maps 獲取步行路線資訊")
        return None, None, url  # 即使無法獲取距離，也返回URL供用戶點擊
        
    except Exception as e:
        print(f"❌ Google Maps 路線查詢失敗: {str(e)}")
        # 即使發生錯誤，也嘗試構建基本的 Google Maps URL
        try:
            base_url = "https://www.google.com/maps/dir/"
            encoded_user = urllib.parse.quote(user_address)
            encoded_restaurant = urllib.parse.quote(restaurant_address)
            url = f"{base_url}{encoded_user}/{encoded_restaurant}"
            return None, None, url
        except:
            return None, None, None
        print(f"❌ Google Maps 路線查詢失敗: {str(e)}")
        return None, None

def calculate_distance(user_coords: Tuple[float, float], restaurant_coords: Tuple[float, float]) -> float:
    """
    計算兩點間直線距離（僅作為備用方案）
    :param user_coords: 使用者座標 (lat, lon)
    :param restaurant_coords: 餐廳座標 (lat, lon)
    :return: 距離（公里）
    """
    try:
        distance = geodesic(user_coords, restaurant_coords).kilometers
        return round(distance, 2)
    except Exception:
        return None

def estimate_distance_by_address(user_address: str, restaurant_address: str) -> float:
    """
    基於地址相似度估算距離（當GPS座標相同時的備用方案）
    針對台灣地址的巷弄門牌進行智能估算
    """
    import re
    
    try:
        # 清理地址格式
        user_clean = user_address.replace('台北市', '').replace('松山區', '').strip()
        restaurant_clean = restaurant_address.replace('台北市', '').replace('松山區', '').strip()
        
        # 提取地址組件
        def extract_address_components(addr):
            components = {}
            # 路段
            road_match = re.search(r'([^市縣區鄉鎮]*[路街大道](?:一|二|三|四|五|六|七|八|九|\d+)*段?)', addr)
            components['road'] = road_match.group(1) if road_match else ''
            
            # 巷號
            lane_match = re.search(r'(\d+)巷', addr)
            components['lane'] = int(lane_match.group(1)) if lane_match else 0
            
            # 弄號
            alley_match = re.search(r'(\d+)弄', addr)
            components['alley'] = int(alley_match.group(1)) if alley_match else 0
            
            # 門牌號
            number_match = re.search(r'(\d+)號', addr)
            components['number'] = int(number_match.group(1)) if number_match else 0
            
            return components
        
        user_comp = extract_address_components(user_clean)
        restaurant_comp = extract_address_components(restaurant_clean)
        
        # 如果不在同一路段，返回較大距離
        if user_comp['road'] != restaurant_comp['road']:
            return 1.0  # 不同路段，估算1公里
        
        # 計算地址差異距離
        distance = 0.0
        
        # 巷的差異（每差1巷約100-200米）
        lane_diff = abs(user_comp['lane'] - restaurant_comp['lane'])
        if lane_diff > 0:
            distance += lane_diff * 0.15  # 每巷150米
        
        # 弄的差異（每差1弄約50-100米）
        alley_diff = abs(user_comp['alley'] - restaurant_comp['alley'])
        if alley_diff > 0:
            distance += alley_diff * 0.08  # 每弄80米
        
        # 門牌號的差異（每差10號約50米）
        number_diff = abs(user_comp['number'] - restaurant_comp['number'])
        if number_diff > 0:
            distance += (number_diff / 10) * 0.05  # 每10號50米
        
        # 如果都在同一巷弄，至少有最小距離
        if distance == 0:
            distance = 0.05  # 同巷弄最小50米
        
        return round(distance, 2)
        
    except Exception as e:
        logger.debug(f"地址距離估算失敗: {e}")
        return 0.1  # 預設100米

def search_restaurants_parallel(keyword: str, location_info: Optional[Dict] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    並行搜尋餐廳 - 多工處理優化版本
    使用瀏覽器池和多執行緒並行搜尋，大幅提升搜尋速度
    
    :param keyword: 搜尋關鍵字
    :param location_info: 位置資訊
    :param max_results: 最大結果數
    :return: 餐廳資訊列表
    """
    
    # 檢查快取
    cached_results = search_cache.get(keyword, location_info)
    if cached_results:
        logger.info(f"📦 使用快取結果，關鍵字: {keyword}")
        return cached_results[:max_results]
    
    logger.info(f"🚀 開始並行搜尋餐廳: {keyword}")
    start_time = time.time()
    
    # 構建搜尋查詢
    if location_info and location_info.get('address'):
        search_query = f"{location_info['address']} {keyword} 餐廳"
    else:
        search_query = f"{keyword} 餐廳 台灣"

    encoded_query = quote(search_query)
    
    # 取得搜尋位置的座標，用於Maps搜尋
    search_coords = "25.0478,121.5318"  # 預設台北座標
    user_coords = None
    
    # 檢查多種可能的座標key
    if location_info:
        if location_info.get('coordinates'):
            user_coords = location_info['coordinates']
        elif location_info.get('coords'):
            user_coords = location_info['coords']
    
    if user_coords:
        lat, lng = user_coords
        search_coords = f"{lat},{lng}"
        logger.info(f"✅ 使用用戶座標進行搜尋: ({lat:.4f}, {lng:.4f})")
    else:
        logger.warning("⚠️ 未找到用戶座標，使用預設台北座標")
    
    # 精簡搜尋策略 - 只用最有效的一種
    search_strategies = [
        {
            'name': 'Maps直接搜尋',
            'url': f"https://www.google.com/maps/search/{encoded_query}/@{search_coords},12z",
            'priority': 1
        }
    ]
    
    all_restaurants = []
    
    # 使用 ThreadPoolExecutor 並行執行搜尋策略
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        # 提交所有搜尋任務
        future_to_strategy = {
            executor.submit(execute_search_strategy_with_pool, strategy, location_info, keyword): strategy 
            for strategy in search_strategies
        }
        
        # 收集結果
        for future in concurrent.futures.as_completed(future_to_strategy):
            strategy = future_to_strategy[future]
            
            try:
                restaurants = future.result()
                if restaurants:
                    logger.info(f"✅ {strategy['name']} 找到 {len(restaurants)} 個結果")
                    all_restaurants.extend(restaurants)
                else:
                    logger.warning(f"❌ {strategy['name']} 未找到結果")
                    
            except Exception as e:
                logger.error(f"❌ {strategy['name']} 執行失敗: {e}")
            
            # 如果已經有足夠的結果，可以考慮提前結束
            if len(all_restaurants) >= max_results * 1.5:  # 多收集一些以便篩選
                logger.info(f"✨ 已收集足夠結果 ({len(all_restaurants)})，加速完成")
                break
    
    # 去重
    unique_restaurants = remove_duplicate_restaurants(all_restaurants)
    
    # 如果有位置資訊，按距離排序
    if location_info and location_info.get('coords'):
        unique_restaurants = sort_restaurants_by_distance(unique_restaurants, location_info['coords'])
    
    # 限制結果數量
    final_results = unique_restaurants[:max_results]
    
    # 快取結果
    if final_results:
        search_cache.set(keyword, location_info, final_results)
    
    elapsed_time = time.time() - start_time
    logger.info(f"🎉 並行搜尋完成！找到 {len(final_results)} 家餐廳，耗時 {elapsed_time:.2f} 秒")
    
    return final_results

def execute_search_strategy_with_pool(strategy: Dict, location_info: Optional[Dict] = None, keyword: str = "") -> List[Dict[str, Any]]:
    """
    使用瀏覽器池執行單個搜尋策略
    
    :param strategy: 搜尋策略配置
    :param location_info: 位置資訊
    :param keyword: 搜尋關鍵字
    :return: 餐廳列表
    """
    
    restaurants = []
    
    try:
        with browser_pool.get_browser() as driver:
            logger.info(f"🔍 執行 {strategy['name']}: {strategy['url']}")
            
            # 訪問搜尋頁面
            driver.get(strategy['url'])
            
            # 大幅縮短等待時間
            time.sleep(0.5)  # 只等待 0.5 秒
            
            # 檢查是否被阻擋
            if "sorry" in driver.current_url.lower() or "captcha" in driver.page_source.lower():
                logger.warning(f"❌ {strategy['name']} 被 Google 阻擋")
                return restaurants
            
            # 尋找搜尋結果
            result_elements = find_search_results(driver)
            
            if not result_elements:
                logger.warning(f"❌ {strategy['name']} 未找到結果元素")
                return restaurants
            
            # 提取餐廳資訊（限制數量避免過載）
            for element in result_elements[:8]:  # 減少到 8 個
                try:
                    restaurant_info = extract_restaurant_info_minimal(element, location_info, keyword)
                    if restaurant_info and restaurant_info.get('name'):
                        # 檢查是否為餐廳相關
                        if is_restaurant_relevant(restaurant_info['name'], keyword):
                            restaurants.append(restaurant_info)
                            logger.debug(f"✅ 找到餐廳: {restaurant_info['name']}")
                        
                except Exception as e:
                    logger.debug(f"提取餐廳資訊失敗: {e}")
                    continue
            
            logger.info(f"✅ {strategy['name']} 成功提取 {len(restaurants)} 家餐廳")
            
    except Exception as e:
        logger.error(f"❌ {strategy['name']} 執行失敗: {e}")
    
    return restaurants

def remove_duplicate_restaurants(restaurants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    去除重複的餐廳
    
    :param restaurants: 餐廳列表
    :return: 去重後的餐廳列表
    """
    
    seen_names = set()
    unique_restaurants = []
    
    for restaurant in restaurants:
        name = restaurant.get('name', '').strip()
        if name and name not in seen_names:
            seen_names.add(name)
            unique_restaurants.append(restaurant)
    
    return unique_restaurants

def sort_restaurants_by_distance(restaurants: List[Dict[str, Any]], user_coords: Tuple[float, float]) -> List[Dict[str, Any]]:
    """
    按距離排序餐廳
    
    :param restaurants: 餐廳列表
    :param user_coords: 用戶座標
    :return: 排序後的餐廳列表
    """
    
    def get_distance_key(restaurant):
        distance = restaurant.get('distance_km')
        return distance if distance is not None else float('inf')
    
    return sorted(restaurants, key=get_distance_key)

def extract_restaurant_info_minimal(element, location_info: Optional[Dict] = None, search_keyword: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    精簡但完整的餐廳資訊提取 - 獲取名稱、地址、評分、價格
    
    :param element: 搜尋結果元素
    :param location_info: 位置資訊
    :return: 餐廳資訊字典
    """
    
    restaurant_info = {
        'name': '',
        'address': '',
        'rating': None,
        'price_level': None,
        'distance_km': None,
        'distance': '距離未知',
        'maps_url': '',
        'phone': '',
        'review_count': None
    }
    
    try:
        # 提取名稱
        name_selectors = ["span.OSrXXb", "h3.LC20lb", "div.qBF1Pd", "span.LrzXr"]
        
        for selector in name_selectors:
            try:
                name_element = element.find_element(By.CSS_SELECTOR, selector)
                name = name_element.text.strip()
                if name and len(name) > 1:
                    restaurant_info['name'] = name
                    break
            except:
                continue
        
        if not restaurant_info['name']:
            return None
        
        # 提取地址 - 使用更廣泛的選擇器和文字分析
        address_found = False
        
        # 方法1: 使用特定選擇器，優先找完整地址
        address_selectors = [
            # Google Maps 搜尋結果中的地址選擇器（優先級由高到低）
            "div.W4Efsd span.ZDu9vd",  # Google Maps 地址
            "span.LrzXr",  # 地址專用樣式
            "div.rllt__details div span",  # 詳細資訊區域中的 span
            "div.rllt__details div",  # 詳細資訊區域
            ".BNeawe.UPmit.AP7Wnd",  # 另一種地址樣式
            "div[data-value*='地址']",  # 包含地址的 div
            "span[title*='地址']",  # 標題包含地址的 span
            # 更多通用選擇器
            "div.fontBodyMedium",
            "span.fontBodyMedium", 
            "div.UaQhfb span",
            "div.lI9IFe span",
            # 包含台灣地址關鍵字的任何元素
            "*[class*='address']",
            "div:contains('台北')", "div:contains('新北')", "div:contains('桃園')",
            "span:contains('路')", "span:contains('街')", "span:contains('號')",
        ]
        
        for selector in address_selectors:
            try:
                address_elements = element.find_elements(By.CSS_SELECTOR, selector)
                for addr_elem in address_elements:
                    addr_text = addr_elem.text.strip()
                    
                    # 清理地址前面的特殊符號
                    addr_text = re.sub(r'^[·•\-\s]+', '', addr_text)
                    
                    # 檢查是否為有效的台灣地址
                    if (addr_text and len(addr_text) > 3 and  
                        # 包含地址相關關鍵字
                        any(keyword in addr_text for keyword in ['路', '街', '巷', '號', '市', '區', '縣', '鄉']) and
                        # 排除明顯的非地址內容
                        not any(avoid in addr_text for avoid in ['評論', '則評論', '星級', '公里', '小時', '營業', 'Google', '分鐘'])):
                        
                        # 優先選擇完整地址（包含縣市區）
                        is_complete = any(city in addr_text for city in ['台北市', '新北市', '桃園市', '台中市', '台南市', '高雄市'])
                        
                        if is_complete:
                            restaurant_info['address'] = addr_text
                            address_found = True
                            logger.info(f"✅ 找到完整地址: {addr_text}")
                            break
                        else:
                            # 不完整地址，嘗試根據搜尋位置補全
                            if search_keyword:
                                completed_addr = smart_address_completion(addr_text, search_keyword)
                                if completed_addr != addr_text:  # 有補全成功
                                    restaurant_info['address'] = completed_addr
                                    address_found = True
                                    logger.info(f"✅ 補全地址成功: {addr_text} -> {completed_addr}")
                                    break
                            
                            # 如果無法補全，保留原地址作為備用
                            if not restaurant_info.get('address'):
                                restaurant_info['address'] = addr_text
                                logger.debug(f"保留部分地址: {addr_text}")
                
                if address_found:
                    break
            except:
                continue
        
        # 方法2: 如果特定選擇器失敗，從完整文字中提取地址
        if not address_found:
            try:
                full_text = element.text
                # 更寬鬆的台灣地址模式
                address_patterns = [
                    # 任何包含地址元素的文字
                    r'[\u4e00-\u9fff]*[市縣區鄉鎮][\u4e00-\u9fff]*[路街巷弄大道][^\s\n]*',
                    r'[\u4e00-\u9fff]+[路街大道]\d+[號]?[^\s\n]*',
                    r'[\u4e00-\u9fff]+[市縣][^\s\n]*',
                    r'新北市[^\s\n]*|台北市[^\s\n]*|桃園市[^\s\n]*|台中市[^\s\n]*|台南市[^\s\n]*|高雄市[^\s\n]*',
                ]
                
                for pattern in address_patterns:
                    matches = re.findall(pattern, full_text)
                    if matches:
                        # 選擇任何找到的地址（降低要求）
                        for match in matches:
                            if len(match.strip()) > 3:  # 降低長度要求
                                restaurant_info['address'] = match.strip()
                                address_found = True
                                logger.info(f"✅ 從文字中找到地址: {match.strip()}")
                                break
                        if address_found:
                            break
            except:
                pass
        
        # 方法3: 如果還是沒有地址，檢查所有 span 元素
        if not address_found:
            try:
                spans = element.find_elements(By.TAG_NAME, "span")
                for span in spans:
                    span_text = span.text.strip()
                    # 最寬鬆的地址檢查
                    if (span_text and len(span_text) > 3 and  # 極低的長度要求
                        # 包含任何地址相關字詞
                        any(keyword in span_text for keyword in ['市', '縣', '區', '鄉', '鎮', '路', '街', '大道', '巷', '號', '台北', '新北', '桃園', '台中', '台南', '高雄']) and
                        # 只排除明顯的非地址內容
                        not any(avoid in span_text for avoid in ['評論', '星級', '公里', 'Google', 'Maps', '小時前', '營業中', '已打烊', 'rating', 'review'])):
                        restaurant_info['address'] = span_text
                        logger.info(f"✅ span方法找到地址: {span_text}")
                        break
            except:
                pass
        
        # 提取評分 - 使用更全面的選擇器和解析策略
        rating_selectors = [
            "span.yi40Hd",      # 主要評分樣式
            "span.MW4etd",      # 另一種評分樣式
            ".BTtC6e",          # 其他評分樣式
            "span[aria-label*='star']",  # 包含 star 的 aria-label
            "span[aria-label*='星']",    # 包含中文星的 aria-label
            "div.fontDisplayLarge", # 大字體評分
            "span.fontDisplayLarge", # 大字體評分
            ".ceNzKf",          # Google Maps 評分樣式
            "span.ZkP5Je",      # 新的評分樣式
            ".Aq14fc",          # 另一種新樣式
            "span[jsaction*='pane']", # 包含評分的互動元素
        ]
        
        logger.debug(f"開始搜尋評分 - 餐廳: {restaurant_info.get('name', '未知')}")
        
        for selector in rating_selectors:
            try:
                rating_elements = element.find_elements(By.CSS_SELECTOR, selector)
                logger.debug(f"選擇器 {selector} 找到 {len(rating_elements)} 個元素")
                
                for rating_element in rating_elements:
                    rating_text = rating_element.text.strip()
                    logger.debug(f"檢查評分文字: '{rating_text}'")
                    
                    # 多種評分格式解析
                    rating_patterns = [
                        r'^(\d+\.?\d*)$',        # 純數字: 4.5
                        r'(\d+\.?\d*)\s*星',      # 中文: 4.5星
                        r'(\d+\.?\d*)\s*star',    # 英文: 4.5 star
                        r'(\d+\.?\d*)/5',        # 分數: 4.5/5
                        r'(\d+\.?\d*)\s*out\s*of\s*5',  # 完整: 4.5 out of 5
                        r'評分\s*(\d+\.?\d*)',    # 評分 4.5
                    ]
                    
                    for pattern in rating_patterns:
                        rating_match = re.search(pattern, rating_text, re.IGNORECASE)
                        if rating_match:
                            rating_value = float(rating_match.group(1))
                            if 0 <= rating_value <= 5:  # 確保評分在合理範圍
                                restaurant_info['rating'] = rating_value
                                logger.info(f"✅ 找到評分: {rating_value} (來源: {rating_text}) - {restaurant_info.get('name', '未知')}")
                                break
                    if restaurant_info['rating'] is not None:
                        break
                if restaurant_info['rating'] is not None:
                    break
            except Exception as e:
                logger.debug(f"選擇器 {selector} 發生錯誤: {e}")
                continue
        
        # 如果上面的方法都失敗，嘗試從 aria-label 或完整文字中提取
        if restaurant_info['rating'] is None:
            try:
                # 檢查所有元素的 aria-label 和文字
                all_elements = element.find_elements(By.XPATH, ".//*")
                for elem in all_elements:
                    aria_label = elem.get_attribute('aria-label') or ''
                    elem_text = elem.text.strip()
                    
                    # 從 aria-label 或文字中找評分
                    for text in [aria_label, elem_text]:
                        if text and len(text) < 50:  # 避免處理過長文字
                            rating_patterns = [
                                r'(\d+\.?\d*)\s*(?:星|star|颗星)',
                                r'rated\s*(\d+\.?\d*)',
                                r'評分[：:]\s*(\d+\.?\d*)',
                                r'(\d+\.?\d*)\s*/\s*5',
                                r'^(\d+\.?\d*)$'  # 純數字，但限制在短文字內
                            ]
                            for pattern in rating_patterns:
                                rating_match = re.search(pattern, text, re.IGNORECASE)
                                if rating_match:
                                    rating_value = float(rating_match.group(1))
                                    if 0 <= rating_value <= 5:
                                        restaurant_info['rating'] = rating_value
                                        logger.debug(f"從文字/aria-label找到評分: {rating_value} (來源: {text[:30]})")
                                        break
                            if restaurant_info['rating'] is not None:
                                break
                    if restaurant_info['rating'] is not None:
                        break
            except:
                pass
        
        # 提取評論數 - 使用更多方法
        review_selectors = [
            "span.RDApEe",           # 主要評論樣式
            "a[href*='reviews']",     # 評論連結
            "span[aria-label*='review']",  # 包含 review 的 aria-label
            "span[aria-label*='則評論']",   # 中文評論 aria-label
        ]
        
        for selector in review_selectors:
            try:
                review_element = element.find_element(By.CSS_SELECTOR, selector)
                review_text = review_element.text.strip()
                
                # 嘗試多種評論數格式
                review_patterns = [
                    r'\((\d+)\)',           # (123) 格式
                    r'(\d+)\s*則評論',        # 123則評論 格式
                    r'(\d+)\s*reviews?',     # 123 reviews 格式
                    r'(\d+)\s*評論',         # 123評論 格式
                ]
                
                for pattern in review_patterns:
                    review_match = re.search(pattern, review_text, re.IGNORECASE)
                    if review_match:
                        restaurant_info['review_count'] = int(review_match.group(1))
                        break
                
                if restaurant_info['review_count'] is not None:
                    break
            except:
                continue
        
        # 如果還是沒有找到，檢查完整文字
        if restaurant_info['review_count'] is None:
            try:
                full_text = element.text
                review_patterns = [
                    r'\((\d+)\)',
                    r'(\d+)\s*則評論',
                    r'(\d+)\s*reviews?',
                    r'(\d+)\s*評論',
                ]
                
                for pattern in review_patterns:
                    review_match = re.search(pattern, full_text, re.IGNORECASE)
                    if review_match:
                        count = int(review_match.group(1))
                        if count > 0 and count < 100000:  # 合理範圍檢查
                            restaurant_info['review_count'] = count
                            break
            except:
                pass
        
        # 提取價格資訊
        try:
            full_text = element.text
            price_patterns = [
                r'\$(\d{2,4})-(\d{2,4})',  # $100-300 格式
                r'NT\$(\d{2,4})-(\d{2,4})',  # NT$100-300 格式
                r'(\d{2,4})-(\d{2,4})元',  # 100-300元 格式
                r'\$(\d{2,4})\+',  # $100+ 格式
                r'(\d{2,4})元',  # 100元 格式
            ]
            
            for pattern in price_patterns:
                price_match = re.search(pattern, full_text)
                if price_match:
                    groups = price_match.groups()
                    if len(groups) == 2:  # 價格區間
                        try:
                            low_price = int(groups[0])
                            high_price = int(groups[1])
                            if 10 <= low_price <= 5000 and 10 <= high_price <= 5000 and low_price < high_price:
                                restaurant_info['price_level'] = f"${low_price}-{high_price}"
                                break
                        except ValueError:
                            continue
                    elif len(groups) == 1:  # 單一價格
                        try:
                            price = int(groups[0])
                            if 10 <= price <= 5000:
                                if '+' in price_match.group(0):
                                    restaurant_info['price_level'] = f"${price}+"
                                else:
                                    restaurant_info['price_level'] = f"${price}"
                                break
                        except ValueError:
                            continue
        except:
            pass
        
        # 計算距離（如果有位置資訊和地址）
        if location_info and restaurant_info.get('address'):
            # 檢查多種可能的座標key
            user_coords = None
            if location_info.get('coords'):
                user_coords = location_info['coords']
            elif location_info.get('coordinates'):
                user_coords = location_info['coordinates']
            
            if user_coords:
                try:
                    logger.debug(f"嘗試計算距離 - 用戶座標: {user_coords}, 餐廳地址: {restaurant_info.get('address')}")
                    
                    # 改進餐廳地址處理，避免過度簡化
                    restaurant_address = restaurant_info['address']
                    
                    # 如果餐廳地址以 "·" 開頭，需要補全城市資訊
                    if restaurant_address.startswith('·'):
                        # 從用戶地址中提取城市區域資訊
                        search_location = location_info.get('address', '') if location_info else ''
                        if '市' in search_location and '區' in search_location:
                            # 提取市區資訊，例如 "台北市松山區"
                            import re
                            city_district_match = re.search(r'([^,]*?市[^,]*?區)', search_location)
                            if city_district_match:
                                city_district = city_district_match.group(1)
                                # 組合完整地址，移除開頭的 "·"
                                restaurant_address = city_district + restaurant_address[1:].strip()
                                logger.debug(f"補全餐廳地址: {restaurant_info['address']} -> {restaurant_address}")
                        else:
                            # 簡單補全台北市（預設）
                            restaurant_address = "台北市" + restaurant_address[1:].strip()
                    
                    restaurant_coords = geocode_address(restaurant_address, search_location)
                    if restaurant_coords:
                        # 優先使用 Google Maps 真實步行路線
                        user_address = location_info.get('address', '')
                        if user_address and restaurant_address:
                            walking_distance, walking_minutes, google_maps_url = calculate_walking_distance_from_google_maps(
                                user_address, restaurant_address
                            )
                            
                            # 保存 Google Maps URL，不論是否成功獲取距離
                            if google_maps_url:
                                restaurant_info['google_maps_url'] = google_maps_url
                            
                            if walking_distance is not None:
                                distance = walking_distance
                                restaurant_info['walking_minutes'] = walking_minutes
                                logger.info(f"🚶 Google Maps 步行路線: {distance:.3f}km, {walking_minutes}分鐘 - {restaurant_info.get('name', '未知餐廳')}")
                            else:
                                # 備用方案：使用GPS直線距離
                                distance = calculate_distance(user_coords, restaurant_coords)
                                logger.info(f"📍 使用GPS直線距離: {distance}km - {restaurant_info.get('name', '未知餐廳')}")
                        else:
                            # 備用方案：使用GPS直線距離
                            distance = calculate_distance(user_coords, restaurant_coords)
                            logger.info(f"📍 使用GPS直線距離: {distance}km - {restaurant_info.get('name', '未知餐廳')}")
                        
                        if distance is not None:
                            # 如果GPS計算距離為0，使用地址估算作為補充
                            if distance == 0.0:
                                estimated_distance = estimate_distance_by_address(
                                    location_info.get('address', ''), 
                                    restaurant_address
                                )
                                distance = estimated_distance
                                logger.info(f"🎯 使用地址估算距離: {distance} km - {restaurant_info.get('name', '未知餐廳')}")
                            
                            restaurant_info['distance_km'] = distance
                            # 格式化距離字串 - 優先使用 Google Maps 的格式
                            if restaurant_info.get('google_maps_url') and restaurant_info.get('walking_minutes'):
                                # 有 Google Maps 資料，使用步行時間格式
                                if distance < 1:
                                    distance_text = f"{int(distance * 1000)}公尺"
                                else:
                                    distance_text = f"{distance:.1f}公里"
                                restaurant_info['distance'] = distance_text
                            else:
                                # 沒有 Google Maps 資料，使用標準格式
                                if distance < 1:
                                    restaurant_info['distance'] = f"{int(distance * 1000)}公尺"
                                else:
                                    restaurant_info['distance'] = f"{distance:.1f}公里"
                            logger.info(f"✅ 距離計算成功: {distance} km - {restaurant_info.get('name', '未知餐廳')}")
                        else:
                            restaurant_info['distance'] = "距離未知"
                            logger.warning(f"❌ 距離計算返回 None - {restaurant_info.get('name', '未知餐廳')}")
                    else:
                        restaurant_info['distance'] = "距離未知"
                        logger.warning(f"❌ 餐廳地址地理編碼失敗: {restaurant_address}")
                except Exception as e:
                    logger.debug(f"距離計算異常: {e}")
            else:
                logger.debug(f"用戶座標為空，跳過距離計算: {location_info}")
        elif not location_info:
            logger.debug("無位置資訊，跳過距離計算")
        elif not restaurant_info.get('address'):
            logger.debug("餐廳地址為空，跳過距離計算")
        
        # 如果沒有距離，設為 None（不要設預設值）
        if restaurant_info['distance_km'] is None:
            restaurant_info['distance_km'] = None
        
        return restaurant_info
        
    except Exception as e:
        logger.debug(f"提取餐廳資訊失敗: {e}")
        return None

def search_restaurants_selenium(keyword: str, location_info: Optional[Dict] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    使用 Selenium 搜尋 Google Maps 餐廳
    :param keyword: 搜尋關鍵字（如：羊肉、火鍋、燒烤）
    :param location_info: 位置資訊 {'coords': (lat, lng), 'address': 'address_string'}
    :param max_results: 最大結果數
    :return: 餐廳資訊列表
    """
    driver = None
    try:
        logger.info(f"開始搜尋餐廳: {keyword}")
        
        # 建立瀏覽器
        driver = create_chrome_driver(headless=True)
        
        # 構建搜尋查詢
        if location_info and location_info.get('address'):
            search_query = f"{location_info['address']} {keyword} 餐廳"
        else:
            search_query = f"{keyword} 餐廳 台灣"
        
        # 建立 Google Local Search URL - 改進版，減少被偵測
        encoded_query = quote(search_query)
        
        # 取得搜尋位置的座標，用於Maps搜尋
        search_coords = "25.0478,121.5318"  # 預設台北座標
        if location_info and location_info.get('coordinates'):
            lat, lng = location_info['coordinates']
            search_coords = f"{lat},{lng}"
        
        # 嘗試不同的搜尋策略
        search_strategies = [
            f"https://www.google.com/maps/search/{encoded_query}/@{search_coords},12z",  # Maps 直接搜尋
            f"https://www.google.com/search?tbm=lcl&q={encoded_query}&hl=zh-TW",  # Local 搜尋
            f"https://www.google.com/search?q={encoded_query}+地址&hl=zh-TW"  # 一般搜尋加上地址關鍵字
        ]
        
        result_elements = []
        for strategy_index, search_url in enumerate(search_strategies):
            logger.info(f"嘗試搜尋策略 {strategy_index + 1}: {search_url}")
            
            try:
                # 訪問搜尋頁面
                driver.get(search_url)
                time.sleep(random.uniform(3, 6))  # 隨機等待時間
                
                # 檢查是否被 Google 阻擋
                if "sorry" in driver.current_url.lower() or "captcha" in driver.page_source.lower():
                    logger.warning(f"策略 {strategy_index + 1} 被 Google 阻擋，嘗試下一個策略")
                    continue
                
                # 嘗試尋找搜尋結果
                result_elements = find_search_results(driver)
                if result_elements:
                    logger.info(f"策略 {strategy_index + 1} 找到 {len(result_elements)} 個結果")
                    break
                else:
                    logger.warning(f"策略 {strategy_index + 1} 未找到結果")
                    
            except Exception as e:
                logger.warning(f"搜尋策略 {strategy_index + 1} 失敗: {e}")
                continue
        
        if not result_elements:
            logger.warning("所有搜尋策略都失敗，無法找到搜尋結果")
            return []
        
        restaurants = []
        # 提取餐廳資訊
        for i, element in enumerate(result_elements[:max_results]):
            try:
                restaurant_info = extract_restaurant_info_minimal(element, location_info, keyword)
                if restaurant_info and restaurant_info.get('name'):
                    # 檢查是否為餐廳相關
                    if is_restaurant_relevant(restaurant_info['name'], keyword):
                        restaurants.append(restaurant_info)
                        logger.info(f"找到餐廳: {restaurant_info['name']}")
                
            except Exception as e:
                logger.error(f"提取第 {i+1} 個結果失敗: {e}")
                continue
        
        logger.info(f"總共找到 {len(restaurants)} 家餐廳")
        return restaurants
        
    except Exception as e:
        logger.error(f"Selenium 搜尋失敗: {e}")
        return []
        
    finally:
        if driver:
            driver.quit()

def find_search_results(driver) -> List:
    """
    在搜尋頁面中尋找結果元素
    :param driver: WebDriver 實例
    :return: 搜尋結果元素列表
    """
    # 嘗試多種元素選擇器策略 - 更新的 Google 結構
    selectors = [
        "div.VkpGBb",  # 新版 Google Local 結果容器
        "div.dbg0pd",  # 另一種結果容器
        "div.rllt__details",  # 本地搜尋結果詳情
        "div.UaQhfb",  # 地圖搜尋結果
        "div[data-ved]",  # 通用的有 data-ved 屬性的容器
        ".g",  # 傳統搜尋結果
        "div.Nv2PK",  # 新的地方搜尋結果
        "div.P7xzyf",  # 另一種地方結果格式
        "article",  # HTML5 文章元素
        "div[role='article']",  # 語義化搜尋結果
        "div.tF2Cxc",  # 新版搜尋結果容器
        "div.MjjYud"  # 另一種新版容器
    ]
    
    result_elements = []
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                logger.info(f"使用選擇器 {selector} 找到 {len(elements)} 個元素")
                result_elements = elements
                break
        except Exception:
            continue
    
    return result_elements

def extract_restaurant_info_from_element_improved(element, location_info: Optional[Dict] = None, driver=None, keyword: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    改進版餐廳資訊提取函數 - 現在直接調用精簡版本
    :param element: Selenium WebElement
    :param location_info: 使用者位置資訊
    :param driver: WebDriver 實例
    :param keyword: 搜尋關鍵詞
    :return: 餐廳資訊字典
    """
    # 直接調用精簡版本，大幅提升速度
    return extract_restaurant_info_minimal(element, location_info, keyword)

def is_restaurant_relevant(restaurant_name: str, keyword: str) -> bool:
    """
    檢查餐廳是否與搜尋關鍵字相關
    :param restaurant_name: 餐廳名稱
    :param keyword: 搜尋關鍵字
    :return: 是否相關
    """
    # 如果餐廳名稱為空或太短，暫時接受（寬鬆策略）
    if not restaurant_name or len(restaurant_name) < 2:
        return True  # 寬鬆接受，讓其他驗證來篩選
    
    # 餐廳相關關鍵字
    restaurant_keywords = [
        '餐廳', '飯店', '食堂', '小吃', '美食', '料理', 
        '火鍋', '燒烤', '拉麵', '義大利麵', '牛排', '壽司',
        '羊肉', '牛肉', '豬肉', '雞肉', '海鮮', '素食',
        '早餐', '午餐', '晚餐', '宵夜', '咖啡', '茶',
        '中式', '西式', '日式', '韓式', '泰式', '義式',
        '店', '館', '坊', '軒', '閣', '樓', '屋'  # 增加常見店家後綴
    ]
    
    # 檢查餐廳名稱是否包含餐廳相關字詞
    name_lower = restaurant_name.lower()
    keyword_lower = keyword.lower()
    
    # 如果餐廳名稱包含搜尋關鍵字
    if keyword_lower in name_lower:
        return True
    
    # 如果餐廳名稱包含餐廳相關關鍵字
    if any(kw in restaurant_name for kw in restaurant_keywords):
        return True
    
    # 排除明顯非餐廳的結果
    exclude_keywords = ['銀行', '醫院', '學校', '公司', '政府', '機關', '停車場', '加油站', '便利商店', '超市']
    if any(kw in restaurant_name for kw in exclude_keywords):
        return False
    
    # 寬鬆策略：如果不是明顯排除的類型，就接受
    return True
def search_restaurants(keyword: str, user_address: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    搜尋餐廳主函數（支援多種輸入格式）
    :param keyword: 搜尋關鍵字
    :param user_address: 使用者地址或 Google Maps 短網址
    :param max_results: 最大結果數
    :return: 餐廳資訊列表
    """
    location_info = None
    
    # 處理使用者位置資訊
    if user_address:
        if user_address.startswith('http') and ('maps.app.goo.gl' in user_address or 'maps.google' in user_address or 'g.co/kgs/' in user_address or 'goo.gl' in user_address):
            # 處理 Google Maps 短網址
            logger.info(f"處理 Google Maps URL: {user_address}")
            location_data = extract_location_from_url(user_address)
            if location_data:
                lat, lng, place_name = location_data
                location_info = {
                    'coords': (lat, lng),
                    'address': place_name or user_address
                }
                logger.info(f"從 URL 提取位置: {place_name} ({lat}, {lng})")
        else:
            # 處理一般地址
            logger.info(f"處理地址: {user_address}")
            coords = geocode_address(user_address, user_address)
            if coords:
                location_info = {
                    'coords': coords,
                    'coordinates': coords,  # 同時設定兩個鍵以確保兼容性
                    'address': user_address
                }
                logger.info(f"地址座標: {coords}")
            else:
                # 即使無法獲得座標，也保留地址用於搜尋
                location_info = {
                    'coords': None,
                    'coordinates': None,  # 同時設定兩個鍵以確保兼容性
                    'address': user_address
                }
                logger.warning(f"無法獲得地址座標，僅用於搜尋: {user_address}")
    
    # 使用並行搜尋（優先）或傳統 Selenium 搜尋
    try:
        results = search_restaurants_parallel(keyword, location_info, max_results)
        if results:
            logger.info(f"🚀 並行搜尋成功找到 {len(results)} 個結果")
        else:
            logger.info("並行搜尋無結果，嘗試傳統 Selenium 搜尋")
            results = search_restaurants_selenium(keyword, location_info, max_results)
    except Exception as e:
        logger.warning(f"並行搜尋失敗: {e}，使用傳統搜尋")
        results = search_restaurants_selenium(keyword, location_info, max_results)
    
    # 如果 Selenium 失敗，使用備用方案
    if not results:
        logger.info("Selenium 搜尋無結果，使用備用搜尋方案")
        results = search_google_maps_web_fallback(keyword, location_info)
    
    # 為每個結果驗證並優化URL
    for restaurant in results:
        if restaurant.get('name'):
            reliable_url = get_reliable_maps_url(restaurant)
            restaurant['maps_url'] = reliable_url
            logger.debug(f"為 {restaurant['name']} 優化URL: {reliable_url[:50]}...")
    
    return results

def search_google_maps_web_fallback(keyword: str, location_info: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """
    備用搜尋方案（使用 requests）
    """
    try:
        location_str = "台灣"
        if location_info and location_info.get('address'):
            location_str = location_info['address']
        
        return search_google_maps_web(keyword, location_str)
    except Exception as e:
        logger.error(f"備用搜尋失敗: {e}")
        return []

# 測試函數更新
def test_search_cases():
    """測試各種搜尋案例"""
    test_cases = [
        # (user_address, keyword, 說明)
        ("https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6", "羊肉", "短網址+羊肉"),
        ("243新北市泰山區明志路二段210號", "火鍋", "泰山火鍋"),
        ("彰化大佛", "燒烤", "彰化大佛燒烤"),
        ("台北中山區", "義大利麵", "中山區義大利麵(無詳細地址)")
    ]
    
    for idx, (addr, kw, desc) in enumerate(test_cases, 1):
        print(f"\n=== 測試案例 {idx}: {desc} ===")
        print(f"位置: {addr}")
        print(f"關鍵字: {kw}")
        print("-" * 50)
        
        try:
            results = search_restaurants(keyword=kw, user_address=addr, max_results=5)
            
            if not results:
                print("❌ 沒有找到相關餐廳！")
            else:
                print(f"✅ 找到 {len(results)} 家餐廳:")
                for i, restaurant in enumerate(results, 1):
                    print(f"\n{i}. 🍽️ {restaurant['name']}")
                    print(f"   📍 地址: {restaurant.get('address', '未提供')}")
                    if restaurant.get('distance_km') is not None:
                        print(f"   📏 距離: {restaurant['distance_km']} 公里")
                    if restaurant.get('rating'):
                        print(f"   ⭐ 評分: {restaurant['rating']}")
                    if restaurant.get('price_level'):
                        print(f"   💰 價格: {restaurant['price_level']}")
                    if restaurant.get('maps_url'):
                        print(f"   🔗 Google Maps: {restaurant['maps_url']}")
            
        except Exception as e:
            print(f"❌ 搜尋失敗: {e}")
        
        print("\n" + "="*80)
        time.sleep(2)  # 避免請求過快

def generate_fallback_maps_url(restaurant_name: str, address: str = "") -> str:
    """
    生成後備的Google Maps搜尋連結
    使用固定格式確保連結始終可用
    
    :param restaurant_name: 餐廳名稱
    :param address: 地址（可選）
    :return: Google Maps搜尋URL
    """
    try:
        encoded_name = quote(restaurant_name)
        if address:
            # 清理地址，只保留主要部分
            clean_address = address.split(',')[0].strip() if ',' in address else address.strip()
            encoded_address = quote(clean_address)
            return f"https://www.google.com/maps/search/{encoded_name}+{encoded_address}"
        else:
            return f"https://www.google.com/maps/search/{encoded_name}"
    except Exception as e:
        logger.warning(f"生成後備URL失敗: {e}")
        return f"https://www.google.com/maps/search/{restaurant_name}"

def validate_maps_url(url: str) -> bool:
    """
    驗證Google Maps URL是否可用
    
    :param url: 要驗證的URL
    :return: True if URL is accessible, False otherwise
    """
    if not url:
        return False
        
    try:
        # 跳過SSL驗證和警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(
            url, 
            headers={'User-Agent': random.choice(USER_AGENTS)}, 
            timeout=10,
            verify=False,
            allow_redirects=True
        )
        return response.status_code == 200
    except Exception:
        return False

def get_reliable_maps_url(restaurant_info: dict) -> str:
    """
    獲取可靠的Google Maps連結
    優先順序：
    1. 系統提取的原始URL（如果可用）
    2. 簡化搜尋URL + 地址
    3. 純餐廳名稱搜尋URL
    
    :param restaurant_info: 餐廳資訊字典
    :return: 可靠的Google Maps URL
    """
    name = restaurant_info.get('name', '')
    address = restaurant_info.get('address', '').split(',')[0] if restaurant_info.get('address') else ''
    original_url = restaurant_info.get('maps_url', '')
    
    # 測試原始URL（快速驗證，不需要實際請求）
    if original_url and '/maps/place/' in original_url and '!' in original_url:
        # 原始URL看起來是正確的餐廳格式
        return original_url
    
    # 後備方案1：餐廳名稱 + 地址
    if name and address:
        fallback_url = generate_fallback_maps_url(name, address)
        return fallback_url
    
    # 後備方案2：純餐廳名稱
    if name:
        simple_url = generate_fallback_maps_url(name)
        return simple_url
    
    # 最終後備：原始URL（即使可能不可用）
    return original_url or "https://www.google.com/maps"

def get_restaurant_details(maps_url: str) -> Optional[Dict[str, Any]]:
    """
    獲取餐廳詳細資訊
    :param maps_url: Google Maps URL
    :return: 詳細餐廳資訊
    """
    try:
        session = create_session()
        response = session.get(maps_url, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取餐廳詳細資訊
        details = {
            'name': None,
            'rating': None,
            'review_count': None,
            'price_level': None,
            'phone': None,
            'website': None,
            'hours': None,
            'address': None
        }
        
        # 這裡可以根據 Google Maps 的 HTML 結構提取更多詳細資訊
        # 由於 Google Maps 使用動態載入，完整實作需要 Selenium
        
        return details
        
    except Exception as e:
        print(f"[詳細資訊] 獲取失敗: {e}")
        return None

# 測試函數
def test_search():
    """測試搜尋功能"""
    print("🚀 開始測試 Google Maps 餐廳搜尋功能")
    print("=" * 80)
    test_search_cases()

if __name__ == "__main__":
    test_search()

# 清理函數
def cleanup_resources():
    """清理系統資源"""
    try:
        browser_pool.close_all()
        logger.info("✅ 資源清理完成")
    except Exception as e:
        logger.error(f"❌ 資源清理失敗: {e}")

# 確保程序退出時清理資源
import atexit
atexit.register(cleanup_resources)

def get_location_candidates(address: str, max_candidates: int = 3) -> List[Dict[str, Any]]:
    """
    獲取模糊地址的候選位置列表，讓用戶選擇正確的位置
    :param address: 地址字串
    :param max_candidates: 最大候選數量
    :return: 候選位置列表
    """
    if not address or len(address.strip()) < 2:
        return []
    
    candidates = []
    
    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
        
        # 構建多種查詢方式
        search_queries = []
        
        # 基本查詢
        search_queries.extend([
            address + ", Taiwan",
            address + ", 台灣",
            address
        ])
        
        # 如果是捷運站名，添加捷運相關查詢
        if address.endswith('站') and not any(keyword in address for keyword in ['市', '縣', '路', '街']):
            search_queries.extend([
                f"台北捷運{address}, Taiwan",
                f"捷運{address}, Taiwan",
                f"台北捷運{address}",
                f"捷運{address}"
            ])
        
        # 如果沒有市縣，添加台北市查詢
        if not any(city in address for city in ['市', '縣']) and any(road in address for road in ['路', '街', '大道']):
            search_queries.extend([
                f"台北市{address}, Taiwan",
                f"台北市{address}"
            ])
        
        seen_locations = set()  # 避免重複位置
        
        for query in search_queries:
            try:
                # 使用 limit 參數獲取多個結果
                locations = geolocator.geocode(query, limit=5, exactly_one=False)
                
                if locations:
                    for location in locations:
                        if location and location.latitude and location.longitude:
                            # 驗證座標在台灣範圍內
                            if 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                                # 創建位置標識符以避免重複
                                location_key = f"{location.latitude:.4f},{location.longitude:.4f}"
                                
                                if location_key not in seen_locations:
                                    seen_locations.add(location_key)
                                    
                                    # 解析地址資訊
                                    address_parts = location.address.split(', ')
                                    display_name = address_parts[0] if address_parts else location.address
                                    
                                    # 提取區域資訊
                                    district = ""
                                    city = ""
                                    for part in address_parts:
                                        if any(suffix in part for suffix in ['區', '鄉', '鎮']):
                                            district = part
                                        elif any(suffix in part for suffix in ['市', '縣']):
                                            city = part
                                    
                                    candidate = {
                                        'name': display_name,
                                        'full_address': location.address,
                                        'coordinates': [location.latitude, location.longitude],
                                        'district': district,
                                        'city': city,
                                        'query_used': query
                                    }
                                    
                                    candidates.append(candidate)
                                    
                                    if len(candidates) >= max_candidates:
                                        break
                        
                        if len(candidates) >= max_candidates:
                            break
                            
            except Exception as e:
                logger.debug(f"候選查詢失敗: {query} - {e}")
                continue
            
            if len(candidates) >= max_candidates:
                break
                
    except Exception as e:
        logger.error(f"獲取位置候選失敗: {e}")
    
    logger.info(f"為地址 '{address}' 找到 {len(candidates)} 個候選位置")
    return candidates

def geocode_address_with_options(address: str) -> Dict[str, Any]:
    """
    智能地址解析 - 如果地址模糊則返回候選選項，否則返回確定位置
    :param address: 地址字串
    :return: 包含位置資訊或候選選項的字典
    """
    if not address or len(address.strip()) < 2:
        return {
            'status': 'error',
            'message': '地址不能為空'
        }
    
    # 首先嘗試直接地理編碼
    coords = geocode_address(address)
    
    # 檢查是否為模糊地址（需要用戶選擇）
    is_ambiguous = False
    
    # 判斷是否為模糊地址的條件
    if address.endswith('站') and not any(keyword in address for keyword in ['市', '縣', '路', '街']):
        # 捷運站名可能模糊
        is_ambiguous = True
    elif len(address) <= 4 and not any(keyword in address for keyword in ['市', '縣', '區', '路', '街']):
        # 短地名可能模糊
        is_ambiguous = True
    
    if is_ambiguous or coords is None:
        # 獲取候選位置
        candidates = get_location_candidates(address, max_candidates=3)
        
        if len(candidates) > 1:
            # 多個候選，需要用戶選擇
            return {
                'status': 'multiple_options',
                'message': f'找到多個 "{address}" 的可能位置，請選擇正確的位置：',
                'candidates': candidates,
                'original_query': address
            }
        elif len(candidates) == 1:
            # 只有一個候選，直接使用
            candidate = candidates[0]
            return {
                'status': 'success',
                'message': '位置解析成功',
                'location': {
                    'address': candidate['full_address'],
                    'coordinates': candidate['coordinates'],
                    'name': candidate['name']
                }
            }
        else:
            # 沒有找到候選
            return {
                'status': 'not_found',
                'message': f'無法找到 "{address}" 的位置資訊',
                'original_query': address
            }
    else:
        # 地址解析成功，返回確定位置
        return {
            'status': 'success',
            'message': '位置解析成功',
            'location': {
                'address': address,
                'coordinates': list(coords),
                'name': address
            }
        }
