# 對話理解與條件分析模組
# 使用 OpenAI GPT-4o-mini 進行自然語言處理

import openai
import os
import json
import re
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 檢查 OpenAI 版本並進行兼容性處理
try:
    # 嘗試新版本導入
    from openai import OpenAI
    # 新版本 (1.0+)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OPENAI_VERSION = "new"
except ImportError:
    # 舊版本 (0.x)
    openai.api_key = os.getenv("OPENAI_API_KEY")
    client = None
    OPENAI_VERSION = "old"

print(f"OpenAI version detected: {OPENAI_VERSION} (openai {openai.__version__})")

# 食物類型模式字典（備用關鍵字檢測）
FOOD_PATTERNS = {
    "冰品": ["冰", "剉冰", "冰品", "冰店", "雪花冰", "芒果冰"],
    "甜點": ["甜點", "蛋糕", "布丁", "甜湯", "仙草"],
    "飲料": ["飲料", "奶茶", "果汁", "氣泡水"],
    "咖啡廳": ["咖啡", "拿鐵", "美式"],
    "早餐": ["早餐", "蛋餅", "三明治", "土司", "漢堡"],
    "火鍋": ["火鍋", "麻辣鍋", "涮涮鍋"],
    "燒烤": ["燒烤", "烤肉", "燒肉"],
    "熱炒": ["熱炒", "炒菜", "合菜"],
    "臭豆腐": ["臭豆腐"],
    "便當": ["便當", "飯盒", "餐盒"],
    "麵食": ["麵", "拉麵", "意麵", "湯麵", "義大利麵", "pasta", "牛肉麵", "擔仔麵", "陽春麵"],
    "小吃": ["小吃", "點心", "東山鴨頭", "鹽酥雞", "雞排"],
    "輕食": ["輕食", "沙拉", "三明治"],
    "湯品": ["湯", "煲湯", "湯麵"],
}

