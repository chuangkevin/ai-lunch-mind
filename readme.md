# 午餐吃什麼 🍱 - AI 智能推薦系統

## ✅ AI 午餐推薦主功能

> **🤖 對話式智能推薦**：整合 ChatGPT 語意分析、天氣查詢、流汗指數計算與 Google Maps 餐廳搜尋，提供最適合的用餐建議。

### 🧠 智能推薦特色

- **🤖 ChatGPT 語意分析**：使用 GPT-4o-mini 深度理解用戶需求，區分地址、店名、食物類型
- **🎯 智能關鍵字擴展**：東山鴨頭 → [鴨頭, 滷味, 小吃]，鹽酥雞 → [鹽酥雞, 炸物, 小吃]
- **🌤️ 天氣感知推薦**：根據溫度、濕度、降雨機率調整餐點類型
- **😅 流汗指數優化**：依據流汗指數動態調整搜尋範圍（500m-3000m）
- **🗣️ 自然語言理解**：支援對話式需求分析與位置解析
- **📊 距離優先排序**：智能餐廳評分（距離優先、評分、天氣適應性、價格）
- **🌧️ 降雨警示整合**：自動提供雨具攜帶建議
- **🔥❄️ 餐點溫度分類**：智能過濾不適合的餐點類型（熱食/冷食/中性）

### 🎯 推薦規則設計

#### 📍 動態搜尋範圍
- **流汗指數 ≥ 8**：極不舒適 → **500m 內**
- **流汗指數 6-7**：不舒適 → **1000m 內** 
- **流汗指數 4-5**：普通 → **2000m 內**
- **流汗指數 ≤ 3**：舒適 → **3000m 內**

#### �️ 餐點類型智能過濾
- **高溫天氣（流汗指數≥7 或 溫度≥32°C）**：降低熱食推薦，提升冷食權重
- **舒適天氣（流汗指數≤3 或 溫度≤20°C）**：提升熱食推薦
- **降雨機率高**：優先推薦室內用餐環境

### 🗣️ 對話互動方式

#### 1️⃣ 位置 + 需求型
```
"我在台北101，想吃火鍋"
"信義區附近有什麼冰品店？"
"西門町的燒烤店推薦"
```

#### 2️⃣ 地址精確型
```
"台北市中山區南京東路的日式料理"
"新北市板橋區的義大利麵餐廳"
```

#### 3️⃣ 地標模糊型
```
"台北車站附近想吃拉麵"
"淡水老街的小吃推薦"
```

---

## 🎯 專案現況

### ✅ 已完成功能

- **🤖 AI 智能推薦引擎**：對話式需求分析與智能餐廳推薦
  - **🧠 ChatGPT 語意分析**：使用 GPT-4o-mini 深度理解「龜山區東山鴨頭」等複雜查詢
  - **🎯 智能關鍵字映射**：東山鴨頭→[鴨頭,滷味,小吃]、牛肉麵→[牛肉麵,麵食]
  - **📊 距離優先排序**：近距離餐廳優先推薦，雙重距離計算機制
  - **🔄 多層次備用機制**：ChatGPT→關鍵字檢測→時間推薦→天氣推薦
  - **💬 位置記憶邏輯**：系統會記住使用者位置，支援位置更新提示
  - **🗣️ 初始引導機制**：首次使用時主動詢問位置，提供多種輸入方式  
  - **📱 Shift+Enter 支援**：對話框支援多行輸入，提升使用體驗
  - **🔗 Google Maps 新格式**：支援最新的 Google Maps 分享網址解析
- **🌤️ 天氣查詢系統**：整合中央氣象署 API，提供溫度、濕度、**降雨機率**
- **🌧️ 流汗指數計算**：基於溫度、濕度、風速計算體感溫度與流汗指數，**包含降雨影響分析**
- **🍽️ 餐廳搜尋系統**：使用 Selenium 自動化搜尋 Google Maps 餐廳資訊
- **🗺️ 智能地址解析**：支援詳細地址、地標名稱、Google Maps 短網址
- **🔗 URL可靠性機制**：多層後備方案確保所有餐廳都有可用的Google Maps連結
- **🤖 聊天機器人前端**：直觀的對話式餐廳搜尋介面
- **🚀 FastAPI 後端**：高性能 REST API 與即時餐廳搜尋
- **📍 距離計算**：自動計算餐廳與目標位置的距離

### 🚧 規劃中功能

以下功能可於未來版本中實作：

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
- **URL可靠性保障**：三層後備機制確保每個餐廳都有可用連結
  - 第一層：系統提取的原始餐廳place連結
  - 第二層：固定格式搜尋連結（餐廳名稱+地址）
  - 第三層：純餐廳名稱搜尋連結
- **距離計算**：自動計算餐廳與目標位置的直線距離
- **結果過濾**：智能過濾非餐廳相關結果

---

## 📁 專案結構

