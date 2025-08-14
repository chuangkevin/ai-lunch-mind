# modules/ai_validator.py
"""
AI驗證模組 - 用於檢驗輸入資訊與回答的相關性

主要功能：
1. 驗證地標關鍵字是否正確解析
2. 檢查搜尋計畫是否貼近使用者意圖
3. 驗證餐廳推薦結果是否符合需求
4. 地址/座標驗證
"""

import os
import json
from typing import Dict, List, Any, Optional, Tuple
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import openai


class AIValidator:
    def __init__(self):
        self.client = None
        self.setup_openai_client()
        
    def setup_openai_client(self):
        """設定 OpenAI 客戶端"""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("警告：OPENAI_API_KEY 環境變數未設置，AI驗證功能將無法使用")
                return
            
            self.client = openai.OpenAI(api_key=api_key)
            print("OpenAI 客戶端初始化成功")
        except Exception as e:
            print(f"OpenAI 客戶端初始化失敗: {e}")
            self.client = None
    
    def validate_location_extraction(self, user_input: str, extracted_location: str) -> Dict[str, Any]:
        """
        驗證地標關鍵字提取是否正確
        
        Args:
            user_input: 原始使用者輸入
            extracted_location: 系統提取的位置資訊
            
        Returns:
            驗證結果字典
        """
        try:
            print(f"驗證位置提取：'{extracted_location}' <- '{user_input}'")
            
            validation_result = {
                "is_valid": False,
                "confidence": 0.0,
                "issues": [],
                "suggestions": [],
                "location_type": "unknown",
                "coordinates": None,
                "formatted_address": None
            }
            
            # 1. 基本檢查
            if not extracted_location or extracted_location.strip() == "":
                validation_result["issues"].append("未能提取到有效的位置資訊")
                validation_result["suggestions"].append("請提供更明確的地址、地標或座標")
                return validation_result
            
            # 2. 使用 AI 驗證位置相關性
            if self.client:
                ai_validation = self._ai_validate_location_relevance(user_input, extracted_location)
                validation_result.update(ai_validation)
            
            # 3. 地理編碼驗證
            geo_validation = self._geocode_validation(extracted_location)
            if geo_validation["success"]:
                validation_result["is_valid"] = True
                validation_result["coordinates"] = geo_validation["coordinates"]
                validation_result["formatted_address"] = geo_validation["formatted_address"]
                validation_result["location_type"] = geo_validation["location_type"]
                if validation_result["confidence"] == 0.0:
                    validation_result["confidence"] = 0.8  # 地理編碼成功的基準信心度
            else:
                validation_result["issues"].extend(geo_validation["issues"])
                validation_result["suggestions"].extend(geo_validation["suggestions"])
            
            # 4. 座標格式檢查
            if self._is_coordinate_format(extracted_location):
                validation_result["location_type"] = "coordinates"
                validation_result["is_valid"] = True
                validation_result["confidence"] = max(validation_result["confidence"], 0.9)
            
            print(f"位置驗證結果：valid={validation_result['is_valid']}, confidence={validation_result['confidence']:.2f}")
            return validation_result
            
        except Exception as e:
            print(f"位置驗證錯誤: {e}")
            return {
                "is_valid": False,
                "confidence": 0.0,
                "issues": [f"驗證過程發生錯誤: {str(e)}"],
                "suggestions": ["請重新輸入位置資訊"],
                "location_type": "error"
            }
    
    def validate_search_plan_relevance(self, user_input: str, search_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證搜尋計畫是否貼近使用者意圖
        
        Args:
            user_input: 原始使用者輸入
            search_plan: 系統生成的搜尋計畫
            
        Returns:
            驗證結果字典
        """
        try:
            print(f"驗證搜尋計畫相關性")
            
            validation_result = {
                "is_relevant": False,
                "relevance_score": 0.0,
                "matched_aspects": [],
                "missing_aspects": [],
                "suggestions": [],
                "keyword_analysis": {},
                "intent_match": False
            }
            
            # 1. 提取搜尋關鍵字
            search_keywords = search_plan.get("search_keywords", [])
            if not search_keywords:
                validation_result["missing_aspects"].append("缺少搜尋關鍵字")
                validation_result["suggestions"].append("系統應根據使用者需求生成適當的搜尋關鍵字")
                return validation_result
            
            # 2. 使用 AI 分析意圖匹配
            if self.client:
                intent_analysis = self._ai_validate_search_intent(user_input, search_keywords)
                validation_result.update(intent_analysis)
            
            # 3. 關鍵字相關性分析
            keyword_relevance = self._analyze_keyword_relevance(user_input, search_keywords)
            validation_result["keyword_analysis"] = keyword_relevance
            
            # 4. 計算整體相關性分數
            relevance_score = self._calculate_relevance_score(validation_result)
            validation_result["relevance_score"] = relevance_score
            validation_result["is_relevant"] = relevance_score >= 0.6
            
            print(f"搜尋計畫驗證結果：relevant={validation_result['is_relevant']}, score={relevance_score:.2f}")
            return validation_result
            
        except Exception as e:
            print(f"搜尋計畫驗證錯誤: {e}")
            return {
                "is_relevant": False,
                "relevance_score": 0.0,
                "matched_aspects": [],
                "missing_aspects": [f"驗證過程發生錯誤: {str(e)}"],
                "suggestions": ["請檢查搜尋計畫是否完整"]
            }
    
    def validate_restaurant_recommendations(self, user_input: str, search_keywords: List[str], 
                                          restaurants: List[Dict]) -> Dict[str, Any]:
        """
        驗證餐廳推薦結果是否符合使用者需求
        
        Args:
            user_input: 原始使用者輸入
            search_keywords: 使用的搜尋關鍵字
            restaurants: 推薦的餐廳清單
            
        Returns:
            驗證結果字典
        """
        try:
            print(f"驗證餐廳推薦結果（{len(restaurants)}家）")
            
            validation_result = {
                "is_satisfactory": False,
                "quality_score": 0.0,
                "coverage_analysis": {},
                "diversity_score": 0.0,
                "distance_analysis": {},
                "issues": [],
                "suggestions": []
            }
            
            if not restaurants:
                validation_result["issues"].append("未找到任何餐廳推薦")
                validation_result["suggestions"].append("建議擴大搜尋範圍或使用更廣泛的關鍵字")
                return validation_result
            
            # 1. 關鍵字覆蓋分析
            coverage = self._analyze_keyword_coverage(search_keywords, restaurants)
            validation_result["coverage_analysis"] = coverage
            
            # 2. 多樣性分析
            diversity = self._analyze_restaurant_diversity(restaurants)
            validation_result["diversity_score"] = diversity
            
            # 3. 距離分析
            distance_analysis = self._analyze_restaurant_distances(restaurants)
            validation_result["distance_analysis"] = distance_analysis
            
            # 4. 使用 AI 分析推薦品質
            if self.client:
                ai_quality = self._ai_validate_recommendation_quality(user_input, restaurants)
                validation_result.update(ai_quality)
            
            # 5. 計算整體品質分數
            quality_score = self._calculate_recommendation_quality_score(validation_result)
            validation_result["quality_score"] = quality_score
            validation_result["is_satisfactory"] = quality_score >= 0.7
            
            print(f"餐廳推薦驗證結果：satisfactory={validation_result['is_satisfactory']}, score={quality_score:.2f}")
            return validation_result
            
        except Exception as e:
            print(f"餐廳推薦驗證錯誤: {e}")
            return {
                "is_satisfactory": False,
                "quality_score": 0.0,
                "issues": [f"驗證過程發生錯誤: {str(e)}"],
                "suggestions": ["請檢查推薦結果是否完整"]
            }
    
    def _ai_validate_location_relevance(self, user_input: str, extracted_location: str) -> Dict[str, Any]:
        """使用 AI 驗證位置提取的相關性"""
        try:
            prompt = f"""請分析以下使用者輸入與提取位置的相關性：

使用者輸入：「{user_input}」
提取的位置：「{extracted_location}」

請評估：
1. 提取的位置是否正確反映了使用者的意圖？
2. 位置資訊是否具體且可用？
3. 是否遺漏了重要的位置資訊？

請以JSON格式回應：
{{
  "relevance_score": 0.0到1.0的分數,
  "is_accurate": true/false,
  "explanation": "簡短解釋",
  "suggestions": ["改進建議列表"]
}}"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)
            
            return {
                "confidence": result.get("relevance_score", 0.0),
                "issues": [] if result.get("is_accurate", False) else [result.get("explanation", "AI檢測到位置提取問題")],
                "suggestions": result.get("suggestions", [])
            }
            
        except Exception as e:
            print(f"AI位置驗證失敗: {e}")
            return {"confidence": 0.0, "issues": [], "suggestions": []}
    
    def _ai_validate_search_intent(self, user_input: str, search_keywords: List[str]) -> Dict[str, Any]:
        """使用 AI 分析搜尋意圖匹配"""
        try:
            keywords_str = "、".join(search_keywords)
            prompt = f"""請分析搜尋關鍵字是否符合使用者意圖：

使用者輸入：「{user_input}」
系統搜尋關鍵字：「{keywords_str}」

請特別注意：
1. 搜尋關鍵字是否抓到使用者的核心需求？
2. 是否遺漏了重要的偏好？
3. 關鍵字是否過於寬泛或狭窄？
4. 【重要】如果使用者提到具體食物（如：拉麵、牛肉麵、義大利麵、鹽酥雞等），搜尋關鍵字是否保持了這種具體性，還是被過度泛化？

評分標準：
- 1.0分：完全匹配，包含具體食物名稱
- 0.8分：大致匹配，但可能略為泛化
- 0.6分：基本匹配，但有明顯泛化問題
- 0.4分：部分匹配，遺漏重要需求
- 0.2分：不太匹配
- 0.0分：完全不匹配

請以JSON格式回應：
{{
  "intent_match_score": 0.0到1.0的分數,
  "matched_aspects": ["符合的需求面向"],
  "missing_aspects": ["遺漏的需求面向"],
  "keyword_assessment": "關鍵字評估",
  "specificity_issue": "具體性問題描述（如有）",
  "suggested_keywords": ["建議的更具體關鍵字"]
}}"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)
            
            return {
                "intent_match": result.get("intent_match_score", 0.0) >= 0.6,
                "matched_aspects": result.get("matched_aspects", []),
                "missing_aspects": result.get("missing_aspects", []),
                "suggestions": [result.get("keyword_assessment", "")],
                "specificity_issue": result.get("specificity_issue", ""),
                "suggested_keywords": result.get("suggested_keywords", []),
                "intent_score": result.get("intent_match_score", 0.0)
            }
            
        except Exception as e:
            print(f"AI意圖驗證失敗: {e}")
            return {"intent_match": False, "matched_aspects": [], "missing_aspects": []}
    
    def _ai_validate_recommendation_quality(self, user_input: str, restaurants: List[Dict]) -> Dict[str, Any]:
        """使用 AI 分析推薦品質"""
        try:
            # 簡化餐廳資訊用於分析
            restaurant_summary = []
            for rest in restaurants[:5]:  # 只分析前5家
                summary = f"{rest.get('name', '未知')}({rest.get('food_type', '未分類')})"
                restaurant_summary.append(summary)
            
            restaurants_str = "、".join(restaurant_summary)
            prompt = f"""請分析餐廳推薦是否滿足使用者需求：

使用者需求：「{user_input}」
推薦餐廳：{restaurants_str}

請評估推薦品質並以JSON格式回應：
{{
  "satisfaction_score": 0.0到1.0的分數,
  "strengths": ["推薦的優點"],
  "weaknesses": ["推薦的不足"],
  "overall_assessment": "整體評估"
}}"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=250
            )
            
            result_text = response.choices[0].message.content.strip()
            result = json.loads(result_text)
            
            return {
                "ai_satisfaction_score": result.get("satisfaction_score", 0.0),
                "strengths": result.get("strengths", []),
                "weaknesses": result.get("weaknesses", [])
            }
            
        except Exception as e:
            print(f"AI推薦品質驗證失敗: {e}")
            return {"ai_satisfaction_score": 0.0, "strengths": [], "weaknesses": []}
    
    def _geocode_validation(self, location: str) -> Dict[str, Any]:
        """使用地理編碼驗證位置"""
        try:
            geolocator = Nominatim(user_agent="ai-lunch-mind-validator")
            location_data = geolocator.geocode(location, language='zh-TW', timeout=5)
            
            if location_data:
                return {
                    "success": True,
                    "coordinates": (location_data.latitude, location_data.longitude),
                    "formatted_address": location_data.address,
                    "location_type": "geocoded",
                    "issues": [],
                    "suggestions": []
                }
            else:
                return {
                    "success": False,
                    "issues": ["無法透過地理編碼找到該位置"],
                    "suggestions": ["請檢查位置名稱是否正確，或提供更詳細的地址"]
                }
                
        except Exception as e:
            return {
                "success": False,
                "issues": [f"地理編碼驗證失敗: {str(e)}"],
                "suggestions": ["請檢查網路連線或稍後再試"]
            }
    
    def _is_coordinate_format(self, location: str) -> bool:
        """檢查是否為座標格式"""
        try:
            if ',' in location:
                parts = location.split(',')
                if len(parts) == 2:
                    lat, lng = float(parts[0].strip()), float(parts[1].strip())
                    return -90 <= lat <= 90 and -180 <= lng <= 180
            return False
        except:
            return False
    
    def _analyze_keyword_relevance(self, user_input: str, keywords: List[str]) -> Dict[str, Any]:
        """分析關鍵字相關性"""
        user_lower = user_input.lower()
        keyword_scores = {}
        
        for keyword in keywords:
            score = 0.0
            # 直接匹配
            if keyword.lower() in user_lower:
                score += 1.0
            # 部分匹配
            elif any(char in user_lower for char in keyword.lower()):
                score += 0.5
            
            keyword_scores[keyword] = score
        
        return {
            "keyword_scores": keyword_scores,
            "average_relevance": sum(keyword_scores.values()) / len(keyword_scores) if keyword_scores else 0.0,
            "high_relevance_count": sum(1 for score in keyword_scores.values() if score >= 0.8)
        }
    
    def _calculate_relevance_score(self, validation_result: Dict) -> float:
        """計算整體相關性分數"""
        scores = []
        
        # AI意圖匹配分數
        if validation_result.get("intent_match"):
            scores.append(0.8)
        
        # 關鍵字分析分數
        keyword_analysis = validation_result.get("keyword_analysis", {})
        if keyword_analysis.get("average_relevance"):
            scores.append(keyword_analysis["average_relevance"])
        
        # 匹配面向數量
        matched_count = len(validation_result.get("matched_aspects", []))
        missing_count = len(validation_result.get("missing_aspects", []))
        if matched_count + missing_count > 0:
            aspect_score = matched_count / (matched_count + missing_count)
            scores.append(aspect_score)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _analyze_keyword_coverage(self, search_keywords: List[str], restaurants: List[Dict]) -> Dict[str, Any]:
        """分析關鍵字覆蓋率"""
        coverage = {}
        for keyword in search_keywords:
            matching_restaurants = [r for r in restaurants if r.get("food_type") == keyword]
            coverage[keyword] = {
                "count": len(matching_restaurants),
                "percentage": len(matching_restaurants) / len(restaurants) if restaurants else 0.0
            }
        
        return coverage
    
    def _analyze_restaurant_diversity(self, restaurants: List[Dict]) -> float:
        """分析餐廳多樣性"""
        if not restaurants:
            return 0.0
        
        food_types = set()
        for restaurant in restaurants:
            food_type = restaurant.get("food_type", "未分類")
            food_types.add(food_type)
        
        # 多樣性分數 = 不同類型數 / 總餐廳數（但不超過1.0）
        diversity_score = min(len(food_types) / len(restaurants), 1.0)
        return diversity_score
    
    def _analyze_restaurant_distances(self, restaurants: List[Dict]) -> Dict[str, Any]:
        """分析餐廳距離分布"""
        distances = []
        for restaurant in restaurants:
            distance = restaurant.get("distance_km")
            if distance and distance != "N/A":
                try:
                    distances.append(float(distance))
                except:
                    continue
        
        if not distances:
            return {"error": "無有效距離資料"}
        
        return {
            "min_distance": min(distances),
            "max_distance": max(distances),
            "avg_distance": sum(distances) / len(distances),
            "count_with_distance": len(distances),
            "total_count": len(restaurants)
        }
    
    def _calculate_recommendation_quality_score(self, validation_result: Dict) -> float:
        """計算推薦品質分數"""
        scores = []
        
        # 多樣性分數
        diversity = validation_result.get("diversity_score", 0.0)
        scores.append(diversity)
        
        # 覆蓋率分數
        coverage = validation_result.get("coverage_analysis", {})
        if coverage:
            coverage_scores = [data.get("percentage", 0.0) for data in coverage.values()]
            avg_coverage = sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0.0
            scores.append(avg_coverage)
        
        # 距離分析分數（距離越近越好，但適度分布更好）
        distance_analysis = validation_result.get("distance_analysis", {})
        if distance_analysis and "avg_distance" in distance_analysis:
            avg_dist = distance_analysis["avg_distance"]
            # 平均距離在1-3km之間給較高分數
            if 1.0 <= avg_dist <= 3.0:
                distance_score = 1.0
            elif avg_dist < 1.0:
                distance_score = 0.8  # 太近可能選擇有限
            else:
                distance_score = max(0.2, 1.0 - (avg_dist - 3.0) * 0.1)  # 距離越遠分數越低
            scores.append(distance_score)
        
        # AI品質分數
        ai_score = validation_result.get("ai_satisfaction_score", 0.0)
        if ai_score > 0:
            scores.append(ai_score)
        
        return sum(scores) / len(scores) if scores else 0.0


# 創建全域驗證器實例
validator = AIValidator()


def validate_location(user_input: str, extracted_location: str) -> Dict[str, Any]:
    """驗證位置提取結果"""
    return validator.validate_location_extraction(user_input, extracted_location)


def validate_search_plan(user_input: str, search_plan: Dict[str, Any]) -> Dict[str, Any]:
    """驗證搜尋計畫"""
    return validator.validate_search_plan_relevance(user_input, search_plan)


def validate_recommendations(user_input: str, search_keywords: List[str], restaurants: List[Dict]) -> Dict[str, Any]:
    """驗證餐廳推薦結果"""
    return validator.validate_restaurant_recommendations(user_input, search_keywords, restaurants)