def analyze_user_request(user_input):
    """
    使用 ChatGPT 分析使用者輸入，提取位置、預算、需求等資訊
    :param user_input: str, 使用者的輸入文字
    :return: dict, 結構化的需求分析結果
    """
    # 檢查AI分析快取
    try:
        from modules.cache_manager import get_ai_cache, set_ai_cache
        cached_analysis = get_ai_cache(user_input, "dialog_analysis")
        if cached_analysis:
            return cached_analysis
    except Exception as e:
        print(f"AI分析快取系統不可用: {e}")
    
    try:
        system_prompt = """你是一個專業的餐廳推薦需求分析助手。請仔細分析使用者的輸入，特別注意以下重點：

1. 地標位置 vs 店名 vs 地名 vs 食物類型：
   - 「屏東海生館」→ 地區：屏東海生館（知名地標），intent: "location_query"
   - 「台北101」→ 地區：台北101（知名地標），intent: "location_query"  
   - 「龜山區東山鴨頭」→ 地區：龜山區，食物類型：東山鴨頭，intent: "search_food_type"
   - 「西門町麥當勞」→ 地區：西門町，店名：麥當勞，intent: "search_specific_store"
   - 「台北牛肉麵」→ 地區：台北，食物類型：牛肉麵，intent: "search_food_type"

2. 重要地標識別（這些輸入應標記為 location_query）：
   - 博物館/美術館：故宮、海生館、科博館、美術館等
   - 知名景點：101、小巨蛋、西門町、夜市等
   - 車站/機場：台北車站、桃園機場、高鐵站等
   - 學校/醫院：台大、榮總、長庚等
   - 商場/百貨：信義威秀、京站、大遠百等

3. 食物類型識別（注意：需要同時提取大類和具體類型）：
   - 東山鴨頭、鹽酥雞、雞排、臭豆腐 → 小吃類，具體關鍵字：東山鴨頭、鹽酥雞等
   - 牛肉麵、拉麵、義大利麵、意麵 → 麵食類，具體關鍵字：牛肉麵、拉麵、義大利麵等
   - 滷肉飯、便當 → 台式料理，具體關鍵字：滷肉飯、便當等
   - 火鍋、燒烤、熱炒 → 正餐類，具體關鍵字：火鍋、燒烤、熱炒等

4. 連鎖店識別：麥當勞、星巴克、肯德基等知名連鎖品牌

**重要判斷原則：**
- 如果輸入只是地標名稱（如：屏東海生館、台北101），應標記為 location_query
- 如果輸入包含食物關鍵字，才標記為 search_food_type 或 search_restaurants
- 當用戶提到具體食物名稱時，必須在 keywords 陣列中包含該具體名稱

請提取以下資訊並以 JSON 格式回傳：

{
  "location": {
    "address": "提取的地址/地點名稱，如果沒有則為 null",
    "google_maps_url": "Google Maps 網址，如果有的話", 
    "coordinates": "座標（如果能識別），格式: 'lat,lng'"
  },
  "food_preferences": {
    "categories": ["食物類型陣列，如: 小吃, 麵食, 火鍋, 便當等"],
    "keywords": ["具體食物關鍵字陣列，如: 東山鴨頭, 牛肉麵, 鹽酥雞等"],
    "mood_context": "用戶的情境描述，如：天氣熱想吃冰、肚子餓等",
    "restaurant_name": "如果輸入包含連鎖店名，提取店名（如：麥當勞、星巴克等）"
  },
  "budget": {
    "min": 最低預算數字，沒有則為 null,
    "max": 最高預算數字，沒有則為 null,
    "currency": "TWD"
  },
  "constraints": {
    "time_preference": "時間偏好，如: 早餐, 午餐, 晚餐, 宵夜",
    "special_requirements": ["特殊需求陣列，如: 素食, 無辣, 外帶等"]
  },
  "intent": "用戶意圖分類: search_restaurants, search_specific_store, search_food_type, location_query"
}

範例分析：
- 「屏東海生館」→ location.address: "屏東海生館", food_preferences.keywords: [], food_preferences.categories: [], intent: "location_query"
- 「台北101」→ location.address: "台北101", food_preferences.keywords: [], food_preferences.categories: [], intent: "location_query"
- 「龜山區東山鴨頭」→ location.address: "龜山區", food_preferences.keywords: ["東山鴨頭"], food_preferences.categories: ["小吃", "滷味"], intent: "search_food_type"
- 「我在西門町找燒烤」→ location.address: "西門町", food_preferences.keywords: ["燒烤"], food_preferences.categories: ["燒烤"], intent: "search_restaurants"
- 「信義區的麥當勞」→ location.address: "信義區", food_preferences.restaurant_name: "麥當勞", intent: "search_specific_store"
- 「中山區想吃義大利麵」→ location.address: "中山區", food_preferences.keywords: ["義大利麵"], food_preferences.categories: ["麵食"], intent: "search_food_type"
- 「台北牛肉麵」→ location.address: "台北", food_preferences.keywords: ["牛肉麵"], food_preferences.categories: ["麵食"], intent: "search_food_type"

請只回傳 JSON，不要有其他說明文字。"""

        # 版本兼容的 API 調用
        if OPENAI_VERSION == "new":
            # 新版本 (1.0+) 格式
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1
            )
            result_text = response.choices[0].message.content.strip()
        else:
            # 舊版本 (0.x) 格式  
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1
            )
            result_text = response['choices'][0]['message']['content'].strip()
        
        # 嘗試解析 JSON
        try:
            parsed_result = json.loads(result_text)
            analysis_result = {
                "success": True,
                "analysis": parsed_result,
                "raw_response": result_text
            }
            
            # 將結果存入快取
            try:
                set_ai_cache(user_input, analysis_result, "dialog_analysis")
            except Exception as e:
                print(f"AI分析快取保存失敗: {e}")
            
            return analysis_result
        except json.JSONDecodeError:
            # 如果 JSON 解析失敗，回傳基本分析
            return {
                "success": False,
                "error": "JSON parsing failed",
                "raw_response": result_text,
                "fallback_analysis": _fallback_analysis(user_input)
            }
            
    except Exception as e:
        print(f"❌ ChatGPT 分析錯誤: {e}")
        return {
            "success": False,
            "error": str(e),
            "fallback_analysis": _fallback_analysis(user_input)
        }

