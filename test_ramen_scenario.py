# test_ramen_scenario.py
"""
測試拉麵場景 - 驗證系統是否能正確處理具體食物需求

執行方式：python test_ramen_scenario.py
"""

import os
import sys
sys.path.append('.')

from modules.ai_recommendation_engine import SmartRecommendationEngine
from modules.ai_validator import validate_search_plan

def test_ramen_scenario():
    """測試拉麵場景的完整流程"""
    print("=== 測試拉麵場景 ===\n")
    
    # 創建推薦引擎實例
    ai_engine = SmartRecommendationEngine()
    
    # 測試輸入
    user_input = "我在台北車站，想吃拉麵"
    location = "台北車站"
    
    print(f"使用者輸入：{user_input}")
    print(f"位置：{location}")
    print()
    
    try:
        # 1. 測試關鍵字選擇邏輯
        print("--- 1. 測試關鍵字選擇邏輯 ---")
        
        # 模擬推薦引擎的關鍵字選擇過程
        search_keywords = ai_engine._get_search_keywords(user_input, 5.0, 25.0)
        print(f"生成的搜尋關鍵字：{search_keywords}")
        
        # 檢查是否包含「拉麵」
        if "拉麵" in search_keywords:
            print("成功保持具體性：包含「拉麵」")
        elif "麵食" in search_keywords:
            print("發現泛化問題：使用了「麵食」而不是「拉麵」")
        else:
            print("關鍵字選擇有問題：既沒有「拉麵」也沒有「麵食」")
        
        print()
        
        # 2. 測試驗證邏輯
        print("--- 2. 測試驗證邏輯 ---")
        
        plan_data = {
            "search_keywords": search_keywords,
            "location": location,
            "max_distance_km": 2.0
        }
        
        validation_result = validate_search_plan(user_input, plan_data)
        
        print(f"驗證結果：")
        print(f"  相關性：{validation_result['is_relevant']}")
        print(f"  相關性分數：{validation_result['relevance_score']:.2f}")
        print(f"  意圖匹配：{validation_result['intent_match']}")
        
        if validation_result.get('specificity_issue'):
            print(f"  具體性問題：{validation_result['specificity_issue']}")
        
        if validation_result.get('suggested_keywords'):
            print(f"  建議關鍵字：{validation_result['suggested_keywords']}")
        
        print()
        
        # 3. 分析結果
        print("--- 3. 結果分析 ---")
        
        # 檢查意圖匹配分數
        intent_score = validation_result.get('intent_score', 0.0)
        if intent_score >= 0.8:
            print("優秀：意圖匹配分數很高")
        elif intent_score >= 0.6:
            print("尚可：意圖匹配分數中等，可能有改進空間")
        else:
            print("問題：意圖匹配分數過低，需要調整")
        
        # 檢查關鍵字具體性
        if "拉麵" in search_keywords:
            print("關鍵字具體性良好")
        else:
            print("關鍵字過度泛化，建議保持具體性")
        
        return {
            "keywords_appropriate": "拉麵" in search_keywords,
            "validation_score": validation_result['relevance_score'],
            "intent_score": intent_score,
            "has_specificity_issue": bool(validation_result.get('specificity_issue'))
        }
        
    except Exception as e:
        print(f"測試過程中發生錯誤：{e}")
        import traceback
        traceback.print_exc()
        return None

def test_comparison_scenarios():
    """測試對比場景：拉麵 vs 麵食"""
    print("\n=== 對比測試：具體 vs 泛化 ===\n")
    
    scenarios = [
        {
            "name": "具體食物需求",
            "user_input": "我想吃拉麵",
            "expected_keywords": ["拉麵"]
        },
        {
            "name": "泛化食物需求",
            "user_input": "我想吃麵食",
            "expected_keywords": ["麵食"]
        },
        {
            "name": "多種具體需求",
            "user_input": "我想吃拉麵或義大利麵",
            "expected_keywords": ["拉麵", "義大利麵"]
        }
    ]
    
    ai_engine = SmartRecommendationEngine()
    
    for scenario in scenarios:
        print(f"場景：{scenario['name']}")
        print(f"輸入：{scenario['user_input']}")
        
        try:
            keywords = ai_engine._get_search_keywords(scenario['user_input'], 5.0, 25.0)
            print(f"生成關鍵字：{keywords}")
            
            # 檢查是否符合期望
            expected = scenario['expected_keywords']
            matches = any(exp in keywords for exp in expected)
            
            if matches:
                print("符合期望")
            else:
                print("不符合期望")
                print(f"期望包含：{expected}")
            
        except Exception as e:
            print(f"錯誤：{e}")
        
        print()

def main():
    """主測試函數"""
    print("開始測試拉麵場景的具體性處理\n")
    
    # 檢查 OpenAI API 金鑰
    if not os.getenv("OPENAI_API_KEY"):
        print("警告：OPENAI_API_KEY 未設置，AI驗證功能可能受限\n")
    
    # 執行主測試
    result = test_ramen_scenario()
    
    # 執行對比測試
    test_comparison_scenarios()
    
    # 總結
    print("=== 測試總結 ===")
    if result:
        print(f"關鍵字適當性：{'通過' if result['keywords_appropriate'] else '失敗'}")
        print(f"驗證分數：{result['validation_score']:.2f}")
        print(f"意圖分數：{result['intent_score']:.2f}")
        print(f"具體性問題：{'有' if result['has_specificity_issue'] else '無'}")
        
        if result['keywords_appropriate'] and result['intent_score'] >= 0.8:
            print("測試通過：系統能正確處理具體食物需求！")
        else:
            print("需要改進：系統在處理具體食物需求方面還有改進空間")
    else:
        print("測試失敗：無法完成測試")

if __name__ == "__main__":
    main()