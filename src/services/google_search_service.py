"""
Google 搜尋服務模組
使用 googlesearch-python 套件取代 Google Maps API
"""
from googlesearch import search
import httpx
import asyncio
import re
from bs4 import BeautifulSoup
from typing import List, Optional, Dict, Any
from src.config import settings
from src.models import Restaurant, Review, UserLocation, PriceLevel

class GoogleSearchService:
    """Google 搜尋服務 - 取代 Google Maps API"""
    
    def __init__(self):
        self.session = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
        )
        
        # 價格等級對應
        self.price_keywords = {
            PriceLevel.BUDGET: ['便宜', '平價', '銅板價', '學生價', '經濟'],
            PriceLevel.MODERATE: ['中價位', '適中', '合理'],
            PriceLevel.EXPENSIVE: ['高級', '精緻', '昂貴'],
            PriceLevel.LUXURY: ['奢華', '頂級', '米其林', '高檔']
        }
    
    async def search_nearby_restaurants(
        self, 
        location: UserLocation, 
        radius: int = None
    ) -> List[Restaurant]:
        """搜尋附近餐廳"""
        radius = radius or settings.search_radius
        
        try:
            # 構建搜尋查詢
            location_name = self._extract_location_name(location.address)
            search_query = f"{location_name} 餐廳 美食 推薦"
            
            print(f"🔍 搜尋查詢: {search_query}")
            
            # 執行 Google 搜尋
            search_results = []
            try:
                for url in search(search_query, num_results=20, lang='zh-TW'):
                    search_results.append(url)
                    if len(search_results) >= 15:  # 限制搜尋結果數量
                        break
            except Exception as e:
                print(f"⚠️ Google 搜尋失敗: {e}")
                return []
            
            print(f"📊 找到 {len(search_results)} 個搜尋結果")
            
            # 解析搜尋結果
            restaurants = []
            for i, url in enumerate(search_results):
                try:
                    restaurant = await self._extract_restaurant_info(url, location, i)
                    if restaurant:
                        restaurants.append(restaurant)
                    
                    # 避免過於頻繁的請求
                    if i % 3 == 0:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    print(f"⚠️ 解析餐廳資訊失敗 {url}: {e}")
                    continue
            
            print(f"✅ 成功解析 {len(restaurants)} 間餐廳")
            return restaurants[:settings.max_restaurants]
            
        except Exception as e:
            print(f"❌ 餐廳搜尋失敗: {e}")
            return []
    
    async def get_restaurant_details(self, place_id: str) -> Optional[Restaurant]:
        """取得餐廳詳細資訊 (基於 URL)"""
        try:
            if not place_id.startswith('http'):
                return None
                
            restaurant = await self._extract_restaurant_info(place_id, None, 0, detailed=True)
            return restaurant
            
        except Exception as e:
            print(f"❌ 餐廳詳情取得失敗: {e}")
            return None
    
    async def get_restaurant_reviews(self, place_id: str) -> List[Review]:
        """取得餐廳評論 (模擬)"""
        try:
            # 由於使用搜尋結果，無法直接取得評論
            # 可以嘗試從網頁內容中擷取評論相關資訊
            
            if not place_id.startswith('http'):
                return []
            
            response = await self.session.get(place_id)
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 尋找可能的評論內容
            reviews = []
            
            # 嘗試從網頁中找評論相關的文字
            review_texts = []
            for text in soup.stripped_strings:
                if any(keyword in text for keyword in ['評價', '推薦', '好吃', '美味', '服務']):
                    if len(text) > 10 and len(text) < 200:
                        review_texts.append(text)
            
            # 建立模擬評論
            for i, text in enumerate(review_texts[:3]):
                review = Review(
                    author_name=f"網友{i+1}",
                    rating=4 + (i % 2),  # 4-5分
                    text=text,
                    time=0
                )
                reviews.append(review)
            
            return reviews
            
        except Exception as e:
            print(f"❌ 評論取得失敗: {e}")
            return []
    
    def _extract_location_name(self, address: str) -> str:
        """從地址中擷取地點名稱"""
        if not address:
            return "台北"
        
        # 移除不需要的詞彙
        location = address.replace('台灣', '').replace('市', '').replace('區', '')
        
        # 擷取主要地點名稱
        if '捷運' in location:
            # 如：台北市大安區信義安和站 -> 信義安和
            station = location.split('捷運')[-1].replace('站', '')
            return station
        elif any(area in location for area in ['大安', '信義', '中山', '松山', '萬華', '中正']):
            # 擷取區域名稱
            for area in ['大安', '信義', '中山', '松山', '萬華', '中正']:
                if area in location:
                    return area
        
        # 預設返回台北
        return location[:4] if len(location) > 4 else "台北"
    
    async def _extract_restaurant_info(
        self, 
        url: str, 
        user_location: Optional[UserLocation], 
        index: int,
        detailed: bool = False
    ) -> Optional[Restaurant]:
        """從搜尋結果 URL 中擷取餐廳資訊"""
        try:
            # 過濾非餐廳相關的網站
            if not self._is_restaurant_url(url):
                return None
            
            response = await self.session.get(url)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 擷取餐廳名稱
            name = self._extract_restaurant_name(soup, url)
            if not name:
                return None
            
            # 擷取地址
            address = self._extract_address(soup)
            
            # 擷取評分
            rating = self._extract_rating(soup)
            
            # 擷取價位
            price_level = self._extract_price_level(soup)
            
            # 擷取料理類型
            cuisine_type = self._extract_cuisine_type(soup, name)
            
            # 擷取電話
            phone = self._extract_phone(soup)
            
            # 生成座標 (基於用戶位置的估算)
            latitude, longitude = self._estimate_coordinates(user_location, index)
            
            restaurant = Restaurant(
                place_id=url,  # 使用 URL 作為 ID
                name=name,
                address=address or "地址未提供",
                latitude=latitude,
                longitude=longitude,
                rating=rating,
                price_level=price_level,
                cuisine_type=cuisine_type,
                phone=phone,
                website=url
            )
            
            return restaurant
            
        except Exception as e:
            print(f"⚠️ 餐廳資訊擷取失敗: {e}")
            return None
    
    def _is_restaurant_url(self, url: str) -> bool:
        """判斷 URL 是否為餐廳相關"""
        restaurant_sites = [
            'ifoodie.tw',
            'pixnet.net',
            'blogspot.com',
            'facebook.com',
            'instagram.com',
            'foodpanda.com.tw',
            'ubereats.com',
            'google.com/maps',
            'tripadvisor',
            'yelp.com',
            'openrice.com'
        ]
        
        # 排除一些明顯非餐廳的網站
        exclude_sites = [
            'youtube.com',
            'wikipedia.org',
            'gov.tw',
            'news.',
            'yahoo.com'
        ]
        
        for exclude in exclude_sites:
            if exclude in url:
                return False
        
        for site in restaurant_sites:
            if site in url:
                return True
        
        # 如果 URL 包含餐廳相關關鍵字
        restaurant_keywords = ['restaurant', '餐廳', '美食', 'food', 'eat']
        return any(keyword in url.lower() for keyword in restaurant_keywords)
    
    def _extract_restaurant_name(self, soup: BeautifulSoup, url: str) -> Optional[str]:
        """擷取餐廳名稱"""
        # 嘗試從 title 標籤
        title = soup.find('title')
        if title:
            title_text = title.get_text().strip()
            # 清理標題
            name = re.sub(r'[\|\-\–\—].*$', '', title_text).strip()
            name = re.sub(r'(食記|評價|推薦|菜單|地址|電話).*$', '', name).strip()
            if len(name) > 2 and len(name) < 50:
                return name
        
        # 嘗試從 h1 標籤
        h1 = soup.find('h1')
        if h1:
            h1_text = h1.get_text().strip()
            if len(h1_text) > 2 and len(h1_text) < 50:
                return h1_text
        
        # 從 URL 中猜測
        if 'maps' in url:
            # Google Maps URL 處理
            return "餐廳 (Google Maps)"
        
        return None
    
    def _extract_address(self, soup: BeautifulSoup) -> Optional[str]:
        """擷取地址"""
        # 尋找包含地址的文字
        address_patterns = [
            r'地址[：:]\s*(.+?)(?:\n|$|電話|營業)',
            r'台北市.+?區.+?(?:\n|$)',
            r'新北市.+?區.+?(?:\n|$)',
            r'桃園市.+?區.+?(?:\n|$)'
        ]
        
        text = soup.get_text()
        for pattern in address_patterns:
            match = re.search(pattern, text)
            if match:
                address = match.group(1) if pattern.startswith('地址') else match.group(0)
                return address.strip()
        
        return None
    
    def _extract_rating(self, soup: BeautifulSoup) -> Optional[float]:
        """擷取評分"""
        # 尋找評分相關的數字
        rating_patterns = [
            r'(\d+\.?\d*)\s*[/／]\s*5',
            r'評分[：:]\s*(\d+\.?\d*)',
            r'★+\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*顆星'
        ]
        
        text = soup.get_text()
        for pattern in rating_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    rating = float(match.group(1))
                    if 0 <= rating <= 5:
                        return rating
                except ValueError:
                    continue
        
        # 預設評分
        return 4.0
    
    def _extract_price_level(self, soup: BeautifulSoup) -> Optional[PriceLevel]:
        """擷取價位等級"""
        text = soup.get_text().lower()
        
        # 根據關鍵字判斷價位
        for price_level, keywords in self.price_keywords.items():
            if any(keyword in text for keyword in keywords):
                return price_level
        
        # 根據價格數字判斷
        price_matches = re.findall(r'[NT$]?\s*(\d+)\s*元?', text)
        if price_matches:
            prices = [int(p) for p in price_matches if p.isdigit()]
            if prices:
                avg_price = sum(prices) / len(prices)
                if avg_price < 200:
                    return PriceLevel.BUDGET
                elif avg_price < 500:
                    return PriceLevel.MODERATE
                elif avg_price < 1000:
                    return PriceLevel.EXPENSIVE
                else:
                    return PriceLevel.LUXURY
        
        return PriceLevel.MODERATE  # 預設中等價位
    
    def _extract_cuisine_type(self, soup: BeautifulSoup, name: str) -> List[str]:
        """擷取料理類型"""
        text = soup.get_text() + ' ' + (name or '')
        
        cuisine_keywords = {
            '中式': ['中式', '中餐', '台菜', '熱炒', '小吃', '麵店', '餃子'],
            '日式': ['日式', '日本', '壽司', '拉麵', '丼飯', '居酒屋', '燒肉'],
            '韓式': ['韓式', '韓國', '韓食', '烤肉', '泡菜', '石鍋'],
            '義式': ['義式', '義大利', '披薩', '義大利麵', 'pizza', 'pasta'],
            '美式': ['美式', '漢堡', '炸雞', '牛排', 'burger', 'steak'],
            '泰式': ['泰式', '泰國', '泰菜', '酸辣', '椰漿'],
            '越式': ['越式', '越南', '河粉', 'pho'],
            '速食': ['速食', '麥當勞', '肯德基', 'KFC', '漢堡王'],
            '咖啡廳': ['咖啡', 'coffee', 'cafe', '下午茶', '甜點'],
            '火鍋': ['火鍋', '麻辣鍋', '涮涮鍋'],
            '燒烤': ['燒烤', 'BBQ', '烤肉']
        }
        
        cuisines = []
        for cuisine, keywords in cuisine_keywords.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                cuisines.append(cuisine)
        
        return cuisines if cuisines else ['餐廳']
    
    def _extract_phone(self, soup: BeautifulSoup) -> Optional[str]:
        """擷取電話號碼"""
        # 尋找電話號碼格式
        phone_patterns = [
            r'電話[：:]\s*([\d\-\(\)\s]+)',
            r'[Tt]el[：:]\s*([\d\-\(\)\s]+)',
            r'(\d{2,4}[-\s]?\d{3,4}[-\s]?\d{3,4})',
            r'(0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{3,4})'
        ]
        
        text = soup.get_text()
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(1) if 'phone' in pattern or '電話' in pattern else match.group(0)
                phone = re.sub(r'\s+', '-', phone.strip())
                if len(phone) >= 8:
                    return phone
        
        return None
    
    def _estimate_coordinates(
        self, 
        user_location: Optional[UserLocation], 
        index: int
    ) -> tuple[float, float]:
        """估算餐廳座標"""
        if not user_location:
            # 預設台北市中心
            base_lat, base_lng = 25.0330, 121.5654
        else:
            base_lat, base_lng = user_location.latitude, user_location.longitude
        
        # 在用戶位置周圍隨機分佈
        import random
        
        # 在半徑 500 公尺內隨機分佈
        offset_lat = (random.random() - 0.5) * 0.01  # 約 1 公里
        offset_lng = (random.random() - 0.5) * 0.01
        
        # 根據索引稍作調整，避免完全重疊
        offset_lat += (index % 5 - 2) * 0.002
        offset_lng += (index // 5 % 5 - 2) * 0.002
        
        return base_lat + offset_lat, base_lng + offset_lng
    
    async def close(self):
        """關閉 HTTP 會話"""
        await self.session.aclose()

# 全域服務實例
google_search_service = GoogleSearchService()