def _fallback_analysis(user_input):
    """
    當 ChatGPT 分析失敗時的備用分析方法
    """
    user_lower = user_input.lower()
    
    # 先檢查是否為純地標查詢
    landmark_keywords = [
        '海生館', '101', '車站', '機場', '夜市', '博物館', '美術館', 
        '故宮', '小巨蛋', '威秀', '京站', '遠百', '大學', '醫院',
        '高鐵', '捷運', '商場', '百貨', '科博館'
    ]
    
    # 如果輸入只包含地標關鍵字而沒有食物關鍵字，判定為位置查詢
    has_landmark = any(keyword in user_input for keyword in landmark_keywords)
    has_food_keyword = any(food_type in user_lower for food_types in FOOD_PATTERNS.values() for food_type in food_types)
    
    if has_landmark and not has_food_keyword:
        # 提取位置
        location = None
        location_patterns = [
            r'([^，。！？\s]*(?:海生館|101|車站|機場|夜市|博物館|美術館|故宮|小巨蛋|威秀|京站|遠百|大學|醫院|高鐵|捷運|商場|百貨|科博館))',
            r'([^，。！？\s]*(?:區|站|路|街|市|縣|大樓|商場|夜市))',
            r'(台北\w+|高雄\w+|台中\w+|台南\w+|屏東\w+)',
        ]
        for pattern in location_patterns:
            matches = re.findall(pattern, user_input)
            if matches:
                location = {"address": matches[0]}
                break
        
        return {
            "location": location or {"address": user_input.strip()},
            "food_preferences": {
                "categories": [],
                "keywords": [],
                "mood_context": None
            },
            "budget": None,
            "constraints": {},
            "intent": "location_query"  # 關鍵：標記為位置查詢
        }
    
    # 原有的食物類型分析邏輯
    food_categories = []
    if any(word in user_lower for word in ['冰', '剉冰', '冰品']):
        food_categories.append('冰品')
    if any(word in user_lower for word in ['甜點', '蛋糕', '布丁']):
        food_categories.append('甜點')
    if '火鍋' in user_lower:
        food_categories.append('火鍋')
    if '便當' in user_lower:
        food_categories.append('便當')
    if any(word in user_lower for word in ['咖啡', '拿鐵']):
        food_categories.append('咖啡廳')
    
    # 提取位置
    location = None
    if 'maps.app.goo.gl' in user_input or 'google.com/maps' in user_input:
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, user_input)
        if urls:
            location = {"google_maps_url": urls[0]}
    else:
        # 地點名稱匹配
        location_patterns = [
            r'([^，。！？\s]*(?:區|站|路|街|市|縣|101|大樓|商場|夜市))',
            r'(台北\w+|高雄\w+|台中\w+|台南\w+)',
        ]
        for pattern in location_patterns:
            matches = re.findall(pattern, user_input)
            if matches:
                location = {"address": matches[0]}
                break
    
    # 預算提取
    budget_pattern = r'(\d+)\s*(?:元|塊|dollar)'
    budget_matches = re.findall(budget_pattern, user_lower)
    budget = None
    if budget_matches:
        amounts = [int(m) for m in budget_matches]
        if len(amounts) == 1:
            budget = {"max": amounts[0], "currency": "TWD"}
        elif len(amounts) == 2:
            budget = {"min": min(amounts), "max": max(amounts), "currency": "TWD"}
    
    return {
        "location": location,
        "food_preferences": {
            "categories": food_categories,
            "keywords": [],
            "mood_context": "熱" if "熱" in user_lower else None
        },
        "budget": budget,
        "constraints": {},
        "intent": "search_restaurants"
    }

def extract_search_keywords_from_analysis(analysis_result):
    """
    從分析結果中提取搜尋關鍵字
    """
    if not analysis_result.get("success") and not analysis_result.get("fallback_analysis"):
        return ["便當", "小吃"]  # 預設關鍵字
    
    # 取得分析數據
    if analysis_result.get("success"):
        data = analysis_result["analysis"]
    else:
        data = analysis_result["fallback_analysis"]
    
    # 檢查意圖類型
    intent = data.get("intent", "search_restaurants")
    
    # 如果是位置查詢（純地標），使用通用餐廳類型
    if intent == "location_query":
        return ["餐廳", "小吃", "便當"]  # 適合地標附近的通用搜尋
    
    # 優先使用具體的食物關鍵字
    keywords = data.get("food_preferences", {}).get("keywords", [])
    if keywords:
        return keywords[:3]  # 限制最多3個具體關鍵字
    
    # 如果沒有具體關鍵字，使用食物類型
    categories = data.get("food_preferences", {}).get("categories", [])
    if categories:
        return categories[:3]  # 限制最多3個類型
    
    # 如果沒有明確類型，根據情境推薦
    mood = data.get("food_preferences", {}).get("mood_context", "")
    if "熱" in mood:
        return ["冰品", "涼麵", "甜點"]
    elif "冷" in mood:
        return ["火鍋", "熱炒", "湯品"]
    
    return ["便當", "小吃", "輕食"]  # 預設關鍵字

def detect_food_keywords_fallback(user_input):
    """
    使用關鍵字模式進行備用食物類型檢測
    :param user_input: str, 使用者輸入
    :return: list, 檢測到的食物類型列表
    """
    user_lower = user_input.lower()
    detected_keywords = []
    
    for food_type, patterns in FOOD_PATTERNS.items():
        for pattern in patterns:
            if pattern in user_lower:
                detected_keywords.append(food_type)
                break
    
    # 去重並限制數量
    unique_keywords = list(dict.fromkeys(detected_keywords))[:3]
    return unique_keywords

def get_weather_based_keywords(sweat_index, temperature):
    """
    根據天氣狀況推薦關鍵字
    :param sweat_index: float, 流汗指數
    :param temperature: float, 溫度
    :return: list, 推薦的關鍵字
    """
    try:
        sweat_index = float(sweat_index) if sweat_index is not None else 50
        temperature = float(temperature) if temperature is not None else 25
    except (ValueError, TypeError):
        sweat_index = 50
        temperature = 25
    
    if sweat_index > 60 or temperature > 28:
        return ["便當", "輕食", "涼麵", "小吃"]
    elif temperature < 20:
        return ["便當", "麵食", "火鍋", "熱炒", "湯品"]
    else:
        return ["便當", "麵食", "小吃", "熱炒"]

# 保持向後兼容
def analyze_user_input(user_input):
    """
    舊版API，保持向後兼容
    """
    result = analyze_user_request(user_input)
    if result.get("success"):
        return result["analysis"]
    else:
        return result.get("fallback_analysis", {})
