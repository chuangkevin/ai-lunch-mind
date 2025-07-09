#!/usr/bin/env python3
"""
測試 AI 午餐推薦系統 API
"""
import requests
import json

def test_health():
    """測試健康檢查端點"""
    try:
        response = requests.get("http://localhost:8000/health")
        print(f"健康檢查: {response.status_code}")
        print(f"回應: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"健康檢查失敗: {e}")
        return False

def test_recommend():
    """測試推薦端點"""
    test_data = {
        "text": "我想找附近好吃的中式餐廳",
        "location": {
            "latitude": 25.0330,
            "longitude": 121.5654,
            "address": "台北市信義區"
        }
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/recommend",
            headers={"Content-Type": "application/json"},
            json=test_data
        )
        print(f"\n推薦端點: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("推薦成功！")
            print(f"找到 {len(result.get('restaurants', []))} 間餐廳")
            print(f"AI 回應: {result.get('ai_response', '無回應')[:100]}...")
        else:
            print(f"錯誤回應: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"推薦測試失敗: {e}")
        return False

def test_root():
    """測試根端點"""
    try:
        response = requests.get("http://localhost:8000/")
        print(f"根端點: {response.status_code}")
        print(f"回應: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"根端點測試失敗: {e}")
        return False

if __name__ == "__main__":
    print("=== AI 午餐推薦系統 API 測試 ===\n")
    
    # 測試所有端點
    tests = [
        ("根端點", test_root),
        ("健康檢查", test_health),
        ("推薦功能", test_recommend)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"正在測試 {name}...")
        success = test_func()
        results.append((name, success))
        print(f"{'✓ 通過' if success else '✗ 失敗'}\n")
    
    # 總結
    print("=== 測試結果 ===")
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✓ 通過" if success else "✗ 失敗"
        print(f"{name}: {status}")
    
    print(f"\n總計: {passed}/{total} 項測試通過")
    
    if passed == total:
        print("🎉 所有測試都通過了！系統運行正常。")
    else:
        print("⚠️  有測試失敗，請檢查錯誤訊息。")
