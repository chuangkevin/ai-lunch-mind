# modules/browser_pool.py
"""
瀏覽器池管理系統 - 避免重複啟動瀏覽器

主要功能：
1. 瀏覽器實例複用
2. 連接池管理
3. 異常恢復機制
4. 資源清理
"""

import time
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from contextlib import contextmanager

class BrowserPool:
    def __init__(self, pool_size=2, max_idle_time=300):  # 5分鐘閒置
        self.pool_size = pool_size
        self.max_idle_time = max_idle_time
        self.browsers = []
        self.in_use = set()
        self.lock = threading.Lock()
        self.last_used = {}
        
        # 初始化瀏覽器選項
        self.chrome_options = self._get_chrome_options()
        
        print(f"初始化瀏覽器池：大小 {pool_size}")
    
    def _get_chrome_options(self):
        """配置Chrome選項"""
        options = Options()
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
        
        # 快速載入設定
        options.add_argument('--disable-images')
        options.add_argument('--disable-javascript')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-extensions')
        
        return options
    
    def _create_browser(self):
        """創建新的瀏覽器實例"""
        try:
            print("創建新的瀏覽器實例...")
            start_time = time.time()
            
            browser = webdriver.Chrome(options=self.chrome_options)
            browser.set_page_load_timeout(30)
            browser.implicitly_wait(10)
            
            # 預載 Google Maps 提升後續速度
            browser.get("https://www.google.com/maps")
            
            elapsed = time.time() - start_time
            print(f"瀏覽器創建完成，耗時 {elapsed:.1f}秒")
            
            return browser
            
        except Exception as e:
            print(f"瀏覽器創建失敗: {e}")
            return None
    
    def _is_browser_healthy(self, browser):
        """檢查瀏覽器是否健康"""
        try:
            # 簡單的健康檢查
            browser.current_url
            return True
        except Exception:
            return False
    
    def get_browser(self):
        """從池中獲取瀏覽器"""
        with self.lock:
            # 清理過期的瀏覽器
            self._cleanup_idle_browsers()
            
            # 查找可用的瀏覽器
            for browser in self.browsers[:]:
                if browser not in self.in_use:
                    if self._is_browser_healthy(browser):
                        self.in_use.add(browser)
                        self.last_used[browser] = time.time()
                        print(f"複用現有瀏覽器 (池中 {len(self.browsers)} 個)")
                        return browser
                    else:
                        # 移除不健康的瀏覽器
                        self._remove_browser(browser)
            
            # 如果池未滿，創建新瀏覽器
            if len(self.browsers) < self.pool_size:
                browser = self._create_browser()
                if browser:
                    self.browsers.append(browser)
                    self.in_use.add(browser)
                    self.last_used[browser] = time.time()
                    return browser
            
            # 池已滿，等待或創建臨時瀏覽器
            print("瀏覽器池已滿，創建臨時實例...")
            return self._create_browser()
    
    def release_browser(self, browser):
        """歸還瀏覽器到池中"""
        with self.lock:
            if browser in self.in_use:
                self.in_use.remove(browser)
                self.last_used[browser] = time.time()
                
                # 重置瀏覽器狀態（可選）
                try:
                    if len(browser.window_handles) > 1:
                        # 關閉多餘的標籤頁
                        for handle in browser.window_handles[1:]:
                            browser.switch_to.window(handle)
                            browser.close()
                        browser.switch_to.window(browser.window_handles[0])
                except Exception as e:
                    print(f"瀏覽器重置失敗: {e}")
                    self._remove_browser(browser)
                    return
                
                print(f"瀏覽器已歸還到池中")
    
    def _remove_browser(self, browser):
        """從池中移除瀏覽器"""
        try:
            if browser in self.browsers:
                self.browsers.remove(browser)
            if browser in self.in_use:
                self.in_use.remove(browser)
            if browser in self.last_used:
                del self.last_used[browser]
            
            browser.quit()
            print("移除不健康的瀏覽器")
        except Exception as e:
            print(f"移除瀏覽器時發生錯誤: {e}")
    
    def _cleanup_idle_browsers(self):
        """清理閒置的瀏覽器"""
        current_time = time.time()
        idle_browsers = []
        
        for browser in self.browsers[:]:
            if browser not in self.in_use:
                last_use = self.last_used.get(browser, current_time)
                if current_time - last_use > self.max_idle_time:
                    idle_browsers.append(browser)
        
        for browser in idle_browsers:
            print(f"清理閒置瀏覽器（閒置 {self.max_idle_time}秒）")
            self._remove_browser(browser)
    
    def close_all(self):
        """關閉所有瀏覽器"""
        with self.lock:
            for browser in self.browsers[:]:
                try:
                    browser.quit()
                except Exception as e:
                    print(f"關閉瀏覽器時發生錯誤: {e}")
            
            self.browsers.clear()
            self.in_use.clear()
            self.last_used.clear()
            print("所有瀏覽器已關閉")
    
    def get_pool_status(self):
        """獲取池狀態"""
        with self.lock:
            return {
                "total_browsers": len(self.browsers),
                "in_use": len(self.in_use),
                "available": len(self.browsers) - len(self.in_use),
                "pool_size": self.pool_size
            }
    
    @contextmanager
    def get_browser_context(self):
        """上下文管理器，確保瀏覽器被正確歸還"""
        browser = None
        try:
            browser = self.get_browser()
            yield browser
        finally:
            if browser:
                self.release_browser(browser)

# 創建全域瀏覽器池實例
browser_pool = BrowserPool(pool_size=2, max_idle_time=300)

# 便捷函數
def get_browser():
    """獲取瀏覽器實例"""
    return browser_pool.get_browser()

def release_browser(browser):
    """歸還瀏覽器實例"""
    browser_pool.release_browser(browser)

def get_browser_context():
    """瀏覽器上下文管理器"""
    return browser_pool.get_browser_context()

def get_pool_status():
    """獲取瀏覽器池狀態"""
    return browser_pool.get_pool_status()

def close_all_browsers():
    """關閉所有瀏覽器"""
    browser_pool.close_all()