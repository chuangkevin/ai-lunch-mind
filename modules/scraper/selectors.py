"""
CSS Selectors - Google Maps / Google Search result page selectors centralized.

All CSS selectors used across the scraper modules are defined here as named
constants so they can be maintained in a single place.
"""

# ---------------------------------------------------------------------------
# find_search_results() -- result container selectors (tried in order)
# ---------------------------------------------------------------------------
SEARCH_RESULT_SELECTORS = [
    "div.VkpGBb",          # New Google Local result container
    "div.dbg0pd",          # Alternative result container
    "div.rllt__details",   # Local search result details
    "div.UaQhfb",          # Maps search result
    "div[data-ved]",       # Generic container with data-ved attribute
    ".g",                  # Classic search result
    "div.Nv2PK",           # New local search result
    "div.P7xzyf",          # Another local result format
    "article",             # HTML5 article element
    "div[role='article']", # Semantic search result
    "div.tF2Cxc",          # New search result container
    "div.MjjYud",          # Another new container
]

# ---------------------------------------------------------------------------
# Restaurant name selectors
# ---------------------------------------------------------------------------
NAME_SELECTORS = [
    "span.OSrXXb",
    "h3.LC20lb",
    "div.qBF1Pd",
    "span.LrzXr",
]

# ---------------------------------------------------------------------------
# Address selectors  (extract_restaurant_info_minimal)
# ---------------------------------------------------------------------------
ADDRESS_SELECTORS = [
    # Latest Google Maps address selectors (2024 format)
    "div.W4Efsd span.ZDu9vd",                                       # Primary Maps address
    "div.W4Efsd > span:last-child",                                  # Last span in W4Efsd div
    "div.W4Efsd span:not([class*='MW4etd']):not([class*='yi40Hd'])", # Exclude rating spans
    "span.LrzXr",                                                    # Address-specific style
    "div.rllt__details div span:not([class*='rating'])",             # Detail spans (non-rating)
    # More precise selectors to avoid rating info
    "div.UaQhfb span:not([class*='MW4etd']):not([class*='yi40Hd'])",
    "div.lI9IFe span:not([class*='rating'])",
    ".BNeawe.UPmit.AP7Wnd",                                          # Another address style
    "div[data-value*='\u5730\u5740']",                                # div containing '地址'
    "span[title*='\u5730\u5740']",                                    # span whose title contains '地址'
    # Generic selectors (last resort)
    "div.fontBodyMedium:not([class*='rating'])",
    "span.fontBodyMedium:not([class*='rating'])",
]

# ---------------------------------------------------------------------------
# Address selectors (display-only variant)
# ---------------------------------------------------------------------------
ADDRESS_SELECTORS_DISPLAY_ONLY = [
    "div.W4Efsd span.ZDu9vd",
    "div.W4Efsd > span:last-child",
    "span.LrzXr",
    "div.rllt__details div span:not([class*='rating'])",
]

# ---------------------------------------------------------------------------
# Rating selectors
# ---------------------------------------------------------------------------
RATING_SELECTORS = [
    "span.yi40Hd",                         # Primary rating style
    "span.MW4etd",                         # Alternative rating style
    ".BTtC6e",                             # Other rating style
    "span[aria-label*='star']",            # aria-label containing 'star'
    "span[aria-label*='\u661f']",          # aria-label containing Chinese '星'
    "div.fontDisplayLarge",                # Large-font rating
    "span.fontDisplayLarge",               # Large-font rating
    ".ceNzKf",                             # Google Maps rating style
    "span.ZkP5Je",                         # New rating style
    ".Aq14fc",                             # Another new style
    "span[jsaction*='pane']",              # Interactive element with rating
]

# ---------------------------------------------------------------------------
# Rating selectors (display-only variant -- smaller set)
# ---------------------------------------------------------------------------
RATING_SELECTORS_DISPLAY_ONLY = [
    "span.yi40Hd",
    "span.MW4etd",
    ".BTtC6e",
    ".ceNzKf",
]

# ---------------------------------------------------------------------------
# Review count selectors
# ---------------------------------------------------------------------------
REVIEW_SELECTORS = [
    "span.RDApEe",                         # Primary review style
    "a[href*='reviews']",                  # Review link
    "span[aria-label*='review']",          # aria-label with 'review'
    "span[aria-label*='\u5247\u8a55\u8ad6']",  # Chinese '則評論' aria-label
]

# ---------------------------------------------------------------------------
# Address selectors for extract_address_from_maps_url (Selenium detail page)
# ---------------------------------------------------------------------------
MAPS_PAGE_ADDRESS_SELECTORS = [
    "button[data-item-id='address']",
    "div[data-attrid='kc:/location/location:address']",
    "span[data-attrid='kc:/location/location:address']",
    ".QSFF4-text",
    ".Io6YTe",
    "div.rogA2c",
    "button.CsEnBe",
]

