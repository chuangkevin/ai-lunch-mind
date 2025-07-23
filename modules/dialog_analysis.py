# 對話理解與條件分析模組
# 使用 OpenAI GPT-4o-mini 進行自然語言處理

import openai
import os
import json
import re
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 初始化 OpenAI API 金鑰
openai.api_key = os.getenv("OPENAI_API_KEY")

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
    "麵食": ["麵", "拉麵", "意麵", "湯麵"],
    "小吃": ["小吃", "點心"],
    "輕食": ["輕食", "沙拉", "三明治"],
    "湯品": ["湯", "煲湯", "湯麵"],
}

def analyze_user_request(user_input):
    """
    使用 ChatGPT 分析使用者輸入，提取位置、預算、需求等資訊
    :param user_input: str, 使用者的輸入文字
    :return: dict, 結構化的需求分析結果
    """
    try:
        system_prompt = """你是一個專業的餐廳推薦需求分析助手。請仔細分析使用者的輸入，特別注意以下重點：

1. 店名 vs 地名 vs 食物類型：
   - 「龜山區東山鴨頭」→ 地區：龜山區，食物類型：東山鴨頭（是滷味/鴨頭類小吃）
   - 「西門町麥當勞」→ 地區：西門町，店名：麥當勞
   - 「台北牛肉麵」→ 地區：台北，食物類型：牛肉麵

2. 食物類型識別：
   - 東山鴨頭、鹽酥雞、雞排、臭豆腐 → 小吃類
   - 牛肉麵、拉麵、意麵 → 麵食類
   - 滷肉飯、便當 → 台式料理
   - 火鍋、燒烤、熱炒 → 正餐類

3. 連鎖店識別：麥當勞、星巴克、肯德基等知名連鎖品牌

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
- 「龜山區東山鴨頭」→ location.address: "龜山區", food_preferences.keywords: ["東山鴨頭"], food_preferences.categories: ["小吃", "滷味"], intent: "search_food_type"
- 「我在西門町找燒烤」→ location.address: "西門町", food_preferences.categories: ["燒烤"], intent: "search_restaurants"
- 「信義區的麥當勞」→ location.address: "信義區", food_preferences.restaurant_name: "麥當勞", intent: "search_specific_store"

請只回傳 JSON，不要有其他說明文字。"""

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
            return {
                "success": True,
                "analysis": parsed_result,
                "raw_response": result_text
            }
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
    
    # 簡單的關鍵字匹配
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
    
    # 提取食物類型
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
