# test_performance_optimization.py
"""
測試性能優化效果 - 比較優化前後的響應時間
"""

import time
import sys
import os

# 添加項目根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_cache_performance():
    """測試快取系統性能提升"""
    print("=" * 60)
    print("測試快取系統性能")
    print("=" * 60)
    
    try:
        from modules.cache_manager import cache_manager
        from modules.google_maps import search_restaurants
        from modules.weather import get_weather_data
        from modules.dialog_analysis import analyze_user_request
        
        # 測試場景
        test_location = "台北101"
        test_keyword = "拉麵"
        test_user_input = "我在台北101想吃拉麵"
        
        print("第一次搜尋（填充快取）...")
        
        # 餐廳搜尋測試
        start_time = time.time()
        restaurants = search_restaurants(test_keyword, test_location, 5)
        first_search_time = time.time() - start_time
        
        # 天氣資料測試
        start_time = time.time()
        weather = get_weather_data(test_location)
        first_weather_time = time.time() - start_time
        
        # AI分析測試
        start_time = time.time()
        analysis = analyze_user_request(test_user_input)
        first_analysis_time = time.time() - start_time
        
        print("第二次搜尋（應使用快取）...")
        
        # 重複測試（應該命中快取）
        start_time = time.time()
        restaurants_cached = search_restaurants(test_keyword, test_location, 5)
        second_search_time = time.time() - start_time
        
        start_time = time.time()
        weather_cached = get_weather_data(test_location)
        second_weather_time = time.time() - start_time
        
        start_time = time.time()
        analysis_cached = analyze_user_request(test_user_input)
        second_analysis_time = time.time() - start_time
        
        # 顯示結果
        print(f"\n性能比較結果：")
        print(f"餐廳搜尋：{first_search_time:.2f}s → {second_search_time:.2f}s (提升 {((first_search_time - second_search_time) / first_search_time * 100):.1f}%)")
        print(f"天氣查詢：{first_weather_time:.2f}s → {second_weather_time:.2f}s (提升 {((first_weather_time - second_weather_time) / first_weather_time * 100):.1f}%)")
        print(f"AI分析：{first_analysis_time:.2f}s → {second_analysis_time:.2f}s (提升 {((first_analysis_time - second_analysis_time) / first_analysis_time * 100):.1f}%)")
        
        # 顯示快取統計
        stats = cache_manager.get_cache_stats()
        print(f"\n快取統計：")
        print(f"總請求數：{stats['total_requests']}")
        print(f"快取命中率：{stats['hit_rate']}")
        print(f"餐廳快取：{stats['restaurant_cache_size']} 項目")
        print(f"天氣快取：{stats['weather_cache_size']} 項目")
        print(f"AI快取：{stats['ai_cache_size']} 項目")
        
        return True
        
    except Exception as e:
        print(f"快取測試失敗: {e}")
        return False

def test_browser_pool_performance():
    """測試瀏覽器池性能提升"""
    print("=" * 60)
    print("測試瀏覽器池性能")
    print("=" * 60)
    
    try:
        from modules.browser_pool import get_pool_status, close_all_browsers
        
        # 顯示瀏覽器池狀態
        status = get_pool_status()
        print(f"瀏覽器池狀態：")
        print(f"總瀏覽器數：{status['total_browsers']}")
        print(f"使用中：{status['in_use']}")
        print(f"可用：{status['available']}")
        print(f"池大小：{status['pool_size']}")
        
        return True
        
    except Exception as e:
        print(f"瀏覽器池測試失敗: {e}")
        return False

def test_parallel_processing_performance():
    """測試並行處理性能提升"""
    print("=" * 60)
    print("測試並行處理性能")
    print("=" * 60)
    
    try:
        from modules.ai_recommendation_engine import recommendation_engine
        
        test_cases = [
            ("台北101", "我想吃拉麵"),
            ("西門町", "想要熱炒店"),
            ("信義區", "找個咖啡廳")
        ]
        
        total_time = 0
        for location, user_input in test_cases:
            print(f"測試案例：{location} - {user_input}")
            
            start_time = time.time()
            result = recommendation_engine.generate_recommendation(
                location=location,
                user_input=user_input,
                max_results=5
            )
            elapsed_time = time.time() - start_time
            total_time += elapsed_time
            
            success = result and len(result.get('restaurants', [])) > 0
            print(f"   耗時：{elapsed_time:.2f}s - {'成功' if success else '失敗'}")
        
        average_time = total_time / len(test_cases)
        print(f"\n平均響應時間：{average_time:.2f}s")
        print(f"目標響應時間：6.0s")
        
        if average_time <= 6.0:
            print("性能目標達成！")
            return True
        else:
            print("需要進一步優化")
            return False
        
    except Exception as e:
        print(f"並行處理測試失敗: {e}")
        return False

def main():
    """主測試函數"""
    print("性能優化測試開始")
    print(f"測試時間：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        "cache": test_cache_performance(),
        "browser_pool": test_browser_pool_performance(),
        "parallel": test_parallel_processing_performance()
    }
    
    print("\n" + "=" * 60)
    print("測試總結")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "通過" if passed_test else "失敗"
        print(f"{test_name:15} {status}")
    
    print(f"\n總體結果：{passed}/{total} 項測試通過")
    
    if passed == total:
        print("所有性能優化測試通過！")
    else:
        print("部分測試失敗，需要檢查優化實現")
    
    # 清理資源
    try:
        from modules.browser_pool import close_all_browsers
        close_all_browsers()
    except:
        pass

if __name__ == "__main__":
    main()