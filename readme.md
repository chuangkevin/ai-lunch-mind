# 午餐吃什麼 - AI 智能推薦系統

[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688.svg?style=flat&logo=FastAPI)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg?style=flat&logo=python)](https://python.org)
[![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-blue.svg?style=flat&logo=google)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat)](LICENSE)

## 系統概述

整合 Gemini AI 語意分析、中央氣象署天氣資料、Google Maps 真實餐廳搜尋、社群平台口碑，根據你的位置、天氣、預算提供個人化午餐推薦。

### 核心特色

- **Gemini 2.5 Flash 語意分析** - 理解自然語言需求，提取位置、食物偏好、預算
- **Google Maps 真實餐廳資料** - Selenium headless 搜尋，取得真實名稱、地址、評分
- **天氣感知推薦** - 中央氣象署 API 整合流汗指數，天氣好走遠一點、天氣差找近的
- **真實步行距離** - ArcGIS 地理編碼 + geodesic 公式計算，不靠 AI 猜測
- **社群口碑** - 搜尋 Dcard/PTT 討論，標記社群推薦的餐廳
- **SSE 即時串流** - Server-Sent Events 即時顯示分析進度（意圖→天氣→搜尋→排序）
- **降雨警示** - 降雨機率 >= 50% 自動提醒帶傘
- **Gemini API Key Pool** - 多把 key 隨機選用，429 自動重試，SQLite 儲存

---

## 快速開始

### 環境需求

```
Python 3.11+
Chrome/Chromium (Selenium headless 搜尋用)
Gemini API Key (至少 1 把，建議 5 把以上)
CWB API Key (可選，用於真實天氣資料)
```

### 安裝

```bash
git clone https://github.com/chuangkevin/ai-lunch-mind.git
cd ai-lunch-mind
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 設定環境變數

```bash
# .env
CWB_API_KEY=your_cwb_api_key  # 可選
```

Gemini API Key 不放 `.env`，透過網頁設定頁面匯入，存在 SQLite（不進 git）。

### 啟動

```bash
uvicorn main:app --host 127.0.0.1 --port 5000
```

### 使用

1. 開啟 `http://localhost:5000/settings` 匯入 Gemini API Key（一行一把）
2. 開啟 `http://localhost:5000/ai_lunch` 開始使用
3. 輸入位置和需求，例如：「我在台北101，想吃火鍋」

---

## 使用方式

### 輸入範例

```
"我在台北101，想吃火鍋"
"信義區附近 200 元以內的便當"
"台北車站附近想吃拉麵"
"午餐吃什麼"（搭配 GPS 或手動位置）
```

### 位置設定（三層優先）

1. **對話中提到** - 「我在台北101」自動覆蓋其他設定
2. **手動輸入** - 點頂部位置區域修改，存在 localStorage
3. **GPS 定位** - 瀏覽器 Geolocation API，首次自動觸發

### 搜尋距離（依天氣自動調整）

| 條件 | 最大距離 | 步行時間 |
|------|---------|---------|
| 舒適天氣（流汗指數 < 5） | 800m | 約 10 分鐘 |
| 普通天氣（流汗指數 5-6） | 600m | 約 8 分鐘 |
| 不舒適（流汗指數 >= 7 或降雨 >= 50%） | 400m | 約 5 分鐘 |
| 範圍內無結果 | 自動擴大 | 顯示最近的 N 間 |

---

## 技術架構

### 推薦流程（SSE 串流）

```
使用者輸入
  |
  v
Phase 1: Gemini 意圖分析 (~1s)
  -> 提取位置、關鍵字、預算
  |
Phase 2: 天氣查詢 (~1s)
  -> 中央氣象署 API -> 流汗指數 -> 搜尋距離
  |
Phase 3: Google Maps 搜尋 (~3-5s)
  -> Selenium headless -> 真實餐廳資料
  -> Gemini 補充推薦理由 + 過濾非餐廳
  |
Phase 4: 距離計算 + 排序 (~1-2s)
  -> ArcGIS geocode -> geodesic 公式
  -> 距離過濾 + 排序
  |
Phase 5: 社群搜尋 (~1-2s)
  -> Google 搜尋 Dcard/PTT 討論
  |
  v
即時串流餐廳卡片到前端
```

### 模組結構

