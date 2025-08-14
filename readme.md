# 午餐吃什麼 🍱 - AI 智能推薦系統

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688.svg?style=flat&logo=FastAPI)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?style=flat&logo=python)](https://python.org)
[![ChatGPT](https://img.shields.io/badge/ChatGPT-4o--mini-orange.svg?style=flat&logo=openai)](https://openai.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat)](LICENSE)

## ✅ 系統概述

> **🤖 對話式智能推薦**：整合 ChatGPT 語意分析、天氣查詢、流汗指數計算與 Google Maps 餐廳搜尋，提供最適合的用餐建議。

### 🎯 核心特色

- **🤖 ChatGPT 語意分析**：使用 GPT-4o-mini 深度理解用戶需求，區分地址、店名、食物類型
- **🎯 智能關鍵字擴展**：拉麵 → [拉麵, 日式拉麵, 豚骨拉麵]，東山鴨頭 → [鴨頭, 滷味, 小吃]
- **🛡️ AI 驗證系統**：三層驗證確保推薦品質（位置、意圖、推薦品質）
- **🌤️ 天氣感知推薦**：根據溫度、濕度、降雨機率調整餐點類型
- **😅 流汗指數優化**：依據流汗指數動態調整搜尋範圍（500m-3000m）
- **🗣️ 自然語言理解**：支援對話式需求分析與位置解析
- **📊 距離優先排序**：智能餐廳評分（距離優先、評分、天氣適應性、價格）
- **🌧️ 降雨警示整合**：自動提供雨具攜帶建議
- **🔥❄️ 餐點溫度分類**：智能過濾不適合的餐點類型（熱食/冷食/中性）

---

## 🚀 快速開始

### 📋 環境需求

```bash
Python 3.11+
Chrome/Chromium 瀏覽器 (用於 Google Maps 搜尋)
中央氣象署 API 金鑰 (可選，用於真實天氣資料)
OpenAI API 金鑰 (用於 ChatGPT 分析)
```

### 🔧 安裝步驟

1. **克隆專案**
```bash
git clone https://github.com/chuangkevin/ai-lunch-mind.git
cd ai-lunch-mind
```

2. **建立虛擬環境**
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux
```

3. **安裝依賴**
```bash
pip install -r requirements.txt
```

4. **設定環境變數**
```bash
# 建立 .env 檔案
OPENAI_API_KEY=your_openai_api_key_here
CWB_API_KEY=your_cwb_api_key_here  # 可選
```

5. **啟動系統**
```bash
python main.py
```

6. **開啟瀏覽器**
```
http://localhost:5001/ai_lunch
```

---

## 🎯 使用方式

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

#### 4️⃣ Google Maps URL
```
"https://maps.app.goo.gl/xxxxx 這裡有什麼好吃的？"
"g.co/kgs/xxxxx 附近的咖啡店"
```

### 🎯 推薦規則設計

#### 📍 動態搜尋範圍
- **流汗指數 ≥ 8**：極不舒適 → **500m 內**
- **流汗指數 6-7**：不舒適 → **1000m 內** 
- **流汗指數 4-5**：普通 → **2000m 內**
- **流汗指數 ≤ 3**：舒適 → **3000m 內**

#### 🍽️ 餐點類型智能過濾
- **高溫天氣（流汗指數≥7 或 溫度≥32°C）**：降低熱食推薦，提升冷食權重
- **舒適天氣（流汗指數≤3 或 溫度≤20°C）**：提升熱食推薦
- **降雨機率高**：優先推薦室內用餐環境

---

## 🛠 技術架構

### 🔧 核心模組

```
modules/
├── ai_recommendation_engine.py  # 🤖 AI 推薦引擎 (主要邏輯)
├── ai_validator.py             # 🛡️ AI 驗證系統 (品質保證)
├── dialog_analysis.py          # 💬 ChatGPT 對話分析
├── google_maps.py              # 🗺️ Google Maps 搜尋整合
├── weather.py                  # 🌡️ 中央氣象署 API
├── sweat_index.py             # 😅 流汗指數計算
└── feedback_learning.py       # 📈 學習回饋機制 (待開發)
```

### 🌐 API 端點

**主要推薦 API：**
- `GET /chat-recommendation` - 分階段對話式推薦
- `POST /chat/recommend` - JSON 格式對話推薦  
- `GET /ai-lunch-recommendation` - 直接推薦API

**功能支援 API：**
- `GET /weather` - 天氣查詢
- `GET /sweat-index` - 流汗指數查詢
- `GET /restaurants` - 餐廳搜尋
- `GET /location-options` - 位置候選列表

**頁面路由：**
- `/` - 主頁面
- `/ai_lunch` - AI 推薦聊天界面
- `/restaurant` - 餐廳搜尋頁面
- `/weather_page` - 天氣查詢頁面

### 後端技術

- **FastAPI**: 高性能 ASGI 框架，自動產生 OpenAPI 文件
- **Uvicorn**: ASGI 伺服器，支援異步處理
- **Selenium**: 瀏覽器自動化，模擬真實使用者搜尋 Google Maps
- **BeautifulSoup**: HTML 解析，提取餐廳資訊
- **Geopy**: 地理編碼與距離計算
- **Requests**: HTTP 客戶端，用於 API 呼叫

### 前端技術

- **HTML5 + CSS3**: 響應式設計
- **JavaScript**: 異步資料處理與 DOM 操作
- **Bootstrap**: UI 框架
- **Chart.js**: 資料視覺化（天氣圖表）

---

## ✅ 已實現功能

### 🤖 AI 智能推薦引擎
- **🧠 ChatGPT 語意分析**：使用 GPT-4o-mini 深度理解「龜山區東山鴨頭」等複雜查詢
- **🎯 智能關鍵字映射**：拉麵→[拉麵,日式拉麵,豚骨拉麵]、東山鴨頭→[鴨頭,滷味,小吃]
- **📊 距離優先排序**：近距離餐廳優先推薦，雙重距離計算機制
- **🔄 多層次備用機制**：ChatGPT→關鍵字檢測→時間推薦→天氣推薦
- **💬 簡化對話流程**：移除複雜位置選擇，實現一步式自動推薦

### 🛡️ AI 驗證系統 (NEW)
- **📍 位置驗證**：檢查地標關鍵字提取正確性，支援地理編碼驗證
- **🎯 意圖匹配驗證**：使用AI分析搜尋關鍵字與使用者意圖相關性
- **🍽️ 推薦品質驗證**：評估餐廳推薦的多樣性、覆蓋率和滿意度
- **🔍 具體性問題檢測**：自動識別過度泛化問題（如：拉麵→麵食）
- **⚡ 動態關鍵字調整**：根據驗證結果自動優化搜尋策略
- **📊 品質指標監控**：提供信心度、相關性分數等量化指標

### 🌤️ 天氣整合系統
- **🌡️ 中央氣象署 API**：整合官方天氣資料
- **😅 流汗指數計算**：基於溫度、濕度、風速計算體感溫度
- **🌧️ 降雨機率查詢**：提供降雨警示與雨具攜帶建議

### 🗺️ 地理位置處理
- **📍 多格式地址支援**：詳細地址、地標名稱、Google Maps URL
- **🌍 智能地址解析**：自動展開短網址並提取座標
- **📏 距離計算**：精確計算餐廳與目標位置距離

### 🍽️ 餐廳搜尋系統
- **🔍 Selenium 自動化**：模擬真實使用者行為搜尋 Google Maps
- **🔄 並行搜尋機制**：多關鍵字同時搜尋，提升效率
- **🔗 URL 可靠性機制**：多層後備方案確保連結有效性

### 🖥️ 用戶界面
- **💬 對話式聊天界面**：直觀的餐廳推薦體驗
- **📱 響應式設計**：支援桌面和行動裝置
- **⚡ 即時回饋**：搜尋進度和結果即時顯示

---

## 🚧 待優化項目

### 🚀 效能優化
1. **搜尋快取機制**：避免重複搜尋相同位置
2. **Google Maps 請求優化**：減少搜尋時間
3. **並行處理增強**：提升多關鍵字搜尋效率

### 📊 品質提升
1. **餐廳評分算法精進**：更精確的推薦排序
2. **用戶偏好學習**：根據選擇歷史優化推薦
3. **推薦解釋功能**：說明推薦理由

### 🔄 功能擴展
1. **多人聚餐推薦**：考慮多人需求
2. **預約整合功能**：直接連結訂位系統
3. **個人化記憶**：記住用戶偏好

---

## 📊 專案結構

```
ai-lunch-mind/
├── main.py                     # FastAPI 主程式
├── requirements.txt            # Python 依賴
├── .env                        # 環境變數設定
├── modules/                    # 核心模組
│   ├── ai_recommendation_engine.py
│   ├── ai_validator.py         # AI 驗證系統
│   ├── dialog_analysis.py
│   ├── google_maps.py
│   ├── weather.py
│   ├── sweat_index.py
│   └── feedback_learning.py
├── frontend/                   # 前端檔案
│   ├── ai_lunch.html          # 主要聊天界面
│   ├── index.html             # 首頁
│   ├── restaurant.html        # 餐廳搜尋頁面
│   └── weather.html           # 天氣查詢頁面
├── doc/                       # 文件
│   ├── 需求文件.md
│   └── 搜尋速度優化解決方案.md
└── test_*.py                  # 測試檔案
```

---

## 🤝 貢獻指南

歡迎提交 Issue 和 Pull Request！

### 開發設定

1. Fork 本專案
2. 建立功能分支：`git checkout -b feature/new-feature`
3. 提交變更：`git commit -am 'Add new feature'`
4. 推送分支：`git push origin feature/new-feature`
5. 建立 Pull Request

### 程式碼規範

- 遵循 PEP 8 風格指南
- 添加適當的註解和文檔字串
- 編寫單元測試
- 確保所有測試通過

---

## 📄 授權

本專案採用 MIT 授權條款 - 詳見 [LICENSE](LICENSE) 檔案

---

## 🙏 致謝

- [OpenAI](https://openai.com) - ChatGPT API
- [中央氣象署](https://www.cwb.gov.tw) - 天氣資料 API
- [Google Maps](https://maps.google.com) - 地圖與餐廳資料
- [FastAPI](https://fastapi.tiangolo.com) - Web 框架
- [Selenium](https://selenium.dev) - 瀏覽器自動化

---

## 📞 聯絡資訊

如有任何問題或建議，歡迎透過以下方式聯絡：

- GitHub Issues: [專案 Issues](https://github.com/chuangkevin/ai-lunch-mind/issues)
- Email: [您的聯絡信箱]

---

**⭐ 如果這個專案對您有幫助，請給我們一個 Star！**