# ---------------------------------------------------------------------------
# Walking tab selectors (for walking distance calculation page)
# ---------------------------------------------------------------------------
WALKING_TAB_SELECTORS = [
    "button[aria-label*='\u6b65\u884c']",                        # '步行'
    "div[role='tab'][aria-label*='\u6b65\u884c']",               # '步行'
    "button[jsaction][aria-controls*='section-directions']",
]

# ---------------------------------------------------------------------------
# Regex patterns used in text extraction
# ---------------------------------------------------------------------------

# Taiwan full address patterns (used in fallback text extraction)
ADDRESS_REGEX_PATTERNS = [
    # Complete: city/county + district + road/street + number + floor (optional)
    r'[\u4e00-\u9fff]*[市縣][\u4e00-\u9fff]*區[\u4e00-\u9fff]*[路街巷弄大道]\d+(?:[巷弄]\d+(?:弄\d+)?)?號(?:\d+樓|[A-Z]\d*[樓層]?)?',
    # Incomplete address but still useful
    r'[\u4e00-\u9fff]*[市縣區鄉鎮][\u4e00-\u9fff]*[路街巷弄大道](?:\d+[巷弄號])(?:(?!\d+號)\d*[樓層]?)*',
    # Address starting with city/county name
    r'[台新高桃台中南](?:[北中南]市|市|縣)[\u4e00-\u9fff]{1,10}[路街巷弄大道][^\s\n]*?號[^\s\n]*',
]

# Rating text patterns
RATING_TEXT_PATTERNS = [
    r'^(\d+\.?\d*)$',                     # Pure number: 4.5
    r'(\d+\.?\d*)\s*\u661f',              # Chinese: 4.5星
    r'(\d+\.?\d*)\s*star',                # English: 4.5 star
    r'(\d+\.?\d*)/5',                     # Fraction: 4.5/5
    r'(\d+\.?\d*)\s*out\s*of\s*5',        # Full: 4.5 out of 5
    r'\u8a55\u5206\s*(\d+\.?\d*)',         # 評分 4.5
]

# Rating patterns for aria-label / full-text fallback
RATING_ARIA_PATTERNS = [
    r'(\d+\.?\d*)\s*(?:\u661f|star|\u98a8\u661f)',  # 星/star/颗星
    r'rated\s*(\d+\.?\d*)',
    r'\u8a55\u5206[\uff1a:]\s*(\d+\.?\d*)',          # 評分：4.5
    r'(\d+\.?\d*)\s*/\s*5',
    r'^(\d+\.?\d*)$',
]

# Review count patterns
REVIEW_TEXT_PATTERNS = [
    r'\((\d+)\)',                          # (123)
    r'(\d+)\s*\u5247\u8a55\u8ad6',        # 123則評論
    r'(\d+)\s*reviews?',                   # 123 reviews
    r'(\d+)\s*\u8a55\u8ad6',              # 123評論
]

# Price patterns
PRICE_PATTERNS = [
    r'\$(\d{1,3}(?:,\d{3})*)-(\d{1,3}(?:,\d{3})*)',    # $800-1,000
    r'\$(\d{1,4})-(\d{1,4})',                             # $1-200
    r'\$(\d{2,4})-(\d{2,4})',                             # $100-300
    r'NT\$(\d{1,3}(?:,\d{3})*)-(\d{1,3}(?:,\d{3})*)',   # NT$800-1,000
    r'NT\$(\d{1,4})-(\d{1,4})',                           # NT$1-200
    r'(\d{1,3}(?:,\d{3})*)-(\d{1,3}(?:,\d{3})*)\u5143',  # 800-1,000元
    r'(\d{1,4})-(\d{1,4})\u5143',                         # 1-200元
    r'\$(\d{1,3}(?:,\d{3})*)\+',                          # $1,000+
    r'\$(\d{1,4})\+',                                     # $1+
    r'(\d{1,3}(?:,\d{3})*)\u5143',                        # 1,000元
    r'(\d{1,4})\u5143',                                   # 1元
]

# Walking distance patterns (line-level)
WALKING_DISTANCE_KM_PATTERN = r"(\d+)\s*\u5206[^\n]*?(\d+(?:\.\d+)?)\s*\u516c\u91cc"  # N分...N公里
WALKING_DISTANCE_M_PATTERN = r"(\d+)\s*\u5206[^\n]*?(\d+)\s*(?:\u516c\u5c3a|m)\b"      # N分...N公尺/m

# Hours-related keywords (used for open/closed detection)
CLOSED_KEYWORDS = [
    "\u5df2\u6b47\u696d",      # 已歇業
    "\u6c38\u4e45\u6b47\u696d",  # 永久歇業
    "\u66ab\u505c\u71df\u696d",  # 暫停營業
    "\u4f11\u606f\u4e2d",      # 休息中
    "\u5df2\u6253\u70ca",      # 已打烊
    "\u4eca\u65e5\u672a\u71df\u696d",  # 今日未營業
    "\u975e\u71df\u696d\u65e5",  # 非營業日
]

OPEN_KEYWORDS = [
    "\u71df\u696d\u4e2d",      # 營業中
    "24 \u5c0f\u6642\u71df\u696d",  # 24 小時營業
]
