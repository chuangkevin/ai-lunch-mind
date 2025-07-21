# 午餐吃什麼 🍱 — AI 餐廳推薦系統

> 智能餐廳搜尋系統：整合天氣查詢、Google Maps 餐廳搜尋與 Selenium 自動化技術，提供精準的用餐推薦。  
> ✅ **Selenium 爬蟲**｜✅ **Google Maps 整合**｜✅ **智能地址解析**｜✅ **聊天機器人介面**

---

## 🎯 專案現況

### ✅ 已完成功能

- **🌤️ 天氣查詢系統**：整合中央氣象署 API，提供溫度、濕度、降雨機率
- **🍽️ 餐廳搜尋系統**：使用 Selenium 自動化搜尋 Google Maps 餐廳資訊
- **🗺️ 智能地址解析**：支援詳細地址、地標名稱、Google Maps 短網址
- **🤖 聊天機器人前端**：直觀的對話式餐廳搜尋介面
- **🚀 FastAPI 後端**：高性能 REST API 與即時餐廳搜尋
- **📍 距離計算**：自動計算餐廳與目標位置的距離

### 🚧 規劃中功能

以下功能可於未來版本中實作：

- 空氣品質與流汗指數計算
- 人潮推估與尖峰時段預測
- 菜單 OCR 與結構化處理
- 機器學習推薦排序引擎

---

## 🧠 專案特色

本系統採用 **Selenium 瀏覽器自動化技術**，模擬真實使用者行為搜尋 Google Maps 餐廳資訊，具備以下核心特色：

### 🎯 多格式地址支援

- **Google Maps 短網址**：自動展開並提取位置座標
- **詳細地址**：支援完整台灣地址格式（如：台北市中山區南京東路）
- **地標名稱**：支援知名地標搜尋（如：台北 101、彰化大佛）
- **區域搜尋**：支援模糊地區搜尋（如：台北中山區）

### 🤖 智能搜尋技術

- **Selenium 自動化**：使用真實瀏覽器避免反爬蟲機制
- **多策略搜尋**：結合多種 CSS 選擇器確保高成功率
- **距離計算**：自動計算餐廳與目標位置的直線距離
- **結果過濾**：智能過濾非餐廳相關結果

---

## 📁 專案結構

```plaintext
```plaintext
ai-lunch-mind/
├── frontend/                     # 前端介面
│   ├── index.html                # 首頁導覽
│   ├── weather.html              # 天氣查詢聊天機器人
│   └── restaurant.html           # ✅ 餐廳搜尋聊天機器人
│
├── modules/                      # 功能模組
│   ├── air_quality.py            # 🚧 空氣品質與流汗指數
│   ├── crowd_estimation.py       # 🚧 人潮預測與分析
│   ├── google_maps.py            # ✅ Selenium 餐廳搜尋系統
│   ├── menu_extraction.py        # 🚧 菜單 OCR 與解析
│   ├── recommendation_engine.py  # 🚧 推薦排序引擎
│   ├── taiwan_locations.py       # ✅ 台灣測試地點資料
│   └── weather.py                # ✅ 中央氣象署天氣 API
│
├── 🐳 容器化檔案
│   ├── Dockerfile                # Docker 映像建構檔
│   ├── docker-compose.yml        # 容器編排配置
│   └── requirements.txt          # Python 依賴清單
│
├── 📄 專案文件
│   ├── GOOGLE_MAPS_SETUP.md      # ✅ 餐廳搜尋模組使用指南
│   ├── install_requirements_local.bat  # ✅ 本地開發依賴安裝
│   └── README.md                 # 專案說明文件
│
├── main.py                       # ✅ FastAPI 主程式
├── .env                          # API 金鑰設定
├── .dockerignore                 # Docker 忽略檔案
└── .gitignore                    # Git 忽略檔案設定
```

---

## 🚀 快速開始

### 1. 環境需求

- **本地開發**：Python 3.8+、Chrome 瀏覽器
- **容器化部署**：Docker 和 Docker Compose
- 中央氣象署 Open Data API Token

### 2. 快速啟動（容器化）🐳

```bash
# 1. 複製專案
git clone <repository-url>
cd ai-lunch-mind

# 2. 設定環境變數
echo "CWB_API_TOKEN=your_cwb_api_token_here" > .env

# 3. 使用 Docker Compose 啟動
docker-compose up --build

# 服務將在 http://localhost:8000 啟動
```

### 3. 本地開發安裝

```bash
# 1. 建立 .env 檔案
echo "CWB_API_TOKEN=your_cwb_api_token_here" > .env

# 2. 安裝依賴
# Windows:
./install_requirements_local.bat

# Linux/Mac:
pip install -r requirements.txt