```
modules/
├── ai/
│   ├── gemini_pool.py          # API Key Pool (隨機選 key, 429 重試, SQLite)
│   ├── intent_analyzer.py      # Gemini 意圖分析 (位置/關鍵字/預算)
│   └── restaurant_scorer.py    # 評分公式 (距離/評分/社群/預算)
├── scraper/
│   ├── browser_pool.py         # Selenium Chrome 池 (lazy init, headless)
│   ├── google_maps.py          # Google Maps 搜尋 + 資料提取
│   ├── google_search.py        # Google 搜尋爬蟲
│   ├── ptt_scraper.py          # PTT 爬蟲
│   └── selectors.py            # CSS selector 集中管理
├── geo/
│   ├── geocoding.py            # 地址解析 + 座標轉換
│   └── distance.py             # 距離計算 (haversine + 步行)
├── fast_search.py              # 快速搜尋 pipeline (Selenium + Gemini enrichment)
├── recommendation_engine.py    # 主流程編排
├── weather.py                  # 中央氣象署 API
├── sweat_index.py              # 流汗指數計算
└── sqlite_cache_manager.py     # SQLite 快取

frontend/
├── ai_lunch_v2.html            # 主介面 (深色科技風)
└── settings.html               # API Key 管理

main.py                         # FastAPI 伺服器 + SSE 端點
```

### API 端點

**推薦 API：**

| 端點 | 方法 | 說明 |
|------|------|------|
| `/chat-recommendation-stream` | GET | SSE 串流推薦（主要使用） |
| `/chat-recommendation` | GET | 分階段推薦（向後相容） |
| `/ai-lunch-recommendation` | GET | 直接推薦 |

**金鑰管理：**

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/keys/import` | POST | 批量匯入 Gemini API Key |
| `/api/keys/status` | GET | 金鑰狀態（僅顯示後 4 碼） |
| `/api/keys/usage` | GET | 使用統計 |
| `/api/keys/{suffix}` | DELETE | 刪除金鑰 |

**其他：**

| 端點 | 方法 | 說明 |
|------|------|------|
| `/weather` | GET | 天氣查詢 |
| `/sweat-index` | GET | 流汗指數 |
| `/health` | GET | 健康檢查 |

**頁面：**
- `/ai_lunch` - AI 推薦介面
- `/settings` - 金鑰管理
- `/restaurant` - 餐廳搜尋
- `/weather_page` - 天氣查詢

### 技術棧

| 層級 | 技術 |
|------|------|
| AI | Google Gemini 2.5 Flash / 2.0 Flash Lite |
| 後端 | Python 3.11+, FastAPI, Uvicorn |
| 搜尋 | Selenium (headless Chrome), BeautifulSoup |
| 地理 | ArcGIS Geocoding, Geopy (geodesic) |
| 天氣 | 中央氣象署 CWB API |
| 快取 | SQLite |
| 前端 | HTML5 + CSS3 + JavaScript (原生，無框架) |
| 串流 | Server-Sent Events (SSE) |

---

## 資料來源與信任原則

| 資料 | 來源 | 信任度 |
|------|------|--------|
| 餐廳名稱、地址、評分 | Google Maps (Selenium) | 高 |
| 步行距離 | ArcGIS geocode + geodesic 公式 | 高 |
| 天氣、降雨機率 | 中央氣象署 API | 高 |
| 社群討論 | Google 搜尋 Dcard/PTT | 中 |
| 推薦理由 | Gemini AI 生成 | 僅供參考 |

**Gemini 不生成餐廳資料。** 所有餐廳名稱、地址、評分來自 Google Maps。Gemini 只負責意圖分析和補充推薦理由。

---

## 測試

```bash
# 單元測試 (43 tests)
python -m unittest test_system_overhaul -v

# 包含：API Key Pool、評分公式、意圖分析 fallback、搜尋場景
```

---

## 授權

MIT License - 詳見 [LICENSE](LICENSE)

## 致謝

- [Google Gemini](https://ai.google.dev) - AI 語意分析
- [中央氣象署](https://www.cwb.gov.tw) - 天氣資料 API
- [Google Maps](https://maps.google.com) - 餐廳資料
- [FastAPI](https://fastapi.tiangolo.com) - Web 框架
- [Selenium](https://selenium.dev) - 瀏覽器自動化
- [ArcGIS](https://www.arcgis.com) - 地理編碼
