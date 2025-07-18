請根據 modules 中每一個檔案，建立獨立 API 路由，並在 main.py 中整合。優先完成：
1. dialog_analysis.py：接收使用者輸入文字，回傳分析後的條件 JSON。
2. weather.py：根據經緯度，自動選擇中央氣象局最近的氣象站，回傳氣溫、濕度、降雨。
3. google_maps.py：根據流汗指數，搜尋 500~2000 公尺內的餐廳並擷取資訊。
4. recommendation_engine.py：整合所有資訊並排序推薦結果。