# 3. 啟動伺服器
python main.py
```

### 4. 容器化部署指令

```bash
# 建構映像
docker build -t ai-lunch-mind .

# 執行容器
docker run -d \
  --name ai-lunch-mind \
  -p 8000:8000 \
  -e CWB_API_TOKEN=your_token_here \
  ai-lunch-mind

# 使用 Docker Compose（推薦）
docker-compose up -d

# 查看日誌
docker-compose logs -f

# 停止服務
docker-compose down
```

---

## 📡 API 端點

### 天氣查詢 API

**GET** `/weather`

查詢指定座標的即時天氣資訊

#### 參數

- `latitude` (float): 緯度 (必填)
- `longitude` (float): 經度 (必填)

#### 回應範例

```json
{
  "temperature": 28.5,
  "humidity": 75,
  "pop": 30,
  "location": "台北市",
  "timestamp": "2024-01-15T14:30:00Z"
}
```

### 餐廳搜尋 API

**GET** `/restaurants`

使用 Selenium 搜尋 Google Maps 餐廳資訊

#### 餐廳搜尋 API 參數

- `keyword` (string): 搜尋關鍵字（如：火鍋、羊肉、燒烤）
- `user_address` (string): 使用者地址或 Google Maps 短網址
- `max_results` (int): 最大結果數量 (預設: 10, 最大: 20)

#### 餐廳搜尋 API 回應

```json
{
  "success": true,
  "restaurants": [
    {
      "name": "阿宗麵線",
      "address": "台北市中正區峨嵋街8-1號",
      "maps_url": "https://maps.google.com/maps/place/...",
      "rating": 4.2,
      "distance_km": 1.5,
      "price_level": null
    }
  ],
  "total": 8,
  "keyword": "麵線",
  "user_address": "台北市中正區"
}
```

#### 使用範例

```bash
# 基本搜尋
curl "http://localhost:8000/restaurants?keyword=火鍋&user_address=台北市中山區"

# 使用 Google Maps 短網址
curl "http://localhost:8000/restaurants?keyword=羊肉&user_address=https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6"

# 地標搜尋
curl "http://localhost:8000/restaurants?keyword=燒烤&user_address=彰化大佛"
```

### 前端介面

- **首頁導覽**: `http://localhost:8000/`
- **天氣聊天機器人**: `http://localhost:8000/static/weather.html`
- **餐廳搜尋聊天機器人**: `http://localhost:8000/restaurant`

---

## 🛠 技術架構

### 後端技術

- **FastAPI**: 高性能 ASGI 框架，自動產生 OpenAPI 文件
- **Uvicorn**: ASGI 伺服器，支援異步處理
- **Selenium**: 瀏覽器自動化，模擬真實使用者搜尋 Google Maps
- **BeautifulSoup**: HTML 解析，提取餐廳資訊
- **Geopy**: 地理編碼與距離計算
- **Requests**: HTTP 客戶端，用於 API 呼叫

### 前端技術

- **原生 HTML/CSS/JS**: 輕量化前端，無框架依賴
- **響應式設計**: 支援桌機與行動裝置
- **聊天機器人介面**: 直觀的對話式查詢體驗
- **餐廳卡片設計**: 清晰呈現餐廳資訊與距離

### 外部整合

- **中央氣象署 Open Data API**: 官方天氣資料來源
- **Google Maps**: 使用 Selenium 自動化搜尋餐廳資訊
- **Nominatim 地理編碼**: 地址與座標轉換服務

---

## 🔧 使用指南

### 餐廳搜尋功能

系統支援 4 種輸入格式，完全符合使用者的實際需求：

#### 1. Google Maps 短網址 + 關鍵字

```python
# 範例：使用 Google Maps 分享的短網址搜尋羊肉餐廳
search_restaurants(
    keyword="羊肉",
    user_address="https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6"
)
```

#### 2. 詳細地址 + 關鍵字

```python
# 範例：在特定地址附近搜尋火鍋店
search_restaurants(
    keyword="火鍋",
    user_address="243新北市泰山區明志路二段210號"
)
```

#### 3. 地標名稱 + 關鍵字

```python
# 範例：在知名地標附近搜尋燒烤店
search_restaurants(
    keyword="燒烤",
    user_address="彰化大佛"
)
```

#### 4. 區域範圍 + 關鍵字

```python
# 範例：在某個區域內搜尋義大利麵餐廳
search_restaurants(
    keyword="義大利麵",
    user_address="台北中山區"
)
```

### 技術特色

