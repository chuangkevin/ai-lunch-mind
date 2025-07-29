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
browser_pool = BrowserPool(pool_size=2)
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
        
        if lat is None or lng is None:
            logger.warning("無法從URL提取有效座標")
            return None
        
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

def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    將地址轉換為座標 - 改進版本，支援多重地理編碼服務
    :param address: 地址字串
    :return: (latitude, longitude) 或 None
    """
    if not address or len(address.strip()) < 3:
        return None
    
    # 標準化地址
    normalized_address = normalize_taiwan_address(address)
    logger.info(f"標準化地址: {address} -> {normalized_address}")
    
    # 嘗試多種地址格式
    address_variants = [
        normalized_address + ", Taiwan",
        normalized_address + ", 台灣",
        normalized_address,
        address + ", Taiwan",  # 原始地址
        address.replace('台', '臺') + ", Taiwan"  # 台/臺轉換 - 只在不包含 "台北" "台中" "台南" 等城市名時轉換
    ]
    
    # 方法1: 使用 Nominatim (OpenStreetMap)
    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
        for addr_variant in address_variants:
            try:
                location = geolocator.geocode(addr_variant)
                if location and location.latitude and location.longitude:
                    # 檢查座標是否在台灣範圍內
                    if 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                        logger.info(f"Nominatim 成功解析地址: {addr_variant} -> ({location.latitude}, {location.longitude})")
                        return (location.latitude, location.longitude)
            except Exception as e:
                logger.warning(f"Nominatim 解析失敗: {addr_variant} - {e}")
                continue
    except Exception as e:
        logger.error(f"Nominatim 服務失敗: {e}")
    
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
    
    # 方法3: 嘗試 Google Maps API 格式解析 (備用)
    try:
        # 如果地址看起來像是從 Google Maps 複製的格式
        if '號' in address or ('路' in address and ('段' in address or '巷' in address)):
            # 嘗試更簡化的查詢
            simplified_parts = []
            
            # 提取市/縣
            city_match = re.search(r'([\u4e00-\u9fff]+[市縣])', address)
            if city_match:
                simplified_parts.append(city_match.group(1))
            
            # 提取區/鄉/鎮
            district_match = re.search(r'([\u4e00-\u9fff]+[區鄉鎮市])', address)
            if district_match:
                simplified_parts.append(district_match.group(1))
            
            # 提取主要道路
            road_match = re.search(r'([\u4e00-\u9fff]+[路街大道])', address)
            if road_match:
                simplified_parts.append(road_match.group(1))
            
            if simplified_parts:
                simplified_address = ''.join(simplified_parts) + ", Taiwan"
                geolocator = Nominatim(user_agent="lunch-recommendation-system", timeout=10)
                location = geolocator.geocode(simplified_address)
                if location and 21.0 <= location.latitude <= 26.0 and 119.0 <= location.longitude <= 122.5:
                    logger.info(f"簡化地址解析成功: {simplified_address} -> ({location.latitude}, {location.longitude})")
                    return (location.latitude, location.longitude)
    
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
    檢查地址是否足夠完整
    :param address: 地址字串
    :return: 是否完整
    """
    if not address or len(address.strip()) < 8:
        return False
    
    address = address.strip()
    
    # 檢查是否包含完整地址要素
    has_city = any(keyword in address for keyword in ['市', '縣'])
    has_district = any(keyword in address for keyword in ['區', '鄉', '鎮'])
    has_road = any(keyword in address for keyword in ['路', '街', '大道', '巷', '弄'])
    has_number = bool(re.search(r'\d+號', address))
    
    # 至少需要 3 個要素且必須包含門牌號才算完整
    completeness_score = sum([has_city, has_district, has_road, has_number])
    
    # 如果有郵遞區號，可以稍微降低要求，但仍需要門牌號
    has_postal = bool(re.match(r'^\d{3}', address))
    if has_postal:
        return completeness_score >= 3 and has_number
    
    # 一般情況下，需要4個要素都有或至少3個且包含門牌號
    return (completeness_score >= 4) or (completeness_score >= 3 and has_number)

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

def calculate_distance(user_coords: Tuple[float, float], restaurant_coords: Tuple[float, float]) -> float:
    """
    計算兩點間距離
    :param user_coords: 使用者座標 (lat, lon)
    :param restaurant_coords: 餐廳座標 (lat, lon)
    :return: 距離（公里）
    """
    try:
        distance = geodesic(user_coords, restaurant_coords).kilometers
        return round(distance, 2)
    except Exception:
        return None

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
    
    # 精簡搜尋策略 - 只用最有效的一種
    search_strategies = [
        {
            'name': 'Maps直接搜尋',
            'url': f"https://www.google.com/maps/search/{encoded_query}/@25.0478,121.5318,12z",
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
                    restaurant_info = extract_restaurant_info_minimal(element, location_info)
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

def extract_restaurant_info_minimal(element, location_info: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """
    最精簡的餐廳資訊提取 - 只獲取名稱和基本資訊
    
    :param element: 搜尋結果元素
    :param location_info: 位置資訊
    :return: 餐廳資訊字典
    """
    
    restaurant_info = {
        'name': '',
        'address': '',
        'rating': None,
        'distance_km': 3.0  # 預設距離
    }
    
    try:
        # 只提取名稱 - 使用最快的選擇器
        name_selectors = ["span.OSrXXb", "h3.LC20lb", "div.qBF1Pd"]
        
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
        
        # 快速提取評分 (可選)
        try:
            rating_element = element.find_element(By.CSS_SELECTOR, "span.yi40Hd")
            rating_text = rating_element.text.strip()
            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
            if rating_match:
                restaurant_info['rating'] = float(rating_match.group(1))
        except:
            pass
        
        return restaurant_info
        
    except Exception as e:
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
        
        # 嘗試不同的搜尋策略
        search_strategies = [
            f"https://www.google.com/maps/search/{encoded_query}/@25.0478,121.5318,12z",  # Maps 直接搜尋
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
                restaurant_info = extract_restaurant_info_minimal(element, location_info)
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

def extract_restaurant_info_from_element_improved(element, location_info: Optional[Dict] = None, driver=None) -> Optional[Dict[str, Any]]:
    """
    改進版餐廳資訊提取函數 - 現在直接調用精簡版本
    :param element: Selenium WebElement
    :param location_info: 使用者位置資訊
    :param driver: WebDriver 實例
    :return: 餐廳資訊字典
    """
    # 直接調用精簡版本，大幅提升速度
    return extract_restaurant_info_minimal(element, location_info)

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
            coords = geocode_address(user_address)
            if coords:
                location_info = {
                    'coords': coords,
                    'address': user_address
                }
                logger.info(f"地址座標: {coords}")
            else:
                # 即使無法獲得座標，也保留地址用於搜尋
                location_info = {
                    'coords': None,
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
