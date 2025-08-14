# test_ai_validation.py
"""
測試 AI 驗證模組功能

執行方式：python test_ai_validation.py
"""

import os
import sys
sys.path.append('.')

from modules.ai_validator import validate_location, validate_search_plan, validate_recommendations

def test_location_validation():
    """測試位置驗證功能"""
    print("=== 測試位置驗證功能 ===\n")
    
    # 測試案例
    test_cases = [
        {
            "user_input": "我在台北101附近",
            "extracted_location": "台北101",
            "expected": "valid"
        },
        {
            "user_input": "想找信義區的餐廳",
            "extracted_location": "信義區",
            "expected": "valid"
        },
        {
            "user_input": "我想吃飯",
            "extracted_location": "XYZ不存在的地方",
            "expected": "invalid"
        },
        {
            "user_input": "25.033,121.565這裡有什麼好吃的",
            "extracted_location": "25.033,121.565",
            "expected": "valid_coordinates"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"測試案例 {i}：")
        print(f"  輸入：{case['user_input']}")
        print(f"  提取位置：{case['extracted_location']}")
        
        result = validate_location(case['user_input'], case['extracted_location'])
        
        print(f"  驗證結果：")
        print(f"    有效性：{result['is_valid']}")
        print(f"    信心度：{result['confidence']:.2f}")
        print(f"    位置類型：{result['location_type']}")
        
        if result['issues']:
            print(f"    問題：{result['issues']}")
        if result['suggestions']:
            print(f"    建議：{result['suggestions']}")
        
        print()

def test_search_plan_validation():
    """測試搜尋計畫驗證功能"""
    print("=== 測試搜尋計畫驗證功能 ===\n")
    
    # 測試案例
    test_cases = [
        {
            "user_input": "我想吃火鍋",
            "search_plan": {
                "search_keywords": ["火鍋", "麻辣鍋", "涮涮鍋"],
                "location": "台北101",
                "max_distance_km": 2.0
            },
            "expected": "relevant"
        },
        {
            "user_input": "想吃清爽的食物",
            "search_plan": {
                "search_keywords": ["火鍋", "麻辣鍋", "燒烤"],
                "location": "信義區",
                "max_distance_km": 1.5
            },
            "expected": "not_relevant"
        },
        {
            "user_input": "我要吃東山鴨頭",
            "search_plan": {
                "search_keywords": ["鴨頭", "滷味", "小吃"],
                "location": "夜市",
                "max_distance_km": 1.0
            },
            "expected": "relevant"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"測試案例 {i}：")
        print(f"  輸入：{case['user_input']}")
        print(f"  搜尋關鍵字：{case['search_plan']['search_keywords']}")
        
        result = validate_search_plan(case['user_input'], case['search_plan'])
        
        print(f"  驗證結果：")
        print(f"    相關性：{result['is_relevant']}")
        print(f"    相關性分數：{result['relevance_score']:.2f}")
        print(f"    意圖匹配：{result['intent_match']}")
        
        if result['matched_aspects']:
            print(f"    匹配面向：{result['matched_aspects']}")
        if result['missing_aspects']:
            print(f"    遺漏面向：{result['missing_aspects']}")
        if result['suggestions']:
            print(f"    建議：{result['suggestions']}")
        
        print()

def test_recommendation_validation():
    """測試餐廳推薦驗證功能"""
    print("=== 測試餐廳推薦驗證功能 ===\n")
    
    # 模擬餐廳資料
    mock_restaurants = [
        {
            "name": "老四川巴蜀麻辣燙",
            "food_type": "火鍋",
            "distance_km": "0.8",
            "rating": "4.2",
            "address": "台北市信義區"
        },
        {
            "name": "鼎王麻辣鍋",
            "food_type": "火鍋",
            "distance_km": "1.2",
            "rating": "4.5",
            "address": "台北市信義區"
        },
        {
            "name": "港式茶餐廳",
            "food_type": "港式",
            "distance_km": "0.5",
            "rating": "4.0",
            "address": "台北市信義區"
        }
    ]
    
    test_cases = [
        {
            "user_input": "我想吃火鍋",
            "search_keywords": ["火鍋", "麻辣鍋"],
            "restaurants": mock_restaurants,
            "expected": "satisfactory"
        },
        {
            "user_input": "想吃清爽的食物",
            "search_keywords": ["沙拉", "輕食"],
            "restaurants": mock_restaurants,  # 不匹配的推薦
            "expected": "not_satisfactory"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"測試案例 {i}：")
        print(f"  輸入：{case['user_input']}")
        print(f"  搜尋關鍵字：{case['search_keywords']}")
        print(f"  推薦餐廳數：{len(case['restaurants'])}")
        
        result = validate_recommendations(
            case['user_input'], 
            case['search_keywords'], 
            case['restaurants']
        )
        
        print(f"  驗證結果：")
        print(f"    滿意度：{result['is_satisfactory']}")
        print(f"    品質分數：{result['quality_score']:.2f}")
        print(f"    多樣性分數：{result['diversity_score']:.2f}")
        
        if 'coverage_analysis' in result:
            print(f"    關鍵字覆蓋：{result['coverage_analysis']}")
        
        if result['issues']:
            print(f"    問題：{result['issues']}")
        if result['suggestions']:
            print(f"    建議：{result['suggestions']}")
        
        print()

def main():
    """主測試函數"""
    print("開始測試 AI 驗證模組\n")
    
    # 檢查 OpenAI API 金鑰
    if not os.getenv("OPENAI_API_KEY"):
        print("警告：OPENAI_API_KEY 未設置，某些 AI 功能將無法測試\n")
    
    try:
        # 執行各項測試
        test_location_validation()
        test_search_plan_validation()
        test_recommendation_validation()
        
        print("所有測試完成！")
        
    except Exception as e:
        print(f"測試過程中發生錯誤：{e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()