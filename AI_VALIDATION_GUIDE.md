# AI驗證模組使用指南

## 概述

AI驗證模組是AI午餐推薦系統的核心品質保證功能，用於檢驗輸入資訊與回答的相關性，確保系統能夠正確理解使用者需求並提供合適的推薦。

## 主要功能

### 1. 地標關鍵字驗證
- **功能**：檢查從使用者輸入中提取的位置資訊是否正確
- **驗證項目**：
  - 位置是否可以通過地理編碼解析
  - 座標格式是否正確
  - 地址與使用者意圖的相關性
- **使用場景**：當使用者輸入「我在台北101附近」時，系統會驗證「台北101」是否正確提取

### 2. 搜尋計畫意圖匹配
- **功能**：檢查生成的搜尋關鍵字是否貼近使用者意圖
- **驗證項目**：
  - 關鍵字與使用者需求的相關性
  - 是否遺漏重要的需求面向
  - 搜尋策略的合理性
- **使用場景**：當使用者說「想吃清爽的食物」時，系統會檢查是否誤用了「火鍋、燒烤」等熱食關鍵字

### 3. 餐廳推薦品質驗證
- **功能**：評估最終推薦結果是否滿足使用者需求
- **驗證項目**：
  - 推薦餐廳的多樣性
  - 關鍵字覆蓋率
  - 距離分布合理性
  - 整體滿意度評估
- **使用場景**：確保推薦的餐廳類型豐富且符合距離要求

## 安裝配置

### 1. 安裝依賴套件
```bash
# 已包含在 requirements.txt 中
pip install geopy openai
```

### 2. 設置環境變數
```bash
# 設置 OpenAI API 金鑰（可選，但建議設置以獲得完整功能）
export OPENAI_API_KEY=你的OpenAI_API金鑰
```

### 3. 驗證安裝
```bash
python test_ai_validation.py
```

## API 使用方式

### 獨立使用驗證功能

```python
from modules.ai_validator import validate_location, validate_search_plan, validate_recommendations

# 1. 位置驗證
result = validate_location(
    user_input="我在台北101附近",
    extracted_location="台北101"
)
print(f"位置有效性：{result['is_valid']}")
print(f"信心度：{result['confidence']}")

# 2. 搜尋計畫驗證
plan_data = {
    "search_keywords": ["火鍋", "麻辣鍋"],
    "location": "台北101",
    "max_distance_km": 2.0
}
result = validate_search_plan(
    user_input="我想吃火鍋",
    search_plan=plan_data
)
print(f"計畫相關性：{result['is_relevant']}")

# 3. 推薦品質驗證
restaurants = [
    {"name": "老四川", "food_type": "火鍋", "distance_km": "0.8"},
    {"name": "鼎王", "food_type": "火鍋", "distance_km": "1.2"}
]
result = validate_recommendations(
    user_input="我想吃火鍋",
    search_keywords=["火鍋"],
    restaurants=restaurants
)
print(f"推薦滿意度：{result['is_satisfactory']}")
```

### 整合在推薦系統中使用

驗證功能已自動整合到主要的推薦API中：

```python
# 調用推薦API時會自動執行驗證
recommendation_result = ai_engine.generate_recommendation(
    location="台北101",
    user_input="我想吃清爽的食物",
    max_results=10
)

# 查看驗證結果
validation_results = recommendation_result.get('validation_results', {})
location_validation = validation_results.get('location_validation', {})
plan_validation = validation_results.get('plan_validation', {})
recommendation_validation = validation_results.get('recommendation_validation', {})
```

## 驗證結果解讀

### 位置驗證結果
```json
{
  "is_valid": true,
  "confidence": 0.85,
  "location_type": "geocoded",
  "coordinates": [25.033, 121.565],
  "formatted_address": "台北市信義區信義路五段7號",
  "issues": [],
  "suggestions": []
}
```

### 搜尋計畫驗證結果
```json
{
  "is_relevant": true,
  "relevance_score": 0.78,
  "intent_match": true,
  "matched_aspects": ["食物類型偏好", "地理位置"],
  "missing_aspects": [],
  "suggestions": []
}
```

### 推薦品質驗證結果
```json
{
  "is_satisfactory": true,
  "quality_score": 0.82,
  "diversity_score": 0.67,
  "coverage_analysis": {
    "火鍋": {"count": 2, "percentage": 0.67},
    "川菜": {"count": 1, "percentage": 0.33}
  },
  "distance_analysis": {
    "min_distance": 0.5,
    "max_distance": 2.1,
    "avg_distance": 1.2
  }
}
```

## 品質閾值說明

- **位置驗證信心度**：>= 0.3 視為可接受，>= 0.8 視為高信心度
- **計畫相關性分數**：>= 0.6 視為相關，>= 0.8 視為高度相關
- **推薦品質分數**：>= 0.7 視為滿意，>= 0.9 視為優秀

## 日誌監控

系統會自動記錄驗證過程中的警告和建議：

```
位置驗證結果：valid=True, confidence=0.85
搜尋計畫驗證結果：relevant=True, score=0.78
餐廳推薦驗證結果：satisfactory=True, score=0.82
```

當發現問題時會輸出警告：
```
⚠️ API警告 - 位置驗證問題：['無法透過地理編碼找到該位置']
⚠️ API警告 - 計畫相關性問題：['遺漏了使用者的預算需求']
⚠️ API警告 - 推薦品質問題：['推薦類型單一，缺乏多樣性']
```

## 最佳實務

1. **定期檢查驗證日誌**：監控系統是否正確理解使用者需求
2. **調整閾值參數**：根據實際使用情況微調品質標準
3. **收集使用者回饋**：結合驗證結果與使用者滿意度進行系統優化
4. **設置 OpenAI API**：雖然不是必須，但會大幅提升驗證準確度

## 故障排除

### 常見問題

1. **OpenAI API 未設置**
   - 症狀：某些AI功能無法使用
   - 解決：設置 OPENAI_API_KEY 環境變數

2. **地理編碼失敗**
   - 症狀：位置驗證總是失敗
   - 解決：檢查網路連線，確認地址格式正確

3. **編碼問題**
   - 症狀：在Windows控制台看到亂碼
   - 解決：已移除emoji字符，應該正常顯示

## 更新記錄

- v1.0: 初始版本，包含三大驗證功能
- 整合到推薦系統主要API端點
- 修正Windows平台編碼兼容性問題