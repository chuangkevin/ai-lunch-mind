# modules/ai_recommendation_engine.py
from datetime import datetime
from modules.sweat_index import query_sweat_index_by_location
from modules.google_maps import search_restaurants
from modules.dialog_analysis import (
    analyze_user_request, 
    extract_search_keywords_from_analysis,
    detect_food_keywords_fallback,
    get_weather_based_keywords
)

class SmartRecommendationEngine:
    def generate_recommendation(self, location, user_input="", max_results=10):
        try:
            print(f"🤖 開始 AI 推薦流程")
            print(f"📍 位置：{location}")
            print(f"💬 用戶輸入：{user_input}")
            
            # 1. 獲取天氣資料
            print(f"🌡️ 正在獲取天氣資料...")
            sweat_data = query_sweat_index_by_location(location)
            sweat_index = sweat_data.get('sweat_index', 50)
            temperature = sweat_data.get('temperature', 25)
            
            # 確保數值類型正確
            try:
                sweat_index = float(sweat_index) if sweat_index is not None else 50
                temperature = float(temperature) if temperature is not None else 25
            except (ValueError, TypeError):
                sweat_index = 50
                temperature = 25
            
            # 2. 選擇搜尋關鍵字（按您的要求：無冰品、沙拉，有熱炒、臭豆腐）
            # 直接取得 AI 分析結果
            analysis_result = analyze_user_request(user_input)
            search_keywords = []
            if analysis_result.get("success"):
                food_prefs = analysis_result["analysis"].get("food_preferences", {})
                categories = food_prefs.get("categories", [])
                keywords = food_prefs.get("keywords", [])
                print(f"🎯 AI分析分類：{', '.join(categories)}")
                print(f"🎯 AI分析細項：{', '.join(keywords)}")
                # 優先用 keywords（如拉麵），只有 keywords 為空才用 categories
                if keywords:
                    search_keywords = keywords[:3]
                elif categories:
                    search_keywords = categories[:3]
            else:
                print(f"⚠️ AI分析失敗，使用預設關鍵字")
                search_keywords = self._get_search_keywords(user_input, sweat_index, temperature)
            print(f"🔍 本次搜尋關鍵字：{', '.join(search_keywords)}")
            
            # 3. 先回傳搜尋計劃給用戶
            search_plan = self._generate_search_plan(location, sweat_data, search_keywords, user_input)
            print(f"� 搜尋計劃：\n{search_plan}")
            
            # 先返回搜尋計劃，讓前端立即顯示
            plan_response = {
                "phase": "search_plan",
                "success": True,
                "location": location,
                "user_input": user_input,
                "weather_info": sweat_data,
                "search_plan": search_plan,
                "search_keywords": search_keywords,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # TODO: 這裡應該有機制讓前端先顯示計劃，然後再繼續搜尋
            # 現在暫時直接繼續執行搜尋
            
            # 4. 開始實際搜尋餐廳（混搭多種類型）
            print(f"🔍 開始搜尋餐廳...")
            print(f"🔍 搜尋策略：混搭多種餐點類型")
            
            all_restaurants = []
            
            # 搜尋多個關鍵字類型，每種類型限制數量
            search_limit_per_type = max(2, max_results // len(search_keywords))
            
            for i, keyword in enumerate(search_keywords[:3], 1):  # 限制前3種類型避免太慢
                print(f"� [{i}/{min(3, len(search_keywords))}] 搜尋「{keyword}」相關餐廳...")
                
                try:
                    restaurants = search_restaurants(
                        keyword=keyword,
                        user_address=location,
                        max_results=search_limit_per_type
                    )
                    
                    if restaurants:
                        print(f"   ✅ 找到 {len(restaurants)} 家「{keyword}」餐廳")
                        # 為每家餐廳添加類型標籤
                        for rest in restaurants:
                            rest['food_type'] = keyword
                        all_restaurants.extend(restaurants)
                    else:
                        print(f"   ⚠️ 「{keyword}」搜尋無結果")
                        
                except Exception as e:
                    print(f"   ❌ 搜尋「{keyword}」時發生錯誤: {e}")
            
            # 5. 依距離升冪排序（近距離優先）
            print(f"📊 正在依距離排序...")
            def get_distance_score(restaurant):
                distance = restaurant.get('distance_km')
                if distance is None or distance == 'N/A':
                    return 999999  # 沒有距離資訊的排在最後
                try:
                    return float(distance)
                except (ValueError, TypeError):
                    return 999999
            
            all_restaurants.sort(key=get_distance_score, reverse=False)
            
            # 限制最終結果數量
            restaurants = all_restaurants[:max_results]
            
            print(f"✅ 搜尋完成，找到 {len(all_restaurants)} 家餐廳，顯示前 {len(restaurants)} 家（依距離排序）")
            
            # 6. 為找到的餐廳逐一輸出詳細資訊（依距離排序）
            if restaurants:
                print(f"📋 推薦餐廳列表（依距離升冪排序）：")
                for i, restaurant in enumerate(restaurants, 1):
                    name = restaurant.get('name', '未知餐廳')
                    address = restaurant.get('address', '地址未提供')
                    distance = restaurant.get('distance_km', 'N/A')
                    rating = restaurant.get('rating', 'N/A')
                    price_level = restaurant.get('price_level', None)
                    food_type = restaurant.get('food_type', '未分類')
                    print(f"  {i}. 🍽️ {name} [{food_type}]")
                    print(f"     📍 {address}")
                    if distance != 'N/A':
                        print(f"     📏 距離: {distance} 公里")
                    if rating != 'N/A':
                        print(f"     ⭐ 評分: {rating}")
                    if price_level:
                        print(f"     💰 預算: {price_level}")
                    print()
            
            # 7. 生成推薦摘要（包含混搭資訊）
            if restaurants:
                # 統計各類型餐廳數量
                type_counts = {}
                for rest in restaurants:
                    food_type = rest.get('food_type', '未分類')
                    type_counts[food_type] = type_counts.get(food_type, 0) + 1
                
                type_summary = ', '.join([f"{t}({c}家)" for t, c in type_counts.items()])
                recommendation_summary = f"根據目前天氣狀況（{temperature}°C，流汗指數{sweat_index}），為您推薦{len(restaurants)}家餐廳，混搭多種類型：{type_summary}。已依距離升冪排序，近距離餐廳優先推薦。"
            else:
                recommendation_summary = "很抱歉，在指定範圍內沒有找到符合條件的餐廳。建議您：1) 擴大搜尋範圍 2) 嘗試其他關鍵字 3) 檢查位置是否正確"
            
            return {
                "success": True,
                "location": location,
                "user_input": user_input,
                "weather_info": sweat_data,
                "search_keywords": search_keywords,
                "restaurants": restaurants,
                "total_found": len(restaurants),
                "recommendation_summary": recommendation_summary,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
        except Exception as e:
            print(f"❌ 推薦過程發生錯誤：{e}")
            return {
                "success": False,
                "error": str(e),
                "location": location,
                "user_input": user_input,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def _get_time_based_keywords(self, current_hour):
        """根據當前時間推薦相應的餐點類型"""
        # 定義時間區間和對應的餐點推薦
        if 6 <= current_hour <= 9:
            # 早餐時間 (6:00-9:00)
            return ["早餐", "三明治", "蛋餅"]
        elif 10 <= current_hour <= 11:
            # 早午餐時間 (10:00-11:00)  
            return ["早午餐", "咖啡", "輕食"]
        elif 12 <= current_hour <= 14:
            # 午餐時間 (12:00-14:00)
            return ["便當", "麵食", "定食"]
        elif 15 <= current_hour <= 17:
            # 下午茶時間 (15:00-17:00)
            return ["甜點", "咖啡", "小食"]
        elif 18 <= current_hour <= 21:
            # 晚餐時間 (18:00-21:00)
            return ["熱炒", "火鍋", "居酒屋"]
        elif 22 <= current_hour <= 23 or 0 <= current_hour <= 2:
            # 宵夜時間 (22:00-02:00)
            return ["小吃", "燒烤", "泡麵"]
        else:
            # 其他時間返回空，讓系統使用天氣推薦
            return []
    
    def _get_meal_time_description(self, current_hour):
        """根據時間返回餐期描述"""
        if 6 <= current_hour <= 9:
            return "早餐時段"
        elif 10 <= current_hour <= 11:
            return "早午餐時段"
        elif 12 <= current_hour <= 14:
            return "午餐時段"
        elif 15 <= current_hour <= 17:
            return "下午茶時段"
        elif 18 <= current_hour <= 21:
            return "晚餐時段"
        elif 22 <= current_hour <= 23 or 0 <= current_hour <= 2:
            return "宵夜時段"
        else:
            return "非用餐時段"
    
    def _get_search_keywords(self, user_input, sweat_index, temperature):
        """使用 ChatGPT 進行智能語意分析，決定搜尋關鍵字"""
        user_lower = user_input.lower()
        
        # 確保數值類型正確
        try:
            sweat_index = float(sweat_index) if sweat_index is not None else 50
            temperature = float(temperature) if temperature is not None else 25
        except (ValueError, TypeError):
            sweat_index = 50
            temperature = 25

        # 獲取當前時間並判斷餐點類型
        current_hour = datetime.now().hour
        time_based_keywords = self._get_time_based_keywords(current_hour)
        
        print(f"🧠 使用 ChatGPT 分析用戶需求...")
        
        # 使用 ChatGPT 進行深度分析
        try:
            analysis_result = analyze_user_request(user_input)
            
            if analysis_result.get("success"):
                # ChatGPT 分析成功
                analysis = analysis_result["analysis"]
                print(f"✅ ChatGPT 分析成功")
                
                # 優先檢查是否有特定食物關鍵字（如：東山鴨頭、鹽酥雞等）
                food_prefs = analysis.get("food_preferences", {})
                keywords = food_prefs.get("keywords", [])
                
                # 特殊處理：將食物名稱轉換為搜尋關鍵字
                special_food_mapping = {
                    "東山鴨頭": ["鴨頭", "滷味", "小吃"],
                    "鹽酥雞": ["鹽酥雞", "炸物", "小吃"],
                    "雞排": ["雞排", "炸雞", "小吃"],
                    "蚵仔煎": ["蚵仔煎", "夜市小吃", "台式料理"],
                    "臭豆腐": ["臭豆腐", "小吃"],
                    "牛肉麵": ["牛肉麵", "麵食"],
                    "滷肉飯": ["滷肉飯", "便當", "台式料理"]
                }
                
                # 檢查關鍵字中是否有特殊食物
                for keyword in keywords:
                    if keyword in special_food_mapping:
                        mapped_keywords = special_food_mapping[keyword]
                        print(f"🎯 檢測到特定食物：{keyword} → 搜尋關鍵字：{', '.join(mapped_keywords)}")
                        return mapped_keywords
                
                # 提取食物類型偏好
                food_categories = analysis.get("food_preferences", {}).get("categories", [])
                if food_categories:
                    print(f"🎯 檢測到用戶明確需求：{', '.join(food_categories)}")
                    return food_categories[:3]  # 限制最多3個類型
                
                # 如果有關鍵字但不在特殊映射中，直接使用關鍵字
                if keywords:
                    print(f"🎯 檢測到食物關鍵字：{', '.join(keywords)}")
                    return keywords[:3]
                
                # 根據情境分析
                mood_context = analysis.get("food_preferences", {}).get("mood_context", "")
                if mood_context:
                    print(f"💭 分析用戶情境：{mood_context}")
                    if "熱" in mood_context and ("想吃" in mood_context or "冰" in mood_context):
                        return ["冰品", "甜點", "涼麵"]
                    elif "冷" in mood_context:
                        return ["火鍋", "熱炒", "湯品"]
            
            else:
                # ChatGPT 分析失敗，使用備用分析
                print(f"⚠️ ChatGPT 分析失敗，使用備用方法")
                fallback = analysis_result.get("fallback_analysis", {})
                food_categories = fallback.get("food_preferences", {}).get("categories", [])
                if food_categories:
                    print(f"🎯 備用分析檢測到：{', '.join(food_categories)}")
                    return food_categories[:3]
                    
        except Exception as e:
            print(f"❌ 對話分析錯誤: {e}")
        
        # 如果所有分析都失敗，使用時間推薦或天氣推薦
        print(f"🤖 使用預設邏輯根據時間和天氣推薦")
        
        # 簡單關鍵字檢測（備用方案）
        detected_keywords = detect_food_keywords_fallback(user_input)
        
        if detected_keywords:
            print(f"🎯 關鍵字檢測到：{', '.join(detected_keywords)}")
            return detected_keywords
        
        # 優先使用時間推薦，如果時間推薦為空則使用天氣推薦
        if time_based_keywords:
            print(f"⏰ 根據時間推薦：{', '.join(time_based_keywords)}")
            return time_based_keywords
        
        # 根據天氣決定預設關鍵字
        weather_keywords = get_weather_based_keywords(sweat_index, temperature)
        print(f"🌤️ 根據天氣推薦：{', '.join(weather_keywords)}")
        return weather_keywords
    
    def _generate_search_plan(self, location, sweat_data, search_keywords, user_input):
        """
        生成詳細的搜尋計劃說明
        """
        plan_parts = []
        
        # 位置資訊
        plan_parts.append(f"📍 搜尋位置：{location}")
        
        # 時間資訊
        current_hour = datetime.now().hour
        current_time = datetime.now().strftime("%H:%M")
        meal_time = self._get_meal_time_description(current_hour)
        plan_parts.append(f"⏰ 當前時間：{current_time} ({meal_time})")
        
        # 天氣和流汗指數資訊
        temperature = sweat_data.get('temperature', '未知')
        heat_index = sweat_data.get('heat_index', '未知')
        sweat_index = sweat_data.get('sweat_index', 0)
        comfort_level = sweat_data.get('comfort_level', {}).get('level', '未知')
        
        # 確保數值類型正確以供比較
        try:
            sweat_index_num = float(sweat_index) if sweat_index != '未知' else 0
        except (ValueError, TypeError):
            sweat_index_num = 0
        
        plan_parts.append(f"🌡️ 目前氣溫：{temperature}°C")
        # 只有當體感溫度與實際溫度不同時才顯示
        if heat_index != '未知' and heat_index != temperature:
            plan_parts.append(f"🌡️ 體感溫度：{heat_index}°C")
        plan_parts.append(f"💧 流汗指數：{sweat_index}/10 ({comfort_level})")
        
        # 推薦邏輯說明
        if sweat_index_num > 6:
            plan_parts.append("🧊 天氣較熱，會優先推薦清爽餐點")
        elif temperature != '未知':
            try:
                temp_num = float(temperature)
                if temp_num < 20:
                    plan_parts.append("🔥 天氣較冷，會優先推薦溫熱餐點")
                else:
                    plan_parts.append("😊 天氣適中，將推薦多元化餐點")
            except (ValueError, TypeError):
                plan_parts.append("😊 天氣適中，將推薦多元化餐點")
        else:
            plan_parts.append("😊 天氣適中，將推薦多元化餐點")
        
        # 搜尋策略
        plan_parts.append(f"🔍 搜尋關鍵字：{', '.join(search_keywords)}")
        plan_parts.append(f"📝 搜尋策略：混搭多種餐點類型，每種類型搜尋優質餐廳")
        plan_parts.append(f"📊 排序方式：依距離升冪排序（近距離優先）")
        
        # ChatGPT 智能需求分析（取代舊的機械式分析）
        try:
            analysis_result = analyze_user_request(user_input)
            if analysis_result.get("success"):
                analysis = analysis_result["analysis"]
                food_prefs = analysis.get("food_preferences", {})
                
                # 顯示檢測到的食物偏好
                if food_prefs.get("categories"):
                    categories_str = ", ".join(food_prefs["categories"])
                    plan_parts.append(f"🎯 AI 分析檢測到需求：{categories_str}")
                
                # 顯示情境分析
                if food_prefs.get("mood_context"):
                    plan_parts.append(f"💭 情境理解：{food_prefs['mood_context']}")
                
                # 顯示預算偏好
                budget_info = analysis.get("budget")
                if budget_info and budget_info.get("range"):
                    plan_parts.append(f"💰 預算考量：{budget_info['range']}")
                    
            else:
                plan_parts.append("🎯 將為您推薦多種類型的優質餐廳")
                
        except Exception as e:
            print(f"⚠️ 需求分析顯示錯誤: {e}")
            plan_parts.append("🎯 將為您推薦多種類型的優質餐廳")
        
        return '\n'.join(plan_parts)
    
    def _generate_search_plan_with_location_info(self, location, sweat_data, search_keywords, user_input, location_info=None):
        """
        生成詳細的搜尋計劃說明（包含位置資訊顯示）
        """
        plan_parts = []
        
        # 位置資訊 - 優先顯示地標名稱
        if location_info and len(location_info) >= 3:
            place_name = location_info[2]  # 地標名稱
            coordinates = f"{location_info[0]},{location_info[1]}"  # 座標
            plan_parts.append(f"📍 搜尋位置：{place_name}")
            plan_parts.append(f"🌍 座標：{coordinates}")
        else:
            plan_parts.append(f"📍 搜尋位置：{location}")
        
        # 時間資訊
        current_hour = datetime.now().hour
        current_time = datetime.now().strftime("%H:%M")
        meal_time = self._get_meal_time_description(current_hour)
        plan_parts.append(f"⏰ 當前時間：{current_time} ({meal_time})")
        
        # 天氣和流汗指數資訊
        temperature = sweat_data.get('temperature', '未知')
        heat_index = sweat_data.get('heat_index', '未知')
        sweat_index = sweat_data.get('sweat_index', 0)
        comfort_level = sweat_data.get('comfort_level', {}).get('level', '未知')
        
        # 確保數值類型正確以供比較
        try:
            sweat_index_num = float(sweat_index) if sweat_index != '未知' else 0
        except (ValueError, TypeError):
            sweat_index_num = 0
        
        plan_parts.append(f"🌡️ 目前氣溫：{temperature}°C")
        # 只有當體感溫度與實際溫度不同時才顯示
        if heat_index != '未知' and heat_index != temperature:
            plan_parts.append(f"🌡️ 體感溫度：{heat_index}°C")
        plan_parts.append(f"💧 流汗指數：{sweat_index}/10 ({comfort_level})")
        
        # 推薦邏輯說明
        if sweat_index_num > 6:
            plan_parts.append("🧊 天氣較熱，會優先推薦清爽餐點")
        elif temperature != '未知':
            try:
                temp_num = float(temperature)
                if temp_num < 20:
                    plan_parts.append("🔥 天氣較冷，會優先推薦溫熱餐點")
                else:
                    plan_parts.append("😊 天氣適中，將推薦多元化餐點")
            except (ValueError, TypeError):
                plan_parts.append("😊 天氣適中，將推薦多元化餐點")
        else:
            plan_parts.append("😊 天氣適中，將推薦多元化餐點")
        
        # 搜尋策略
        plan_parts.append(f"🔍 搜尋關鍵字：{', '.join(search_keywords)}")
        plan_parts.append(f"📝 搜尋策略：混搭多種餐點類型，每種類型搜尋優質餐廳")
        plan_parts.append(f"📊 排序方式：依距離升冪排序（近距離優先）")
        
        # ChatGPT 智能需求分析（取代舊的機械式分析）
        try:
            analysis_result = analyze_user_request(user_input)
            if analysis_result.get("success"):
                analysis = analysis_result["analysis"]
                food_prefs = analysis.get("food_preferences", {})
                
                # 顯示檢測到的食物偏好
                if food_prefs.get("categories"):
                    categories_str = ", ".join(food_prefs["categories"])
                    plan_parts.append(f"🎯 AI 分析檢測到需求：{categories_str}")
                
                # 顯示情境分析
                if food_prefs.get("mood_context"):
                    plan_parts.append(f"💭 情境理解：{food_prefs['mood_context']}")
                
                # 顯示預算偏好
                budget_info = analysis.get("budget")
                if budget_info and budget_info.get("range"):
                    plan_parts.append(f"💰 預算考量：{budget_info['range']}")
                    
            else:
                plan_parts.append("🎯 將為您推薦多種類型的優質餐廳")
                
        except Exception as e:
            print(f"⚠️ 需求分析顯示錯誤: {e}")
            plan_parts.append("🎯 將為您推薦多種類型的優質餐廳")
        
        return '\n'.join(plan_parts)
    
    def process_conversation(self, message, phase="start"):
        """
        處理對話式推薦請求，支援分階段執行
        :param message: 使用者完整訊息
        :param phase: 執行階段 ("start", "search")
        :return: 推薦結果
        """
        try:
            print(f"🗣️ 處理對話（階段：{phase}）：{message}")
            
            # 從訊息中提取位置資訊
            location = self._extract_location_from_message(message)
            location_info = None  # 儲存額外的位置資訊（如地標名稱）
            
            # 如果是 Google Maps URL，取得詳細地標資訊
            if 'maps.app.goo.gl' in message or 'g.co/kgs/' in message or 'goo.gl' in message:
                try:
                    import re
                    url_pattern = r'https?://[^\s]+'
                    urls = re.findall(url_pattern, message)
                    if urls:
                        from modules.google_maps import extract_location_from_url
                        result = extract_location_from_url(urls[0])
                        if result and isinstance(result, tuple) and len(result) >= 3:
                            location_info = result  # (lat, lng, place_name)
                            location = f"{result[0]},{result[1]}"  # 使用座標格式作為 location
                            print(f"🌍 解析到地標：{result[2]} 座標：{result[0]},{result[1]}")
                except Exception as e:
                    print(f"❌ 地標解析失敗: {e}")
            
            if not location:
                return {
                    "success": False,
                    "error": "無法從訊息中識別位置資訊，請提供更明確的地址或地標。",
                    "message": message,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

            if phase == "start":
                # 第一階段：只回傳搜尋計劃
                print(f"📋 第一階段：生成搜尋計劃")
                
                # 獲取天氣資料
                sweat_data = query_sweat_index_by_location(location)
                sweat_index = sweat_data.get('sweat_index', 50)
                temperature = sweat_data.get('temperature', 25)
                
                # 確保數值類型正確
                try:
                    sweat_index = float(sweat_index) if sweat_index is not None else 50
                    temperature = float(temperature) if temperature is not None else 25
                except (ValueError, TypeError):
                    sweat_index = 50
                    temperature = 25
                
                # 選擇搜尋關鍵字
                search_keywords = self._get_search_keywords(message, sweat_index, temperature)
                
                # 生成搜尋計劃（傳遞位置資訊）
                search_plan = self._generate_search_plan_with_location_info(location, sweat_data, search_keywords, message, location_info)
                
                return {
                    "phase": "plan",
                    "success": True,
                    "location": location,
                    "location_info": location_info,
                    "user_input": message,
                    "weather_info": sweat_data,
                    "search_plan": search_plan,
                    "search_keywords": search_keywords,
                    "message": "搜尋計劃已生成，準備開始搜尋餐廳...",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            
            elif phase == "search":
                # 第二階段：執行實際搜尋
                print(f"🔍 第二階段：執行餐廳搜尋")
                return self.generate_recommendation(location, message, max_results=8)
            
            else:
                # 一次性執行（舊版本兼容）
                return self.generate_recommendation(location, message, max_results=8)
            
        except Exception as e:
            print(f"❌ 對話處理錯誤：{e}")
            return {
                "success": False,
                "error": str(e),
                "message": message,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def _extract_location_from_message(self, message):
        """
        使用 ChatGPT + 傳統方法提取位置資訊
        支援 Google Maps 短網址和地標名稱
        """
        print(f"🧠 使用 ChatGPT 分析位置資訊...")
        
        # 首先使用 ChatGPT 分析
        try:
            analysis_result = analyze_user_request(message)
            
            if analysis_result.get("success"):
                location_data = analysis_result["analysis"].get("location", {})
                
                # 優先處理 Google Maps URL
                if location_data.get("google_maps_url"):
                    url = location_data["google_maps_url"]
                    print(f"🗺️ ChatGPT 檢測到 Google Maps URL: {url}")
                    
                    try:
                        from modules.google_maps import extract_location_from_url
                        location_result = extract_location_from_url(url)
                        if location_result and isinstance(location_result, tuple) and len(location_result) >= 3:
                            lat, lng, place_name = location_result
                            location_str = f"{lat},{lng}"
                            print(f"✅ Google Maps URL 解析成功: {place_name} ({location_str})")
                            return location_str
                    except Exception as e:
                        print(f"❌ Google Maps URL 解析失敗: {e}")
                
                # 處理座標
                if location_data.get("coordinates"):
                    coords = location_data["coordinates"]
                    print(f"📍 ChatGPT 檢測到座標: {coords}")
                    return coords
                
                # 處理地址/地點名稱
                if location_data.get("address"):
                    address = location_data["address"]
                    print(f"🏠 ChatGPT 檢測到地址: {address}")
                    return address
            
            else:
                # 使用備用分析
                fallback = analysis_result.get("fallback_analysis", {})
                location_data = fallback.get("location")
                if location_data:
                    if location_data.get("google_maps_url"):
                        return self._process_google_maps_url(location_data["google_maps_url"])
                    elif location_data.get("address"):
                        return location_data["address"]
                        
        except Exception as e:
            print(f"❌ ChatGPT 位置分析錯誤: {e}")
        
        # 傳統方法備用
        print(f"🔍 使用傳統方法分析位置...")
        
        # 檢查是否包含 Google Maps 短網址
        if 'maps.app.goo.gl' in message or 'g.co/kgs/' in message or 'goo.gl' in message:
            import re
            url_pattern = r'https?://[^\s]+'
            urls = re.findall(url_pattern, message)
            if urls:
                return self._process_google_maps_url(urls[0])
        
        # 提取地標或地址
        location_patterns = [
            r'(?:我在|在)([^，。！？\s]+)',
            r'([^，。！？\s]*(?:區|站|路|街|市|縣|101|大樓|商場|夜市))',
            r'(台北\w+|高雄\w+|台中\w+|台南\w+)',
        ]
        
        for pattern in location_patterns:
            import re
            matches = re.findall(pattern, message)
            if matches:
                return matches[0].strip()
        
        return None
    
    def _process_google_maps_url(self, url):
        """處理 Google Maps URL"""
        try:
            from modules.google_maps import extract_location_from_url
            location_result = extract_location_from_url(url)
            if location_result:
                if isinstance(location_result, tuple) and len(location_result) >= 3:
                    lat, lng, place_name = location_result
                    location_str = f"{lat},{lng}"
                    print(f"🌍 Google Maps URL 解析到位置: {place_name} ({location_str})")
                    return location_str
                else:
                    print(f"⚠️ Google Maps URL 解析結果格式異常: {location_result}")
        except Exception as e:
            print(f"❌ Google Maps URL 解析失敗: {e}")
        
        # 如果解析失敗，返回原始 URL
        return url

recommendation_engine = SmartRecommendationEngine()

def get_ai_lunch_recommendation(location, user_input="", max_results=10):
    return recommendation_engine.generate_recommendation(location, user_input, max_results)