```plaintext
ai-lunch-mind/
├── frontend/                     # 前端介面
│   ├── index.html                # 首頁導覽
│   ├── ai_lunch.html             # ✅ AI 午餐推薦聊天機器人
│   ├── weather.html              # 天氣查詢聊天機器人
│   └── restaurant.html           # ✅ 餐廳搜尋聊天機器人
│
├── modules/                      # 功能模組
│   ├── ai_recommendation_engine.py # ✅ AI 智能推薦引擎
│   ├── dialog_analysis.py        # ✅ ChatGPT 對話語意分析
│   ├── sweat_index.py            # ✅ 流汗指數與體感溫度計算
│   ├── google_maps.py            # ✅ Selenium 餐廳搜尋系統
│   ├── weather.py                # ✅ 中央氣象署天氣 API
│   ├── taiwan_locations.py       # ✅ 台灣測試地點資料
│   ├── crowd_estimation.py       # 🚧 人潮預測與分析
│   ├── menu_extraction.py        # 🚧 菜單 OCR 與解析
│   └── recommendation_engine.py  # 🚧 推薦排序引擎
│
├── 🐳 容器化檔案
│   ├── Dockerfile                # Docker 映像建構檔
│   ├── docker-compose.yml        # 容器編排配置
│   └── requirements.txt          # Python 依賴清單
│
├── 📄 專案文件
│   ├── doc/需求文件.md            # ✅ 專案需求與功能規格
│   ├── GOOGLE_MAPS_SETUP.md      # ✅ 餐廳搜尋模組使用指南  
│   ├── DATABASE_MIGRATION_TODO.md # 🚧 資料庫遷移規劃
│   └── README.md                 # 專案說明文件
│
├── main.py                       # ✅ FastAPI 主程式
├── .env                          # API 金鑰設定 (需要 OPENAI_API_KEY)
├── .dockerignore                 # Docker 忽略檔案
└── .gitignore                    # Git 忽略檔案設定
```

---

## 🚀 快速開始

### 1. 環境需求

- **本地開發**：Python 3.8+、Chrome 瀏覽器
- **容器化部署**：Docker 和 Docker Compose
- **API 金鑰需求**：
  - 中央氣象署 Open Data API Token
  - OpenAI API Key (用於 ChatGPT 語意分析)

### 2. 快速啟動（容器化）🐳

```bash
# 1. 複製專案
git clone <repository-url>
cd ai-lunch-mind

# 2. 設定環境變數
echo "CWB_API_KEY=your_cwb_api_key_here" > .env
echo "OPENAI_API_KEY=your_openai_api_key_here" >> .env

# 3. 使用 Docker Compose 啟動
docker-compose up --build

# 服務將在 http://localhost:5000 啟動
```

### 3. 本地開發安裝

```bash
# 1. 建立 .env 檔案
echo "CWB_API_KEY=your_cwb_api_key_here" > .env
echo "OPENAI_API_KEY=your_openai_api_key_here" >> .env

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
  -p 5000:5000 \
  -e CWB_API_KEY=your_key_here \
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

### AI 聊天推薦 API

**GET** `/chat-recommendation`

使用 ChatGPT 進行智能語意分析並推薦餐廳

#### 參數

- `message` (string): 用戶輸入訊息（如：「龜山區東山鴨頭」、「我在西門町找燒烤」）
- `phase` (string): 執行階段（"start" 生成搜尋計劃，"search" 執行搜尋）

#### 回應範例

```json
{
  "success": true,
  "location": "龜山區",
  "search_keywords": ["鴨頭", "滷味", "小吃"],
  "restaurants": [
    {
      "name": "大可 東山丫頭",
      "address": "333桃園市龜山區復興一路102號",
      "distance_km": 18.62,
      "rating": 4.5,
      "food_type": "小吃"
    }
  ],
  "recommendation_summary": "根據目前天氣狀況，為您推薦6家餐廳..."
}
```

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
      "maps_url": "https://maps.google.com/maps/place/阿宗麵線/data=...",
      "rating": 4.2,
      "distance_km": 1.5,
      "price_level": "$1-200"
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
curl "http://localhost:5000/restaurants?keyword=火鍋&user_address=台北市中山區"

# 使用 Google Maps 短網址
curl "http://localhost:5000/restaurants?keyword=羊肉&user_address=https://maps.app.goo.gl/qmnmsH1EwrYnYsCF6"

# 地標搜尋
curl "http://localhost:5000/restaurants?keyword=燒烤&user_address=彰化大佛"
```

### 前端介面

- **首頁導覽**: `http://localhost:5000/`
- **天氣聊天機器人**: `http://localhost:5000/weather.html`
- **餐廳搜尋聊天機器人**: `http://localhost:5000/restaurant.html`
- **流汗指數查詢**: `http://localhost:5000/sweat_index.html`

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
- **URL可靠性機制**：三層後備系統確保所有餐廳連結始終可用
  - 原始餐廳place連結：優先使用系統抓取的真實餐廳頁面連結
  - 固定格式後備連結：使用餐廳名稱+地址的搜尋連結
  - 純名稱搜尋連結：最終後備方案使用餐廳名稱搜尋
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

# 🆕 URL可靠性機制
def generate_fallback_maps_url(restaurant_name: str, address: str = "") -> str
def validate_maps_url(url: str) -> bool  
def get_reliable_maps_url(restaurant_info: dict) -> str
```

#### 2. 天氣查詢模組 (`weather.py`)

```python
def get_weather_data(latitude: float, longitude: float) -> dict
def get_location_weather(location_name: str) -> dict
```

### 待實作模組架構

#### 1. 流汗指數模組 (`sweat_index.py`)

```python
def estimate_sweat_index(temp: float, humidity: float, wind_speed: float = 0) -> float
def calculate_heat_index(temp: float, humidity: float) -> float
def get_comfort_level(sweat_index: float) -> dict
def calculate_dining_recommendation(temp: float, humidity: float, wind_speed: float = 0, location: str = "") -> dict
def get_sweat_risk_alerts(temp: float, humidity: float, wind_speed: float = 0) -> list
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
- [x] 實現URL可靠性機制與固定pattern後備方案

### 中期目標 (1-2 個月)

- [ ] 整合流汗指數與人潮預測功能
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
        'maps_url': 'https://maps.google.com/maps/place/阿宗麵線/data=...',
        'rating': 4.2,
        'distance_km': 1.5,
        'price_level': '$1-200'
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

> 最後更新：2025年7月 | 主要功能：✅ ChatGPT 智能語意分析已完成 | ✅ 距離優先排序已實現 | ✅ 流汗指數模組已完成 | ✅ AI 推薦引擎已完成
