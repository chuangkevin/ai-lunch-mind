# Google Maps 餐廳搜尋模組 - 依賴安裝指南

## 需要安裝的套件

```bash
pip install selenium beautifulsoup4 geopy requests urllib3 webdriver-manager
```

## Chrome WebDriver 安裝

### 方法 1: 自動安裝（推薦）
```python
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# 自動下載並設定 ChromeDriver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)
```

### 方法 2: 手動安裝
1. 下載 ChromeDriver: https://chromedriver.chromium.org/
2. 將 chromedriver.exe 放到 PATH 目錄或專案目錄
3. 確保 ChromeDriver 版本與您的 Chrome 瀏覽器版本相符

## 使用範例

```python
from modules.google_maps import search_restaurants

# 測試案例 1: Google Maps 短網址 + 關鍵字
results = search_restaurants(
    keyword="羊肉",
    user_address="https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6",
    max_results=5
)

# 測試案例 2: 詳細地址 + 關鍵字
results = search_restaurants(
    keyword="火鍋",
    user_address="243新北市泰山區明志路二段210號",
    max_results=5
)

# 測試案例 3: 地標 + 關鍵字
results = search_restaurants(
    keyword="燒烤",
    user_address="彰化大佛",
    max_results=5
)

# 測試案例 4: 地區（無詳細地址）+ 關鍵字
results = search_restaurants(
    keyword="義大利麵",
    user_address="台北中山區",
    max_results=5
)

for restaurant in results:
    print(f"餐廳: {restaurant['name']}")
    print(f"地址: {restaurant.get('address')}")
    print(f"距離: {restaurant.get('distance_km')} 公里")
    print(f"評分: {restaurant.get('rating')}")
    print(f"Google Maps: {restaurant.get('maps_url')}")
    print("-" * 40)
```

## 功能特色

1. **多格式地址支援**：
   - Google Maps 短網址自動展開
   - 詳細地址座標解析
   - 地標名稱搜尋
   - 地區範圍搜尋

2. **距離計算**：
   - 自動計算餐廳與目標位置的距離
   - 支援座標和地址混合計算

3. **餐廳資訊提取**：
   - 餐廳名稱
   - 詳細地址
   - Google Maps 連結
   - 評分和價格等級
   - 與目標位置的距離

4. **智慧搜尋**：
   - 自動過濾非餐廳結果
   - 關鍵字相關性檢查
   - 多重搜尋策略備援

## 注意事項

- 首次使用可能需要下載 ChromeDriver
- 建議在穩定的網路環境下使用
- Google 可能會對頻繁請求進行限制
- 搜尋結果的準確性取決於 Google 的搜尋演算法
