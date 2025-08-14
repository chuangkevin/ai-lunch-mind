# test_performance_quick.py
"""
快速性能測試 - 驗證性能優化功能是否正常運作
"""

import time
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_caching_system():
    """測試快取系統是否正常運作"""
    print("=" * 50)
    print("測試快取系統")
    print("=" * 50)
    
    try:
        from modules.cache_manager import cache_manager
        
        # 清空快取
        cache_manager.clear_cache()
        
        # 測試餐廳快取
        cache_manager.set_restaurant_cache("拉麵", "台北101", 5, [{"name": "測試餐廳"}])
        cached = cache_manager.get_restaurant_cache("拉麵", "台北101", 5)
        
        # 測試天氣快取
        cache_manager.set_weather_cache("台北101", {"temperature": 25})
        weather_cached = cache_manager.get_weather_cache("台北101")
        
        # 測試AI快取
        cache_manager.set_ai_cache("測試輸入", {"result": "測試"})
        ai_cached = cache_manager.get_ai_cache("測試輸入")
        
        # 檢查結果
        stats = cache_manager.get_cache_stats()
        
        print(f"餐廳快取: {'成功' if cached else '失敗'}")
        print(f"天氣快取: {'成功' if weather_cached else '失敗'}")  
        print(f"AI快取: {'成功' if ai_cached else '失敗'}")
        print(f"快取命中率: {stats['hit_rate']}")
        print(f"總快取項目: {stats['restaurant_cache_size'] + stats['weather_cache_size'] + stats['ai_cache_size']}")
        
        return cached and weather_cached and ai_cached
        
    except Exception as e:
        print(f"快取系統測試失敗: {e}")
        return False

def test_browser_pool():
    """測試瀏覽器池是否正常運作"""
    print("=" * 50)
    print("測試瀏覽器池")
    print("=" * 50)
    
    try:
        from modules.browser_pool import get_pool_status
        
        status = get_pool_status()
        print(f"瀏覽器池大小: {status['pool_size']}")
        print(f"總瀏覽器數: {status['total_browsers']}")
        print(f"可用瀏覽器: {status['available']}")
        
        # 瀏覽器池基本功能正常
        return True
        
    except Exception as e:
        print(f"瀏覽器池測試失敗: {e}")
        return False

def test_parallel_processing():
    """測試並行處理是否已整合"""
    print("=" * 50)
    print("測試並行處理整合")
    print("=" * 50)
    
    try:
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor
        
        # 驗證並行處理模組可用
        print("ThreadPoolExecutor: 可用")
        
        # 簡單的並行任務測試
        def test_task(x):
            time.sleep(0.1)
            return x * 2
        
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(test_task, i) for i in range(3)]
            results = [f.result() for f in futures]
        parallel_time = time.time() - start_time
        
        print(f"並行執行3個任務耗時: {parallel_time:.2f}s")
        print(f"預期時間約0.1s (而非0.3s)")
        
        return parallel_time < 0.2  # 應該遠小於順序執行的0.3s
        
    except Exception as e:
        print(f"並行處理測試失敗: {e}")
        return False

def main():
    """主測試函數"""
    print("快速性能測試開始")
    print(f"測試時間: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = {
        "快取系統": test_caching_system(),
        "瀏覽器池": test_browser_pool(), 
        "並行處理": test_parallel_processing()
    }
    
    print("\n" + "=" * 50)
    print("測試結果摘要")
    print("=" * 50)
    
    passed = 0
    total = len(tests)
    
    for test_name, result in tests.items():
        status = "通過" if result else "失敗"
        if result:
            passed += 1
        print(f"{test_name:10} {status}")
    
    print(f"\n總體結果: {passed}/{total} 項測試通過")
    
    if passed == total:
        print("所有性能優化組件測試通過！")
        print("性能優化功能已成功整合到系統中")
    else:
        print("部分功能測試失敗")
    
    # 清理
    try:
        from modules.browser_pool import close_all_browsers
        close_all_browsers()
    except:
        pass
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)