- **智能 URL 解析**：自動展開 Google Maps 短網址並提取座標
- **多層級地址支援**：從精確地址到模糊區域都能處理
- **距離計算**：自動計算並排序最近的餐廳
- **反反爬蟲**：使用 Selenium 模擬真實瀏覽器行為
- **容錯機制**：多種搜尋策略確保高成功率

---

## 🔧 開發指南

### 已實作核心模組

#### 1. 餐廳搜尋模組 (`google_maps.py`)

```python
def search_restaurants(keyword: str, user_address: Optional[str] = None, max_results: int = 10) -> List[Dict[str, Any]]
def search_restaurants_selenium(keyword: str, location_info: Optional[Dict] = None, max_results: int = 10) -> List[Dict[str, Any]]
def extract_location_from_url(url: str) -> Optional[Tuple[float, float, str]]
def calculate_distance(user_coords: Tuple[float, float], restaurant_coords: Tuple[float, float]) -> float
```

#### 2. 天氣查詢模組 (`weather.py`)

```python
def get_weather_data(latitude: float, longitude: float) -> dict
def get_location_weather(location_name: str) -> dict
```

### 待實作模組架構

#### 1. 空氣品質模組 (`air_quality.py`)

```python
def calculate_air_quality_impact(pm25: float, location: str) -> dict
def estimate_sweat_index(temp: float, humidity: float, wind_speed: float) -> float
def get_pollution_alerts(latitude: float, longitude: float) -> list
```

#### 2. 人潮預測模組 (`crowd_estimation.py`)

```python
def predict_crowd_level(restaurant_id: str, datetime_obj: datetime) -> dict
def get_peak_hours(restaurant_id: str, day_of_week: int) -> list
def analyze_wait_time(restaurant_id: str, current_time: datetime) -> dict
```

#### 3. 菜單處理模組 (`menu_extraction.py`)

```python
def extract_menu_from_image(image_path: str) -> dict
def categorize_menu_items(menu_text: str) -> dict
def estimate_price_range(menu_items: list) -> dict
```

#### 4. 推薦引擎 (`recommendation_engine.py`)

```python
def calculate_restaurant_score(restaurant_data: dict, user_preferences: dict) -> float
def rank_restaurants(restaurants: list, weather_data: dict, user_context: dict) -> list
def explain_recommendation(restaurant: dict, factors: dict) -> str
```

---

## 🎯 專案規劃

### 短期目標 (已完成 ✅)

- [x] 完成 Google Maps Selenium 搜尋系統
- [x] 實作多格式地址解析功能
- [x] 建立聊天機器人餐廳搜尋介面
- [x] 整合距離計算與排序功能

### 中期目標 (1-2 個月)

- [ ] 整合空氣品質與人潮預測
- [ ] 實作菜單 OCR 功能
- [ ] 加入使用者偏好學習
- [ ] 建立餐廳評分推薦演算法

### 長期目標 (3-6 個月)

- [ ] 部署至雲端平台
- [ ] 建立完整的機器學習推薦模型
- [ ] 開發行動應用程式
- [ ] 整合更多外部資料源

---

## 📊 測試範例

專案提供完整的測試案例，涵蓋所有支援的搜尋格式：

### 測試案例 1: Google Maps 短網址 + 關鍵字

```python
# 使用 Google Maps 分享連結搜尋羊肉餐廳
results = search_restaurants(
    keyword="羊肉",
    user_address="https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6",
    max_results=5
)
```

### 測試案例 2: 詳細地址 + 關鍵字

```python
# 在新北市泰山區搜尋火鍋店
results = search_restaurants(
    keyword="火鍋",
    user_address="243新北市泰山區明志路二段210號",
    max_results=5
)
```

### 測試案例 3: 地標名稱 + 關鍵字

```python
# 在彰化大佛附近搜尋燒烤店
results = search_restaurants(
    keyword="燒烤",
    user_address="彰化大佛",
    max_results=5
)
```

### 測試案例 4: 區域搜尋 + 關鍵字

```python
# 在台北中山區搜尋義大利麵餐廳
results = search_restaurants(
    keyword="義大利麵",
    user_address="台北中山區",
    max_results=5
)
```

### 回傳結果格式

```python
[
    {
        'name': '阿宗麵線',
        'address': '台北市中正區峨嵋街8-1號',
        'maps_url': 'https://maps.google.com/maps/place/...',
        'rating': 4.2,
        'distance_km': 1.5,
        'price_level': None
    }
]
```

---

## 🤝 貢獻指南

1. Fork 此專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 開啟 Pull Request

---

## 📝 授權條款

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

---

## 📞 聯絡資訊

專案維護者：[您的名稱]  
Email: [您的 Email]  
專案連結：[GitHub Repository URL]

---

> 最後更新：2025年7月 | 主要功能：✅ Selenium 餐廳搜尋系統已完成
