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
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
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

def expand_short_url(short_url: str) -> str:
    """
    展開 Google Maps 短網址
    :param short_url: 短網址
    :return: 完整 URL
    """
    try:
        session = create_session()
        response = session.get(short_url, allow_redirects=True, timeout=10)
        return response.url
    except Exception as e:
        logger.error(f"展開短網址失敗: {e}")
        return short_url

def extract_location_from_url(url: str) -> Optional[Tuple[float, float, str]]:
    """
    從 Google Maps URL 提取位置資訊
    :param url: Google Maps URL
    :return: (latitude, longitude, place_name) 或 None
    """
    try:
        # 展開短網址
        if 'maps.app.goo.gl' in url or 'goo.gl' in url:
            url = expand_short_url(url)
        
        # 提取座標
        coord_match = re.search(r'/@(-?\d+\.\d+),(-?\d+\.\d+)', url)
        if coord_match:
            lat = float(coord_match.group(1))
            lng = float(coord_match.group(2))
            
            # 提取地點名稱
            place_name = None
            place_match = re.search(r'/place/([^/@]+)', url)
            if place_match:
                place_name = unquote(place_match.group(1)).replace('+', ' ')
            
            return (lat, lng, place_name)
        
        return None
        
    except Exception as e:
        logger.error(f"URL 位置提取失敗: {e}")
        return None

def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    將地址轉換為座標
    :param address: 地址字串
    :return: (latitude, longitude) 或 None
    
    TODO: 地址解析尚未完全完整
    - 需要支援更多台灣地址格式
    - 需要加入多重地理編碼服務備援
    - 需要改善模糊地址的處理邏輯
    """
    try:
        geolocator = Nominatim(user_agent="lunch-recommendation-system")
        location = geolocator.geocode(address + ", Taiwan")
        if location:
            return (location.latitude, location.longitude)
        return None
    except Exception as e:
        print(f"[Geocoding] 地址解析失敗: {e}")
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
        driver = create_chrome_driver(headless=True)  # 改為 headless 模式提高穩定性
        
        # 構建搜尋查詢
        if location_info and location_info.get('address'):
            search_query = f"{location_info['address']} {keyword} 餐廳"
        else:
            search_query = f"{keyword} 餐廳 台灣"
        
        # 建立 Google Local Search URL
        encoded_query = quote(search_query)
        search_url = f"https://www.google.com/search?tbm=lcl&q={encoded_query}&num={max_results}&hl=zh-TW"
        
        logger.info(f"搜尋 URL: {search_url}")
        
        # 訪問搜尋頁面
        driver.get(search_url)
        time.sleep(5)  # 增加等待時間確保頁面完全載入
        
        restaurants = []
        
        # 嘗試多種元素選擇器策略
        selectors = [
            "div.VkpGBb",  # 新版 Google Local 結果容器
            "div.dbg0pd",  # 另一種結果容器
            "div[data-ved]",  # 通用的有 data-ved 屬性的容器
            ".g",  # 傳統搜尋結果
            "div.UaQhfb"  # 地圖搜尋結果
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
        
        if not result_elements:
            logger.warning("未找到任何搜尋結果元素")
            return []
        
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
        
        # 提取餐廳名稱 - 多種策略
        name_selectors = [
            "h3.LC20lb",
            "h3",
            "div[role='heading']",
            ".BNeawe.vvjwJb.AP7Wnd",
            "a h3",
            "span.OSrXXb"
        ]
        
        for selector in name_selectors:
            try:
                name_element = element.find_element(By.CSS_SELECTOR, selector)
                name_text = name_element.text.strip()
                if name_text and len(name_text) > 0:
                    restaurant_info['name'] = name_text
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
        
        # 提取 Google Maps 連結
        link_selectors = [
            "a[href*='maps.google']",
            "a[href*='/maps/place']",
            "a[href*='place_id']",
            "a"
        ]
        
        for selector in link_selectors:
            try:
                link_element = element.find_element(By.CSS_SELECTOR, selector)
                href = link_element.get_attribute('href')
                if href and ('maps' in href or 'place' in href):
                    restaurant_info['maps_url'] = href
                    break
            except NoSuchElementException:
                continue
        
        # 提取地址 - 改進策略
        address_patterns = [
            r'[\u4e00-\u9fff]+[市縣][^\s]{2,}[區鄉鎮市][^\s]*[路街巷弄][^\s]*號?',  # 中文地址格式
            r'\d{3}[\u4e00-\u9fff]+[市縣][^\s]+',  # 郵遞區號+地址
        ]
        
        try:
            # 從整個元素的文字中尋找地址
            full_text = element.text
            for pattern in address_patterns:
                matches = re.findall(pattern, full_text)
                if matches:
                    restaurant_info['address'] = matches[0]
                    break
        except:
            pass
        
        # 如果還是沒有地址，嘗試特定的地址選擇器
        if not restaurant_info['address']:
            address_selectors = [
                ".rllt__details div",
                "span.LrzXr",
                ".BNeawe.UPmit.AP7Wnd",
                "div span"
            ]
            
            for selector in address_selectors:
                try:
                    addr_elements = element.find_elements(By.CSS_SELECTOR, selector)
                    for addr_elem in addr_elements:
                        addr_text = addr_elem.text.strip()
                        if any(keyword in addr_text for keyword in ['市', '區', '路', '街', '號']):
                            restaurant_info['address'] = addr_text
                            break
                    if restaurant_info['address']:
                        break
                except:
                    continue
        
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
        
        # 計算距離
        if location_info and location_info.get('coords') and restaurant_info.get('address'):
            try:
                restaurant_coords = geocode_address(restaurant_info['address'])
                if restaurant_coords:
                    distance = calculate_distance(location_info['coords'], restaurant_coords)
                    restaurant_info['distance_km'] = distance
            except Exception as e:
                logger.error(f"距離計算失敗: {e}")
        
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
    # 餐廳相關關鍵字
    restaurant_keywords = [
        '餐廳', '飯店', '食堂', '小吃', '美食', '料理', 
        '火鍋', '燒烤', '拉麵', '義大利麵', '牛排', '壽司',
        '羊肉', '牛肉', '豬肉', '雞肉', '海鮮', '素食',
        '早餐', '午餐', '晚餐', '宵夜', '咖啡', '茶',
        '中式', '西式', '日式', '韓式', '泰式', '義式'
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
    exclude_keywords = ['銀行', '醫院', '學校', '公司', '政府', '機關', '停車場', '加油站']
    if any(kw in restaurant_name for kw in exclude_keywords):
        return False
    
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
        if user_address.startswith('http') and ('maps.app.goo.gl' in user_address or 'maps.google' in user_address):
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
