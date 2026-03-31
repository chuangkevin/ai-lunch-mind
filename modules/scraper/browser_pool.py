"""
Browser Pool Management + Search Cache for the scraper subsystem.

Contains:
- create_chrome_driver() / create_chrome_driver_fast() -- Chrome WebDriver factories
- BrowserPool -- queue-based browser instance pool (used inside google_maps scraper)
- SearchCache -- in-memory TTL cache for search results
- Global singleton instances: browser_pool, search_cache

Note: The *other* browser pool lives at modules/browser_pool.py and is used by
some legacy code paths (search_restaurants_selenium).  This module is the one
used by the parallel / fast search pipeline.
"""

from typing import List, Dict, Optional, Any
import time
import random
import logging
import threading
from queue import Queue
from contextlib import contextmanager
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User-Agent pool
# ---------------------------------------------------------------------------
# TODO: migrate to database (see DATABASE_MIGRATION_TODO.md)
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
]


# ---------------------------------------------------------------------------
# Chrome driver factories
# ---------------------------------------------------------------------------

def create_chrome_driver(headless: bool = True) -> webdriver.Chrome:
    """
    Build a full-featured Chrome WebDriver instance.

    :param headless: run in headless mode
    :return: Chrome WebDriver
    """
    options = Options()

    if headless:
        options.add_argument('--headless')

    # Basic settings
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-gpu-sandbox')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-ipc-flooding-protection')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--disable-logging')
    options.add_argument('--disable-gpu-logging')
    options.add_argument('--silent')
    options.add_argument('--log-level=3')

    # Random User-Agent
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'--user-agent={user_agent}')

    # Language
    options.add_argument('--lang=zh-TW')

    try:
        driver = webdriver.Chrome(options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return driver
    except Exception as e:
        logger.error(f"Failed to create Chrome driver: {e}")
        raise


def create_chrome_driver_fast(headless: bool = True) -> webdriver.Chrome:
    """
    Build a speed-optimised Chrome WebDriver (no images, no JS).

    :param headless: run in headless mode
    :return: Chrome WebDriver
    """
    options = Options()

    if headless:
        options.add_argument('--headless')

    # Minimal settings for speed
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-plugins')
    options.add_argument('--disable-images')       # skip image loading
    options.add_argument('--disable-javascript')   # skip JS execution
    options.add_argument('--window-size=1024,768')  # small viewport

    # Fast User-Agent
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )

    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        logger.error(f"Failed to create fast Chrome driver: {e}")
        raise


# ---------------------------------------------------------------------------
# BrowserPool
# ---------------------------------------------------------------------------

class BrowserPool:
    """Queue-based browser instance pool for parallel searches."""

    def __init__(self, pool_size: int = 3):
        self.pool_size = pool_size
        self.available_browsers: Queue = Queue()
        self.all_browsers: list = []
        self.lock = threading.Lock()
        self._initialize_pool()

    def _initialize_pool(self):
        """Pre-create *pool_size* browser instances."""
        logger.info(f"[INIT] Initializing browser pool, size: {self.pool_size}")
        for i in range(self.pool_size):
            try:
                driver = create_chrome_driver_fast()
                self.available_browsers.put(driver)
                self.all_browsers.append(driver)
                logger.info(f"[SUCCESS] Browser {i + 1} created and added to pool")
            except Exception as e:
                logger.error(f"[ERROR] Failed to create browser {i + 1}: {e}")

    @contextmanager
    def get_browser(self):
        """Context manager that borrows a browser from the pool."""
        driver = None
        try:
            # Try to get a browser from the pool (3 s timeout)
            driver = self.available_browsers.get(timeout=3)

            # Verify the session is alive before yielding
            try:
                driver.title  # simple check that doesn't navigate
            except Exception:
                # Session is dead, create a new one
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = create_chrome_driver_fast()
                with self.lock:
                    self.all_browsers.append(driver)

            yield driver
        except Exception:
            # Pool exhausted -- create a temporary instance
            logger.warning("[WARNING] Pool exhausted, creating temporary browser")
            driver = create_chrome_driver(headless=True)
            with self.lock:
                self.all_browsers.append(driver)
            yield driver
        finally:
            if driver:
                try:
                    driver.delete_all_cookies()
                    self.available_browsers.put(driver)
                except Exception:
                    try:
                        driver.quit()
                    except Exception:
                        pass

    def close_all(self):
        """Shut down every browser managed by this pool."""
        logger.info("[SHUTDOWN] Closing all browser instances")
        for driver in self.all_browsers:
            try:
                driver.quit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# SearchCache
# ---------------------------------------------------------------------------

class SearchCache:
    """In-memory TTL cache for search results."""

    def __init__(self, cache_ttl: int = 300):  # 5-minute default
        self.cache: dict = {}
        self.cache_ttl = cache_ttl
        self.lock = threading.Lock()

    def get_cache_key(self, keyword: str, location_info: Optional[Dict] = None) -> str:
        location_str = ""
        if location_info and location_info.get('address'):
            location_str = location_info['address']
        return f"{keyword}_{location_str}"

    def get(self, keyword: str, location_info: Optional[Dict] = None) -> Optional[List[Dict]]:
        cache_key = self.get_cache_key(keyword, location_info)
        with self.lock:
            if cache_key in self.cache:
                cached_data, timestamp = self.cache[cache_key]
                if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                    logger.info(f"Using cached result: {cache_key}")
                    return cached_data
                else:
                    del self.cache[cache_key]
        return None

    def set(self, keyword: str, location_info: Optional[Dict], results: List[Dict]):
        cache_key = self.get_cache_key(keyword, location_info)
        with self.lock:
            self.cache[cache_key] = (results, datetime.now())
            logger.info(f"Cached search result: {cache_key}")


# ---------------------------------------------------------------------------
# Global singleton instances
# ---------------------------------------------------------------------------
# Lazy-initialized singleton — don't create Chrome on import
_browser_pool_instance = None
_browser_pool_lock = threading.Lock()

def _get_browser_pool():
    global _browser_pool_instance
    if _browser_pool_instance is None:
        with _browser_pool_lock:
            if _browser_pool_instance is None:
                _browser_pool_instance = BrowserPool(pool_size=2)
    return _browser_pool_instance

class _LazyBrowserPool:
    """Proxy that delays BrowserPool creation until first use."""
    def get_browser(self):
        return _get_browser_pool().get_browser()
    def close_all(self):
        if _browser_pool_instance:
            _browser_pool_instance.close_all()

browser_pool = _LazyBrowserPool()
search_cache = SearchCache()
