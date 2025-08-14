# modules/ai_recommendation_engine.py
from datetime import datetime
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import asyncio
from typing import List, Dict, Any
from modules.sweat_index import query_sweat_index_by_location
from modules.google_maps import search_restaurants
from modules.dialog_analysis import (
    analyze_user_request, 
    extract_search_keywords_from_analysis,
    detect_food_keywords_fallback,
    get_weather_based_keywords
)
from modules.ai_validator import validate_location, validate_search_plan, validate_recommendations

class SmartRecommendationEngine:
    def generate_recommendation(self, location, user_input="", max_results=10):
        try:
            print(f"🤖 開始 AI 推薦流程")
            print(f"📍 位置：{location}")
            print(f"💬 用戶輸入：{user_input}")
            
            # 並行執行初始化任務
            print(f"⚡ 並行處理位置驗證、天氣資料和對話分析...")
            with ThreadPoolExecutor(max_workers=3) as executor:
                # 提交三個並行任務
                future_location = executor.submit(validate_location, user_input, location)
                future_weather = executor.submit(query_sweat_index_by_location, location)
                future_dialog = executor.submit(analyze_user_request, user_input) if user_input.strip() else None
                
                # 等待結果
                location_validation = future_location.result()
                sweat_data = future_weather.result()
                dialog_analysis = future_dialog.result() if future_dialog else None
            
            print(f"🔍 位置驗證結果：valid={location_validation['is_valid']}, confidence={location_validation['confidence']:.2f}")
            
            if not location_validation['is_valid'] and location_validation['confidence'] < 0.3:
                print(f"⚠️ 位置驗證警告：{location_validation.get('issues', [])}")
                # 不阻斷流程，但記錄問題
            # 使用較合理的預設值（避免過度縮小搜尋半徑）
            sweat_index = sweat_data.get('sweat_index', 5.0)
            temperature = sweat_data.get('temperature', 25)
            
            # 確保數值類型正確
            try:
                sweat_index = float(sweat_index) if sweat_index is not None else 5.0
                temperature = float(temperature) if temperature is not None else 25
            except (ValueError, TypeError):
                sweat_index = 5.0
                temperature = 25
            
            # 1.5. 根據流汗指數計算搜尋距離範圍
            max_distance_km = self._calculate_max_distance_by_sweat_index(sweat_index)
            print(f"📏 根據流汗指數 {sweat_index}/10，設定最大搜尋距離：{max_distance_km}km")
            
            # 2. 選擇搜尋關鍵字（按您的要求：無冰品、沙拉，有熱炒、臭豆腐）
            search_keywords = self._get_search_keywords(user_input, sweat_index, temperature)
            if not search_keywords:
                # 關鍵字為空時的保底
                search_keywords = ["熱炒", "便當", "麵食"]
            
            # 3. 生成搜尋計劃
            search_plan = self._generate_search_plan(location, sweat_data, search_keywords, user_input, max_distance_km)
            print(f"📋 搜尋計劃：\n{search_plan}")
            
            # 3.5. AI驗證：搜尋計畫相關性
            plan_data = {
                "search_keywords": search_keywords,
                "location": location,
                "weather_info": sweat_data,
                "max_distance_km": max_distance_km
            }
            plan_validation = validate_search_plan(user_input, plan_data)
            print(f"搜尋計畫驗證：relevant={plan_validation['is_relevant']}, score={plan_validation['relevance_score']:.2f}")
            
            if not plan_validation['is_relevant']:
                print(f"搜尋計畫可能需要調整：{plan_validation.get('missing_aspects', [])}")
                # 記錄建議但不阻斷流程
                
            # 檢查具體性問題
            specificity_issue = plan_validation.get('specificity_issue', '')
            if specificity_issue and specificity_issue.strip():
                print(f"具體性問題：{specificity_issue}")
                suggested_keywords = plan_validation.get('suggested_keywords', [])
                if suggested_keywords:
                    print(f"建議關鍵字：{', '.join(suggested_keywords)}")
                    # 可選：動態調整搜尋關鍵字
                    if plan_validation.get('intent_score', 0.0) < 0.6:
                        print(f"意圖匹配分數過低 ({plan_validation.get('intent_score', 0.0):.2f})，考慮使用建議關鍵字")
                        # 替換或補充關鍵字
                        search_keywords = suggested_keywords[:3] if len(suggested_keywords) >= 3 else suggested_keywords + search_keywords
                        print(f"調整後搜尋關鍵字：{', '.join(search_keywords)}")
            
            # 先返回搜尋計劃，讓前端立即顯示
            plan_response = {
                "phase": "search_plan",
                "success": True,
                "location": location,
                "user_input": user_input,
                "weather_info": sweat_data,
                "search_plan": search_plan,
                "search_keywords": search_keywords,
                "max_distance_km": max_distance_km,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # TODO: 這裡應該有機制讓前端先顯示計劃，然後再繼續搜尋
            # 現在暫時直接繼續執行搜尋
            
            # 4. 開始實際搜尋餐廳（並行搜尋多種類型）
            print(f"🔍 開始並行搜尋餐廳...")
            print(f"🔍 搜尋策略：並行混搭多種餐點類型，距離限制 {max_distance_km}km")
            
            all_restaurants = []
            
            # 搜尋多個關鍵字類型，每種類型限制數量
            search_limit_per_type = max(2, max_results // len(search_keywords))
            
            # 使用 ThreadPoolExecutor 並行搜尋
            # 視關鍵字數量動態調整 worker，提升搜尋覆蓋率但維持保守上限
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(4, len(search_keywords)))) as executor:
                # 提交搜尋任務
                future_to_keyword = {}
                keywords_to_search = search_keywords[:2]  # 維持前2種類型以控管負載
                
                for keyword in keywords_to_search:
                    future = executor.submit(
                        search_restaurants,
                        keyword=keyword,
                        user_address=location,
                        max_results=search_limit_per_type
                    )
                    future_to_keyword[future] = keyword
                
                print(f"📡 已提交 {len(keywords_to_search)} 個並行搜尋任務")
                
                # 收集結果
                completed_searches = 0
                for future in concurrent.futures.as_completed(future_to_keyword):
                    keyword = future_to_keyword[future]
                    completed_searches += 1
                    
                    try:
                        restaurants = future.result()
                        
                        if restaurants:
                            print(f"   ✅ [{completed_searches}/{len(keywords_to_search)}] 「{keyword}」找到 {len(restaurants)} 家餐廳")
                            # 為每家餐廳添加類型標籤
                            for rest in restaurants:
                                rest['food_type'] = keyword
                            all_restaurants.extend(restaurants)
                        else:
                            print(f"   ⚠️ [{completed_searches}/{len(keywords_to_search)}] 「{keyword}」搜尋無結果")
                            
                    except Exception as e:
                        print(f"   ❌ [{completed_searches}/{len(keywords_to_search)}] 搜尋「{keyword}」時發生錯誤: {e}")
                
                print(f"🎉 並行搜尋完成！總共收集到 {len(all_restaurants)} 家餐廳")
            
            # 若並行搜尋完全無結果，嘗試廣義回補關鍵字
            if not all_restaurants:
                try:
                    fallback_keywords = ["餐廳", "美食"]
                    for fb_kw in fallback_keywords:
                        fb_results = search_restaurants(keyword=fb_kw, user_address=location, max_results=max(3, max_results))
                        if fb_results:
                            for rest in fb_results:
                                rest['food_type'] = fb_kw
                            all_restaurants.extend(fb_results)
                            break
                except Exception as _:
                    pass

            # 4.5. 根據距離限制過濾餐廳
            print(f"📏 正在根據距離限制 {max_distance_km}km 過濾餐廳...")
            filtered_restaurants = self._filter_restaurants_by_distance(all_restaurants, max_distance_km)
            print(f"📊 距離過濾後剩餘 {len(filtered_restaurants)} 家餐廳")
            
            # 4.6. 去除重複餐廳
            print(f"🔄 正在去除重複餐廳...")
            unique_restaurants = self._remove_duplicate_restaurants(filtered_restaurants)
            print(f"📊 去重後剩餘 {len(unique_restaurants)} 家餐廳")
            
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
            
            unique_restaurants.sort(key=get_distance_score, reverse=False)
            
            # 限制最終結果數量
            restaurants = unique_restaurants[:max_results]
            # 如果過濾後還是沒有結果，保底回傳原始結果前幾筆，避免全空
            if not restaurants and all_restaurants:
                restaurants = all_restaurants[:max_results]
            
            print(f"✅ 搜尋完成，找到 {len(all_restaurants)} 家餐廳，距離過濾後 {len(filtered_restaurants)} 家，去重後 {len(unique_restaurants)} 家，顯示前 {len(restaurants)} 家（依距離排序）")
            
            # 5.5. AI驗證：餐廳推薦品質
            recommendation_validation = validate_recommendations(user_input, search_keywords, restaurants)
            print(f"🍽️ 推薦品質驗證：satisfactory={recommendation_validation['is_satisfactory']}, score={recommendation_validation['quality_score']:.2f}")
            
            if not recommendation_validation['is_satisfactory']:
                quality_issues = recommendation_validation.get('issues', [])
                quality_suggestions = recommendation_validation.get('suggestions', [])
                if quality_issues:
                    print(f"⚠️ 推薦品質問題：{quality_issues}")
                if quality_suggestions:
                    print(f"💡 改善建議：{quality_suggestions}")
            
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
                recommendation_summary = f"很抱歉，在{max_distance_km}km範圍內沒有找到符合條件的餐廳。建議您：1) 嘗試其他關鍵字 2) 檢查位置是否正確"
            
            return {
                "success": True,
                "location": location,
                "user_input": user_input,
                "weather_info": sweat_data,
                "search_keywords": search_keywords,
                "max_distance_km": max_distance_km,
                "restaurants": restaurants,
                "total_found": len(restaurants),
                "recommendation_summary": recommendation_summary,
                "validation_results": {
                    "location_validation": location_validation,
                    "plan_validation": plan_validation,
                    "recommendation_validation": recommendation_validation
                },
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
    
    def _calculate_max_distance_by_sweat_index(self, sweat_index):
        """
        根據流汗指數計算合適的搜尋距離範圍
        流汗指數越高，搜尋範圍越小（避免走太遠）
        """
        try:
            sweat_index = float(sweat_index) if sweat_index is not None else 5.0
        except (ValueError, TypeError):
            sweat_index = 5.0
        
        # 放寬半徑，避免過度收斂導致只剩極少數結果
        if sweat_index >= 9:
            return 0.8  # 非常熱，~800m
        elif sweat_index >= 7:
            return 1.5  # 很熱，1.5km
        elif sweat_index >= 5:
            return 2.5  # 偏熱，2.5km
        elif sweat_index >= 3:
            return 3.0  # 適中，3km
        else:
            return 4.0  # 涼爽，4km

    def _filter_restaurants_by_distance(self, restaurants, max_distance_km):
        """
        根據距離限制過濾餐廳
        """
        filtered = []
        unknown_distance = []
        for restaurant in restaurants:
            distance = restaurant.get('distance_km')
            if distance is None or distance == 'N/A':
                # 保留未知距離，避免把潛在好店全丟掉
                unknown_distance.append(restaurant)
                continue

            try:
                distance_float = float(distance)
                if distance_float <= max_distance_km:
                    filtered.append(restaurant)
                else:
                    print(f"   📏 過濾掉距離過遠的餐廳：{restaurant.get('name', 'Unknown')} ({distance}km > {max_distance_km}km)")
            except (ValueError, TypeError):
                unknown_distance.append(restaurant)

        # 若完全沒有符合距離條件，至少回傳未知距離的選項以供使用者參考
        return filtered if filtered else unknown_distance

    def _remove_duplicate_restaurants(self, restaurants):
        """
        根據餐廳名稱和地址去除重複的餐廳
        """
        seen = set()
        unique_restaurants = []
        
        for restaurant in restaurants:
            name = restaurant.get('name', '').strip()
            address = restaurant.get('address', '').strip()
            
            # 創建唯一標識符（名稱+地址前20字元）
            identifier = f"{name}_{address[:20]}"
            
            if identifier not in seen:
                seen.add(identifier)
                unique_restaurants.append(restaurant)
            else:
                print(f"   🔄 發現重複餐廳，已跳過：{name}")
        
        return unique_restaurants
    
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
            sweat_index = float(sweat_index) if sweat_index is not None else 5.0
            temperature = float(temperature) if temperature is not None else 25
        except (ValueError, TypeError):
            sweat_index = 5.0
            temperature = 25

        # 獲取當前時間並判斷餐點類型
        current_hour = datetime.now().hour
        time_based_keywords = self._get_time_based_keywords(current_hour)
        
        print(f"使用 ChatGPT 分析用戶需求...")
        
        # 使用 ChatGPT 進行深度分析
        try:
            analysis_result = analyze_user_request(user_input)
            
            if analysis_result.get("success"):
                # ChatGPT 分析成功
                analysis = analysis_result["analysis"]
                print(f"ChatGPT 分析成功")
                
                # 優先檢查是否有特定食物關鍵字（如：東山鴨頭、鹽酥雞等）
                food_prefs = analysis.get("food_preferences", {})
                keywords = food_prefs.get("keywords", [])
                
                # 特殊處理：將食物名稱轉換為搜尋關鍵字（保持具體性）
                special_food_mapping = {
                    # 麵類 - 保持具體性，優先使用具體名稱
                    "拉麵": ["拉麵", "日式拉麵", "豚骨拉麵"],
                    "牛肉麵": ["牛肉麵", "紅燒牛肉麵", "清燉牛肉麵"],
                    "義大利麵": ["義大利麵", "意麵", "pasta"],
                    "烏龍麵": ["烏龍麵", "日式烏龍", "湯烏龍"],
                    "泡麵": ["泡麵", "即食麵", "速食麵"],
                    "米線": ["米線", "雲南米線", "過橋米線"],
                    "河粉": ["河粉", "炒河粉", "湯河粉"],
                    "陽春麵": ["陽春麵", "白麵", "清湯麵"],
                    "擔仔麵": ["擔仔麵", "台南小吃", "麵食"],
                    
                    # 小吃類
                    "東山鴨頭": ["鴨頭", "滷味", "小吃"],
                    "鹽酥雞": ["鹽酥雞", "炸物", "小吃"],
                    "雞排": ["雞排", "炸雞", "小吃"],
                    "蚵仔煎": ["蚵仔煎", "夜市小吃", "台式料理"],
                    "臭豆腐": ["臭豆腐", "小吃"],
                    "滷肉飯": ["滷肉飯", "便當", "台式料理"],
                    "雞肉飯": ["雞肉飯", "火雞肉飯", "嘉義小吃"],
                    
                    # 火鍋類
                    "麻辣鍋": ["麻辣鍋", "麻辣火鍋", "四川火鍋"],
                    "涮涮鍋": ["涮涮鍋", "清湯火鍋", "個人鍋"],
                    "薑母鴨": ["薑母鴨", "食補", "冬令進補"],
                    "羊肉爐": ["羊肉爐", "食補", "冬令進補"],
                    
                    # 其他具體食物
                    "壽司": ["壽司", "日式料理", "生魚片"],
                    "燒烤": ["燒烤", "烤肉", "BBQ"],
                    "韓式料理": ["韓式料理", "韓國菜", "韓式燒烤"],
                    "泰式料理": ["泰式料理", "泰國菜", "東南亞菜"],
                    "印度料理": ["印度料理", "印度菜", "咖哩"]
                }
                
                # 檢查關鍵字中是否有特殊食物
                for keyword in keywords:
                    if keyword in special_food_mapping:
                        mapped_keywords = special_food_mapping[keyword]
                        print(f"檢測到特定食物：{keyword} → 搜尋關鍵字：{', '.join(mapped_keywords)}")
                        return mapped_keywords
                
                # 後備檢查：直接在使用者輸入中檢查具體食物名稱（防止ChatGPT過度泛化）
                user_input_lower = user_input.lower()
                for specific_food, mapped_keywords in special_food_mapping.items():
                    if specific_food in user_input_lower or specific_food.lower() in user_input_lower:
                        print(f"直接檢測到使用者輸入的具體食物：{specific_food} → 搜尋關鍵字：{', '.join(mapped_keywords)}")
                        return mapped_keywords
                
                # 提取食物類型偏好
                food_categories = analysis.get("food_preferences", {}).get("categories", [])
                if food_categories:
                    print(f"檢測到用戶明確需求：{', '.join(food_categories)}")
                    return food_categories[:3]  # 限制最多3個類型
                
                # 如果有關鍵字但不在特殊映射中，直接使用關鍵字
                if keywords:
                    print(f"檢測到食物關鍵字：{', '.join(keywords)}")
                    return keywords[:3]
                
                # 根據情境分析
                mood_context = analysis.get("food_preferences", {}).get("mood_context", "")
                if mood_context:
                    print(f"分析用戶情境：{mood_context}")
                    if "熱" in mood_context and ("想吃" in mood_context or "冰" in mood_context):
                        return ["冰品", "甜點", "涼麵"]
                    elif "冷" in mood_context:
                        return ["火鍋", "熱炒", "湯品"]
            
            else:
                # ChatGPT 分析失敗，使用備用分析
                print(f"ChatGPT 分析失敗，使用備用方法")
                fallback = analysis_result.get("fallback_analysis", {})
                food_categories = fallback.get("food_preferences", {}).get("categories", [])
                if food_categories:
                    print(f"備用分析檢測到：{', '.join(food_categories)}")
                    return food_categories[:3]
                    
        except Exception as e:
            print(f"對話分析錯誤: {e}")
        
        # 如果所有分析都失敗，使用時間推薦或天氣推薦
        print(f"使用預設邏輯根據時間和天氣推薦")
        
        # 簡單關鍵字檢測（備用方案）
        detected_keywords = detect_food_keywords_fallback(user_input)
        
        if detected_keywords:
            print(f"關鍵字檢測到：{', '.join(detected_keywords)}")
            return detected_keywords
        
        # 優先使用時間推薦，如果時間推薦為空則使用天氣推薦
        if time_based_keywords:
            print(f"根據時間推薦：{', '.join(time_based_keywords)}")
            return time_based_keywords
        
        # 根據天氣決定預設關鍵字
        weather_keywords = get_weather_based_keywords(sweat_index, temperature)
        print(f"根據天氣推薦：{', '.join(weather_keywords)}")
        return weather_keywords
    
    def _generate_search_plan(self, location, sweat_data, search_keywords, user_input, max_distance_km=None):
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
        
        # 顯示距離限制
        if max_distance_km:
            plan_parts.append(f"📏 搜尋距離限制：{max_distance_km}km（根據流汗指數調整）")
        
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
        
        # 計算距離限制
        max_distance_km = self._calculate_max_distance_by_sweat_index(sweat_index)
        
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
        plan_parts.append(f"📏 搜尋距離限制：{max_distance_km}km（根據流汗指數調整）")
        
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