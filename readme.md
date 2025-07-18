# 午餐吃什麼 🍱 — AI 餐廳推薦系統

> 專案目標：根據天氣、預算、時間、人潮、空氣品質與對話輸入，使用 AI 分析與實時資料推薦用餐地點。  
> ✅ **100% 真實資料**｜✅ **可部署 API**｜✅ **模組化設計**｜✅ **支援 Copilot 與 Docker Compose**

---

## 🧠 專案概念
本系統整合 **OpenAI** 對話分析、**Google Maps** 餐廳搜尋、**中央氣象署** 天氣資料、人潮推估、空氣品質與使用者回饋，透過多因子推薦模型提供最合適的餐廳建議。

---

## 📁 專案結構
```plaintext
AI-LUNCH-MIND/
├── modules/                      # 功能模組（純邏輯 / 第三方 API）
│   ├── air_quality.py            # 流汗指數／油煙敏感度
│   ├── crowd_estimation.py       # 人潮預測
│   ├── dialog_analysis.py        # GPT 對話理解
│   ├── feedback_learning.py      # 使用者回饋學習
│   ├── google_maps.py            # Google Places 搜尋與詳情
│   ├── menu_extraction.py        # 菜單 OCR／分類
│   ├── recommendation_engine.py  # 推薦排序（rule-based／ML）
│   ├── review_analysis.py        # Google 評論 NLP
│   └── weather.py                # 中央氣象署天氣查詢
│
├── main.py                       # FastAPI 入口
├── .env                          # API Key 設定（請參考 .env.example）
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
└── README.md


🧰 技術棧與工具
| 項目     | 技術                          | 說明                    |
| ------ | --------------------------- | --------------------- |
| 語言     | Python 3.10+                | 使用 type hints + async |
| 框架     | FastAPI                     | 高性能後端 REST API        |
| AI 對話  | OpenAI GPT-4o / gpt-4o-mini | 分析使用者意圖與評論情緒          |
| 餐廳搜尋   | Google Places API           | 餐廳位置、評論、照片            |
| 天氣資料   | 中央氣象局 API                   | 取得實時天氣資料              |
| OCR    | PaddleOCR / Tesseract       | 菜單圖片文字辨識              |
| DB 儲存  | PostgreSQL / Supabase       | 儲存回饋與偏好               |
| 前端（可選） | React / Flutter             | 可選配合的前端介面             |

🔗 API 路徑一覽
| 功能     | 路徑                             | 方法   |
| ------ | ------------------------------ | ---- |
| 智慧推薦   | /recommend                     | POST |
| 餐廳搜尋   | /restaurants/search            | GET  |
| 天氣查詢   | /weather                       | GET  |
| 流汗指數   | /api/sweat-index               | POST |
| 餐廳推薦   | /api/restaurant-recommendation | POST |
| 人潮分析   | /crowd/analysis                | GET  |
| 安靜餐廳   | /crowd/quiet-restaurants       | GET  |
| 對話查詢分析 | /analyze/query                 | POST |

 🔑 API 金鑰需求（填入 .env）
 ```env
OPENAI_API_KEY=sk-xxx
CWB_API_KEY=CWB-xxx
```

### 天氣模組更新

#### 使用方式

1. 確保 `.env` 檔案中已設定 `CWB_API_KEY` 環境變數。

2. 呼叫 `get_weather_data(latitude, longitude)` 函數，傳入經緯度參數。

3. 函數將返回包含氣溫、濕度與降雨機率的天氣資料。

#### API 整合

- **API 提供者**: 中央氣象署

- **API URL**: `https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001`

- **參數**:

  - `Authorization`: API 金鑰

  - `elementName`: 查詢的天氣元素（如 TEMP, HUMD, RAIN）

  - `parameterName`: 經緯度參數（LAT, LON）

#### 注意事項

- 測試環境中已禁用 SSL 驗證，生產環境建議啟用。

- 若 API 回應資料過多，需根據經緯度篩選最近的氣象站資料。
