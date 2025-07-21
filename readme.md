# 午餐吃什麼 🍱 — AI 餐廳推薦系統

> 專案目標：根據天氣、預算、時間、人潮、空氣品質與對話輸入，使用 AI 分析與實時資料推薦用餐地點。  
> ✅ **100% 真實資料**｜✅ **可部署 API**｜✅ **模組化設計**｜✅ **現代化前端介面**

---

## 🎯 專案現況

### ✅ 已完成功能

- **天氣查詢系統**：整合中央氣象署 API，提供溫度、濕度、降雨機率
- **現代化前端**：聊天機器人風格的天氣查詢介面
- **FastAPI 後端**：高性能 REST API 與靜態檔案服務
- **台灣地點資料**：100+ 測試地點覆蓋本島與離島

### 🚧 開發中功能

以下模組已建立框架，等待後續實作：

- 空氣品質與流汗指數計算
- 人潮推估與尖峰時段預測
- Google Maps 餐廳搜尋整合
- 菜單 OCR 與結構化處理
- 智慧推薦排序引擎

---

## 🧠 專案概念

本系統整合 **中央氣象署** 天氣資料、**Google Maps** 餐廳搜尋、人潮推估、空氣品質與使用者回饋，透過多因子推薦模型提供最合適的餐廳建議。

---

## 📁 專案結構

```plaintext
```plaintext
ai-lunch-mind/
├── frontend/                     # 前端介面
│   ├── index.html                # 首頁目錄
│   └── weather.html              # 天氣查詢聊天機器人
│
├── modules/                      # 功能模組
│   ├── air_quality.py            # 🚧 空氣品質與流汗指數
│   ├── crowd_estimation.py       # 🚧 人潮預測與分析
│   ├── google_maps.py            # 🚧 Google Places 整合
│   ├── menu_extraction.py        # 🚧 菜單 OCR 與解析
│   ├── recommendation_engine.py  # 🚧 推薦排序引擎
│   ├── taiwan_locations.py       # ✅ 台灣測試地點資料
│   └── weather.py                # ✅ 中央氣象署天氣 API
│
├── main.py                       # ✅ FastAPI 主程式
├── .env                          # API 金鑰設定
├── .gitignore                    # Git 忽略檔案設定
└── README.md                     # 專案說明文件
```

---

## 🚀 快速開始

### 1. 環境需求

- Python 3.8+
- 中央氣象署 Open Data API Token

### 2. 安裝與設定

```bash
# 1. 複製專案
git clone <repository-url>
cd ai-lunch-mind

# 2. 建立 .env 檔案
echo "CWB_API_TOKEN=your_cwb_api_token_here" > .env

# 3. 安裝依賴
pip install fastapi uvicorn requests python-dotenv

# 4. 啟動伺服器
python main.py
```

### 3. 取得 API Token

1. 前往 [中央氣象署 Open Data](https://opendata.cwb.gov.tw/index) 註冊帳號
2. 申請 API 授權碼
3. 將授權碼加入 `.env` 檔案

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

#### 使用範例

```bash
# 台北 101 天氣
curl "http://localhost:8000/weather?latitude=25.0340&longitude=121.5645"
```

### 前端介面

- **首頁目錄**: `http://localhost:8000/`
- **天氣聊天機器人**: `http://localhost:8000/static/weather.html`

---

## 🛠 技術架構

### 後端技術

- **FastAPI**: 高性能 ASGI 框架，自動產生 OpenAPI 文件
- **Uvicorn**: ASGI 伺服器，支援異步處理
- **Requests**: HTTP 客戶端，用於 API 呼叫
- **Python-dotenv**: 環境變數管理

### 前端技術

- **原生 HTML/CSS/JS**: 輕量化前端，無框架依賴
- **響應式設計**: 支援桌機與行動裝置
- **聊天機器人介面**: 直觀的對話式查詢體驗

### 外部 API

- **中央氣象署 Open Data API**: 官方天氣資料來源
  - 使用 `F-D0047-001` 至 `F-D0047-093` 系列資料集
  - 涵蓋全台灣本島與離島天氣預報

---

## 🔧 開發規劃

### 待實作模組

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

#### 3. Google Maps 整合 (`google_maps.py`)

```python
def search_restaurants(latitude: float, longitude: float, radius: int) -> list
def get_restaurant_details(place_id: str) -> dict
def get_restaurant_reviews(place_id: str, limit: int) -> list
```

#### 4. 菜單處理模組 (`menu_extraction.py`)

```python
def extract_menu_from_image(image_path: str) -> dict
def categorize_menu_items(menu_text: str) -> dict
def estimate_price_range(menu_items: list) -> dict
```

#### 5. 推薦引擎 (`recommendation_engine.py`)

```python
def calculate_restaurant_score(restaurant_data: dict, user_preferences: dict) -> float
def rank_restaurants(restaurants: list, weather_data: dict, user_context: dict) -> list
def explain_recommendation(restaurant: dict, factors: dict) -> str
```

---

## 🎯 專案目標

### 短期目標 (1-2 週)

- [ ] 完成 Google Maps API 整合
- [ ] 實作基礎推薦演算法
- [ ] 建立簡單的前端查詢介面

### 中期目標 (1-2 個月)

- [ ] 整合空氣品質與人潮預測
- [ ] 實作菜單 OCR 功能
- [ ] 加入使用者偏好學習

### 長期目標 (3-6 個月)

- [ ] 部署至雲端平台
- [ ] 建立完整的機器學習推薦模型
- [ ] 開發行動應用程式

---

## 📊 測試資料

專案包含 100+ 台灣測試地點，覆蓋：

- **本島城市**: 台北、新北、桃園、台中、台南、高雄等
- **離島地區**: 金門、馬祖、澎湖、綠島、蘭嶼等
- **山區景點**: 陽明山、阿里山、太魯閣等

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

> 最後更新：2024年1月
