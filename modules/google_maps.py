"""
Google Maps 餐廳搜尋模組 - Selenium 版本
使用 Selenium 進行真實瀏覽器自動化搜尋，提供更準確的餐廳資訊
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
                restaurant_info = extract_restaurant_info_from_element_improved(element, location_info, driver)
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
    改進版餐廳資訊提取函數
    :param element: Selenium WebElement
    :param location_info: 使用者位置資訊
    :param driver: WebDriver 實例
    :return: 餐廳資訊字典
    """
    try:
        restaurant_info = {
            'name': None,
            'address': None,
            'maps_url': None,
            'rating': None,
            'price_level': None,
            'distance_km': None
        }
        
        # 提取餐廳名稱 - 更新選擇器針對新的 Google Maps 結構
        name_selectors = [
            "div.qBF1Pd.fontHeadlineSmall",  # 新版 Google Maps 餐廳名稱
            "div.qBF1Pd",  # 簡化版選擇器
            ".fontHeadlineSmall",  # 標題樣式
            "h3.LC20lb",  # 傳統搜尋結果
            "h3",  # 一般標題
            "div[role='heading']",  # 語義化標題
            ".BNeawe.vvjwJb.AP7Wnd",  # 舊版選擇器
            "a h3",  # 連結內的標題
            "span.OSrXXb"  # 其他文字選擇器
        ]
        
        for selector in name_selectors:
            try:
                name_element = element.find_element(By.CSS_SELECTOR, selector)
                name_text = name_element.text.strip()
                if name_text and len(name_text) > 0:
                    restaurant_info['name'] = name_text
                    logger.info(f"使用選擇器 {selector} 提取到餐廳名稱: {name_text}")
                    break
            except NoSuchElementException:
                continue
        
        # 如果還是沒有名稱，嘗試從連結文字提取
        if not restaurant_info['name']:
            try:
                link_elements = element.find_elements(By.CSS_SELECTOR, "a")
                for link in link_elements:
                    link_text = link.text.strip()
                    if link_text and len(link_text) > 3:  # 過濾太短的文字
                        restaurant_info['name'] = link_text
                        break
            except:
                pass
        
        # 提取 Google Maps 連結 - 修正版本，正確識別 place 連結
        logger.info("開始嘗試提取 Google Maps 連結...")
        
        # 首先嘗試從當前元素內查找
        all_links = element.find_elements(By.TAG_NAME, "a")
        logger.info(f"在當前元素內找到 {len(all_links)} 個 <a> 標籤")
        
        if len(all_links) == 0:
            # 如果當前元素內沒有連結，嘗試從更高層級查找
            try:
                # 嘗試找到父容器
                parent_container = element.find_element(By.XPATH, "./..")
                all_links = parent_container.find_elements(By.TAG_NAME, "a")
                logger.info(f"在父容器中找到 {len(all_links)} 個 <a> 標籤")
            except:
                logger.debug("無法從父容器查找連結")
        
        # 如果還是沒有找到，嘗試從整個頁面範圍內查找包含餐廳名稱的連結
        if len(all_links) == 0 and restaurant_info.get('name') and driver:
            try:
                restaurant_name = restaurant_info['name'][:15]  # 取前15個字符
                logger.info(f"嘗試在整個頁面搜尋包含餐廳名稱 '{restaurant_name}' 的連結...")
                
                # 在整個頁面範圍內查找連結，使用更精確的搜尋
                page_links = driver.find_elements(By.XPATH, f"//a[contains(@aria-label, '{restaurant_name}') or contains(text(), '{restaurant_name}')]")
                logger.info(f"在整個頁面找到 {len(page_links)} 個相關連結")
                
                for link in page_links:
                    href = link.get_attribute('href')
                    if href and '/maps/place/' in href:
                        # 驗證這是真正的餐廳連結，不是純坐標連結
                        if not (href.count('/@') > 0 and href.count('/place/') > 0 and '/' == href.split('/place/')[1].split('/')[0]):
                            # 檢查連結是否包含餐廳信息
                            if any(indicator in href for indicator in ['!', '0x', 'data=', restaurant_name[:10]]):
                                all_links = [link]
                                logger.info(f"在頁面範圍找到有效的餐廳 place 連結")
                                break
                        else:
                            logger.debug(f"跳過純坐標 place 連結")
            except Exception as e:
                logger.debug(f"頁面範圍搜尋失敗: {e}")
        
        # 檢查每個連結
        for i, link_element in enumerate(all_links):
            try:
                href = link_element.get_attribute('href')
                if href:
                    logger.debug(f"連結 {i+1}: {href[:100]}...")
                    
                    # 檢查是否為真實的 Google Maps 餐廳連結
                    # 排除只有坐標的連結（如 /place//@lat,lng）
                    if '/maps/place/' in href:
                        # 檢查是否為有效的餐廳連結
                        # 有效的餐廳連結應該包含餐廳名稱，而不只是坐標
                        if not href.count('/@') > href.count('/place/') or '!' in href:
                            # 進一步驗證連結品質
                            if any(char in href for char in ['!', '0x', 'data=']):
                                restaurant_info['maps_url'] = href
                                logger.info(f"找到有效的 Google Maps Place 連結: {href[:80]}...")
                                break
                            else:
                                logger.debug(f"跳過坐標位置連結: {href[:80]}...")
                        else:
                            logger.debug(f"跳過純坐標連結: {href[:80]}...")
                    elif 'maps.google.com' in href and 'place_id=' in href:
                        restaurant_info['maps_url'] = href
                        logger.info(f"找到包含 Place ID 的連結: {href[:80]}...")
                        break
                    elif 'maps.google.com' in href and any(keyword in href for keyword in ['/@', '/place']):
                        # 額外檢查，確保不是純坐標連結
                        if '!' in href or 'data=' in href:
                            restaurant_info['maps_url'] = href
                            logger.info(f"找到 Google Maps 位置連結: {href[:80]}...")
                            break
                        else:
                            logger.debug(f"跳過可能的坐標連結: {href[:80]}...")
                    elif 'maps.google.com' in href:
                        restaurant_info['maps_url'] = href
                        logger.info(f"找到 Google Maps 連結: {href[:80]}...")
                        break
            except Exception as e:
                logger.debug(f"檢查連結時出錯: {e}")
        
        # 如果上面的方法都沒有找到連結，嘗試其他策略
        if not restaurant_info.get('maps_url'):
            logger.info("嘗試其他連結查找策略...")
            link_selectors = [
                "a[href*='maps.google.com/maps/place']",  # 最精確的 place 連結
                "a[href*='place_id=']",  # 包含 place_id 的連結
                "a[href*='maps.google']",  # 直接包含 maps.google 的連結
                "a[href*='/maps/place']",  # Google Maps place 連結
                "a[data-cid]",  # 有 data-cid 屬性的連結
                "a.hfpxzc",  # Google Maps 特定的連結樣式
                "a[jsaction*='pane']",  # 有 pane 相關 jsaction 的連結
            ]
            
            for selector in link_selectors:
                try:
                    link_elements = element.find_elements(By.CSS_SELECTOR, selector)
                    logger.debug(f"使用選擇器 '{selector}' 找到 {len(link_elements)} 個連結元素")
                    for link_element in link_elements:
                        href = link_element.get_attribute('href')
                        if href:
                            logger.debug(f"檢查連結: {href[:100]}...")
                            # 檢查是否為真實的 Google Maps 連結（優先級最高）
                            # 只要包含 /maps/place 就是真實的 place 連結
                            if '/maps/place' in href:
                                restaurant_info['maps_url'] = href
                                logger.info(f"找到真實 Google Maps Place 連結: {href[:80]}...")
                                break
                            elif 'maps.google.com' in href and 'place_id=' in href:
                                restaurant_info['maps_url'] = href
                                logger.info(f"找到包含 Place ID 的連結: {href[:80]}...")
                                break
                            elif 'maps.google.com' in href and any(keyword in href for keyword in ['/@', '/place']):
                                restaurant_info['maps_url'] = href
                                logger.info(f"找到 Google Maps 位置連結: {href[:80]}...")
                                break
                            elif 'maps.google.com' in href:
                                # 這也是有效的 Google Maps 連結
                                restaurant_info['maps_url'] = href
                                logger.info(f"找到 Google Maps 連結: {href[:80]}...")
                                break
                        
                        # 檢查 data-href 屬性（有時連結存在這裡）
                        data_href = link_element.get_attribute('data-href')
                        if data_href and 'maps.google.com' in data_href:
                            restaurant_info['maps_url'] = data_href
                            logger.info(f"從 data-href 提取到 Maps 連結: {data_href[:80]}...")
                            break
                
                    if restaurant_info.get('maps_url'):
                        break
                        
                except NoSuchElementException:
                    continue
        
        # 如果上面的方法都沒有找到連結，嘗試點擊餐廳獲取真實連結
        if not restaurant_info.get('maps_url') and driver:
            logger.info("嘗試點擊餐廳元素以獲取真實 place 連結...")
            try:
                # 保存當前 URL
                original_url = driver.current_url
                
                # 嘗試點擊餐廳元素
                driver.execute_script("arguments[0].click();", element)
                
                # 等待頁面可能的變化
                import time
                time.sleep(2)
                
                # 檢查 URL 是否變化到 place 連結
                current_url = driver.current_url
                if current_url != original_url and '/maps/place/' in current_url:
                    # 驗證這是有效的餐廳 place 連結
                    if not (current_url.count('/@') > 0 and '/' == current_url.split('/place/')[1].split('/')[0]):
                        restaurant_info['maps_url'] = current_url
                        logger.info(f"通過點擊獲取到真實 place 連結: {current_url[:80]}...")
                    else:
                        logger.debug(f"點擊後獲取的是坐標連結，非餐廳 place 連結")
                else:
                    logger.debug(f"點擊後 URL 未變化為 place 連結")
                    
                # 如果 URL 沒有直接變化，檢查頁面上是否有新的連結
                if not restaurant_info.get('maps_url'):
                    try:
                        # 在當前頁面查找所有包含餐廳名稱的 place 連結
                        restaurant_name = restaurant_info.get('name', '')[:15]
                        if restaurant_name:
                            place_links = driver.find_elements(By.XPATH, 
                                f"//a[contains(@href, '/maps/place/') and (contains(@aria-label, '{restaurant_name}') or contains(text(), '{restaurant_name}'))]")
                            
                            for link in place_links:
                                href = link.get_attribute('href')
                                if href and restaurant_name[:10] in href:
                                    restaurant_info['maps_url'] = href
                                    logger.info(f"在點擊後的頁面找到餐廳 place 連結: {href[:80]}...")
                                    break
                    except Exception as e:
                        logger.debug(f"在點擊後頁面搜尋連結失敗: {e}")
                
            except Exception as e:
                logger.debug(f"點擊餐廳元素失敗: {e}")
        
        # 如果沒有找到直接連結，嘗試從父級元素或 aria-label 中尋找
        if not restaurant_info.get('maps_url'):
            try:
                # 尋找具有 aria-label 包含餐廳名稱的連結
                if restaurant_info.get('name'):
                    short_name = restaurant_info['name'][:15]  # 取前15個字符
                    
                    # 嘗試各種可能的連結查找方式
                    xpath_queries = [
                        f".//a[contains(@aria-label, '{short_name}')]",
                        f".//a[contains(@href, 'maps.google')]",
                        f".//a[contains(@href, 'place')]"
                    ]
                    
                    for xpath in xpath_queries:
                        try:
                            links = element.find_elements(By.XPATH, xpath)
                            for link in links:
                                href = link.get_attribute('href')
                                if href and 'maps.google.com' in href:
                                    restaurant_info['maps_url'] = href
                                    logger.info(f"通過 XPath 查找到 Maps 連結: {href[:80]}...")
                                    break
                            if restaurant_info.get('maps_url'):
                                break
                        except:
                            continue
                            
            except Exception as e:
                logger.debug(f"額外連結搜尋失敗: {e}")
        
        # 如果仍然沒有連結，嘗試構建一個基於餐廳名稱和地址的搜尋連結
        if not restaurant_info.get('maps_url') and restaurant_info.get('name'):
            try:
                # 清理餐廳名稱，移除過長的描述和特殊字符
                clean_name = restaurant_info['name']
                
                # 移除過長的描述性文字（超過50字符的部分通常是廣告文字）
                if len(clean_name) > 50:
                    # 尋找第一個 '-' 或 '|' 或 '(' 來截斷
                    for delimiter in ['-', '|', '(', '（']:
                        if delimiter in clean_name:
                            clean_name = clean_name.split(delimiter)[0].strip()
                            break
                    
                    # 如果還是太長，只取前30個字符
                    if len(clean_name) > 30:
                        clean_name = clean_name[:30].strip()
                
                # 移除特殊字符和多餘空格
                clean_name = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', clean_name)  # 保留中文、英文、數字、空格
                clean_name = re.sub(r'\s+', ' ', clean_name).strip()  # 合併多個空格
                
                # 構建搜尋查詢
                search_query = clean_name
                if restaurant_info.get('address'):
                    # 也清理地址，移除過長的部分
                    clean_address = restaurant_info['address']
                    if len(clean_address) > 50:
                        # 通常地址的主要部分在前面
                        clean_address = clean_address[:50]
                    search_query += f" {clean_address}"
                
                # 確保查詢不會太長
                if len(search_query) > 100:
                    search_query = search_query[:100]
                
                # 正確的 URL 編碼
                encoded_query = quote(search_query, safe='', encoding='utf-8')
                constructed_url = f"https://www.google.com/maps/search/{encoded_query}"
                restaurant_info['maps_url'] = constructed_url
                logger.info(f"構建搜尋連結 (清理後名稱: {clean_name}): {constructed_url[:80]}...")
            except Exception as e:
                logger.debug(f"構建連結失敗: {e}")
        
        # 提取地址 - 針對新版 Google Maps 結構改進策略
        address_patterns = [
            # 完整台灣地址格式（門牌號碼在前）
            r'[\u4e00-\u9fff]*[路街巷弄大道][^\s]*\d+[-\d]*號[^\s]*',
            # 完整台灣地址格式
            r'\d{3}[\u4e00-\u9fff]+[市縣][\u4e00-\u9fff]+[區鄉鎮市][\u4e00-\u9fff]*[路街巷弄大道][^\s]*號?[^\s]*',
            # 中文地址格式（含郵遞區號）
            r'\d{3}[\u4e00-\u9fff]+[市縣][^\s]+',
            # 標準地址格式
            r'[\u4e00-\u9fff]+[市縣][\u4e00-\u9fff]+[區鄉鎮市][\u4e00-\u9fff]*[路街巷弄大道][^\s]*號?[^\s]*',
            # 簡化地址格式
            r'[\u4e00-\u9fff]+[市縣][^\s]{2,}[區鄉鎮市][^\s]*[路街巷弄][^\s]*號?',
            # 包含段的地址
            r'[\u4e00-\u9fff]+[路街大道][^\s]*段[^\s]*號?[^\s]*',
            # 包含巷弄的地址
            r'[\u4e00-\u9fff]+[路街][^\s]*巷[^\s]*號?[^\s]*',
            # 路名 + 號碼的簡單格式
            r'[\u4e00-\u9fff]+[路街大道]\d+[-\d]*號?',
            # 商圈或地標
            r'[\u4e00-\u9fff]+[商圈夜市車站]',
            # 包含"市"和"區"的基本格式
            r'[\u4e00-\u9fff]+市[\u4e00-\u9fff]+區[\u4e00-\u9fff]+',
        ]
        
        try:
            # 從整個元素的文字中尋找地址
            full_text = element.text
            potential_addresses = []
            
            for pattern in address_patterns:
                matches = re.findall(pattern, full_text)
                if matches:
                    potential_addresses.extend(matches)
            
            # 驗證和選擇最佳地址
            if potential_addresses:
                best_address = validate_and_select_best_address(potential_addresses)
                if best_address:
                    restaurant_info['address'] = best_address
                    logger.info(f"從文字中提取到地址: {best_address}")
        except Exception as e:
            logger.warning(f"地址模式匹配失敗: {e}")
        
        # 如果還是沒有地址，嘗試特定的地址選擇器
        if not restaurant_info['address']:
            address_selectors = [
                "div.W4Efsd:last-child span.ZDu9vd",  # 新版 Google Maps 地址
                "div.W4Efsd span.ZDu9vd",  # 地址容器
                ".rllt__details div",  # 詳細資訊區域
                "span.LrzXr",  # 地址專用樣式
                ".BNeawe.UPmit.AP7Wnd",  # 另一種地址樣式
                "div span",  # 通用 span 元素
                ".dbg0pd div",  # 容器內的 div
                ".UaQhfb span",  # Maps 容器內的 span
                ".Nv2PK span",  # 新版容器內的 span
                "div.rllt__details span",  # 詳細資訊內的 span
                ".OSrXXb",  # 文字內容樣式
                "div[data-attrid='kc:/location/location:address']",  # 地址屬性
                "span[data-attrid='kc:/location/location:address']"  # 地址屬性 span
            ]
            
            for selector in address_selectors:
                try:
                    addr_elements = element.find_elements(By.CSS_SELECTOR, selector)
                    for addr_elem in addr_elements:
                        addr_text = addr_elem.text.strip()
                        if is_valid_taiwan_address(addr_text):
                            cleaned_addr = clean_address(addr_text)
                            # 進一步驗證清理後的地址
                            if len(cleaned_addr) > 5 and is_complete_address(cleaned_addr):
                                restaurant_info['address'] = cleaned_addr
                                break
                    if restaurant_info['address']:
                        break
                except Exception as e:
                    logger.debug(f"地址選擇器 {selector} 失敗: {e}")
                    continue
        
        # 如果仍然沒有完整地址，嘗試從 Maps URL 或其他來源補全
        if not restaurant_info['address'] or not is_complete_address(restaurant_info['address']):
            if restaurant_info.get('maps_url'):
                try:
                    # 嘗試從 Google Maps URL 提取更完整的地址
                    enhanced_address = extract_address_from_maps_url(restaurant_info['maps_url'])
                    if enhanced_address and is_complete_address(enhanced_address):
                        restaurant_info['address'] = enhanced_address
                        logger.info(f"從 Maps URL 補全地址: {enhanced_address}")
                except Exception as e:
                    logger.debug(f"從 Maps URL 提取地址失敗: {e}")
        
        # 提取評分
        rating_selectors = [
            "span.yi40Hd",
            ".BTtC6e",
            "span[aria-label*='顆星']",
            "span[aria-label*='stars']"
        ]
        
        for selector in rating_selectors:
            try:
                rating_element = element.find_element(By.CSS_SELECTOR, selector)
                rating_text = rating_element.text.strip()
                # 提取數字評分
                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                if rating_match:
                    rating_value = float(rating_match.group(1))
                    if 0 <= rating_value <= 5:  # 確保評分在合理範圍
                        restaurant_info['rating'] = rating_value
                        break
            except (NoSuchElementException, ValueError):
                continue
        
        # 提取平均價格
        price_patterns = [
            r'\$(\d{2,4})-(\d{2,4})',  # $100-300 格式（至少2位數）
            r'NT\$(\d{2,4})-(\d{2,4})',  # NT$100-300 格式
            r'(\d{2,4})-(\d{2,4})元',  # 100-300元 格式
            r'\$(\d{2,4})\+',  # $100+ 格式
            r'NT\$(\d{2,4})\+',  # NT$100+ 格式
            r'(\d{2,4})元以上',  # 100元以上 格式
            r'\$(\d{2,4})',  # 單一價格 $100（至少2位數）
            r'NT\$(\d{2,4})',  # 單一價格 NT$100
            r'(\d{2,4})元'  # 單一價格 100元
        ]
        
        try:
            full_text = element.text
            for pattern in price_patterns:
                price_match = re.search(pattern, full_text)
                if price_match:
                    groups = price_match.groups()
                    if len(groups) == 2:  # 價格區間
                        try:
                            low_price = int(groups[0])
                            high_price = int(groups[1])
                            # 確保價格合理且邏輯正確
                            if (10 <= low_price <= 10000 and 10 <= high_price <= 10000 and 
                                low_price < high_price):
                                restaurant_info['price_level'] = f"${low_price}-{high_price}"
                                logger.info(f"提取到價格區間: ${low_price}-{high_price}")
                                break
                        except ValueError:
                            continue
                    elif len(groups) == 1:  # 單一價格或起始價格
                        try:
                            price = int(groups[0])
                            # 確保價格合理（最低10元，避免錯誤解析）
                            if 10 <= price <= 10000:
                                if '+' in price_match.group(0) or '以上' in price_match.group(0):
                                    restaurant_info['price_level'] = f"${price}+"
                                    logger.info(f"提取到起始價格: ${price}+")
                                else:
                                    restaurant_info['price_level'] = f"${price}"
                                    logger.info(f"提取到單一價格: ${price}")
                                break
                        except ValueError:
                            continue
        except Exception as e:
            logger.debug(f"價格提取失敗: {e}")
        
        # 如果沒有通過文字提取到價格，嘗試特定的價格選擇器
        if not restaurant_info.get('price_level'):
            price_selectors = [
                "span.UY7F9",  # Google Maps 價格樣式
                ".r4GTf",  # 另一種價格樣式
                "span[aria-label*='價格']",  # 含價格的 aria-label
                "span[aria-label*='Price']",  # 英文價格 aria-label
                ".BNeawe.deIvCb.AP7Wnd"  # 其他價格樣式
            ]
            
            for selector in price_selectors:
                try:
                    price_element = element.find_element(By.CSS_SELECTOR, selector)
                    price_text = price_element.text.strip()
                    
                    # 使用相同的價格模式匹配
                    for pattern in price_patterns:
                        price_match = re.search(pattern, price_text)
                        if price_match:
                            groups = price_match.groups()
                            if len(groups) == 2:
                                try:
                                    low_price = int(groups[0])
                                    high_price = int(groups[1])
                                    if 1 <= low_price <= 10000 and 1 <= high_price <= 10000:
                                        restaurant_info['price_level'] = f"${low_price}-{high_price}"
                                        logger.info(f"使用選擇器 {selector} 提取到價格區間: ${low_price}-{high_price}")
                                        break
                                except ValueError:
                                    continue
                            elif len(groups) == 1:
                                try:
                                    price = int(groups[0])
                                    if 1 <= price <= 10000:
                                        if '+' in price_match.group(0) or '以上' in price_match.group(0):
                                            restaurant_info['price_level'] = f"${price}+"
                                        else:
                                            restaurant_info['price_level'] = f"${price}"
                                        logger.info(f"使用選擇器 {selector} 提取到價格: {restaurant_info['price_level']}")
                                        break
                                except ValueError:
                                    continue
                    if restaurant_info.get('price_level'):
                        break
                except (NoSuchElementException, ValueError):
                    continue
        
        # 計算距離 - 優先使用地址，然後嘗試其他方法
        if location_info and location_info.get('coords'):
            distance_calculated = False
            
            # 方法1：使用餐廳地址計算距離
            if restaurant_info.get('address'):
                try:
                    restaurant_coords = geocode_address(restaurant_info['address'])
                    if restaurant_coords:
                        distance = calculate_distance(location_info['coords'], restaurant_coords)
                        if distance is not None:
                            restaurant_info['distance_km'] = distance
                            distance_calculated = True
                            logger.info(f"距離計算成功（地址方法）: {distance} km")
                except Exception as e:
                    logger.debug(f"地址距離計算失敗: {e}")
            
            # 方法2：如果地址方法失敗，使用估算距離
            if not distance_calculated:
                try:
                    # 根據餐廳名稱估算合理距離（搜尋結果通常按距離排序）
                    estimated_distance = 3.0  # 預設3公里範圍
                    restaurant_info['distance_km'] = estimated_distance
                    logger.info(f"使用估算距離: {estimated_distance} km")
                except Exception as e:
                    logger.debug(f"估算距離失敗: {e}")
                    restaurant_info['distance_km'] = None
        
        # 只有在有名稱時才返回結果
        if restaurant_info['name']:
            return restaurant_info
        else:
            return None
        
    except Exception as e:
        logger.error(f"提取餐廳資訊失敗: {e}")
        return None

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
    
    # 使用 Selenium 搜尋
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
