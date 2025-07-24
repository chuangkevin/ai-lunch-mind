# 對話理解與條件分析模組
# 使用 OpenAI GPT-4o-mini 進行自然語言處理

from openai import OpenAI
import os
import json
import re
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 初始化 OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        system_prompt = """
你是一個專業的餐廳推薦需求分析助手。請仔細分析使用者的輸入，並同時回傳：
1. 食物類型（categories）：如：麵食、小吃、火鍋等
2. 具體食物（keywords）：如：拉麵、牛肉麵、鹽酥雞等，必須精確提取用戶明確指定的食物
3. 其他資訊（地點、預算、情境、店名等）

規則：
- 若用戶輸入「我想吃拉麵」，categories 必須包含「麵食」，keywords 必須包含「拉麵」
- 若用戶輸入「我想吃牛肉麵」，categories 必須包含「麵食」，keywords 必須包含「牛肉麵」
- 若用戶輸入「我想吃火鍋」，categories 必須包含「火鍋」，keywords 必須包含「火鍋」
- 若用戶輸入「我想吃鹽酥雞」，categories 必須包含「小吃」，keywords 必須包含「鹽酥雞」
- 若用戶輸入「我在西門町找燒烤」，categories 必須包含「燒烤」，keywords 必須包含「燒烤」

請以 JSON 格式回傳分析結果，結構如下：
{
  "location": {
    "address": "提取的地址/地點名稱，如果沒有則為 null",
    "google_maps_url": "Google Maps 網址，如果有的話", 
    "coordinates": "座標（如果能識別），格式: 'lat,lng'"
  },
  "food_preferences": {
    "categories": ["食物類型陣列，如: 小吃, 麵食, 火鍋, 便當等"],
    "keywords": ["具體食物關鍵字陣列，如: 拉麵, 牛肉麵, 鹽酥雞, 火鍋等"],
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
- 「我想吃拉麵」→ food_preferences.categories: ["麵食"], food_preferences.keywords: ["拉麵"], intent: "search_food_type"
- 「我想吃牛肉麵」→ food_preferences.categories: ["麵食"], food_preferences.keywords: ["牛肉麵"], intent: "search_food_type"
- 「我想吃火鍋」→ food_preferences.categories: ["火鍋"], food_preferences.keywords: ["火鍋"], intent: "search_food_type"
- 「我想吃鹽酥雞」→ food_preferences.categories: ["小吃"], food_preferences.keywords: ["鹽酥雞"], intent: "search_food_type"
- 「我在西門町找燒烤」→ location.address: "西門町", food_preferences.categories: ["燒烤"], food_preferences.keywords: ["燒烤"], intent: "search_restaurants"
- 「信義區的麥當勞」→ location.address: "信義區", food_preferences.restaurant_name: "麥當勞", intent: "search_specific_store"

請只回傳 JSON，不要有其他說明文字。
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=0.1
        )
        result_text = response.choices[0].message.content.strip()
        # 嘗試解析 JSON
        try:
            parsed_result = json.loads(result_text)
            # 後處理：若 keywords 未包含 user_input 的明確品項，自動補上
            food_prefs = parsed_result.get("food_preferences", {})
            keywords = food_prefs.get("keywords", [])
            # 只取 user_input 中的明確食物詞（如麻辣鍋、牛肉麵、拉麵等）
            # 這裡用簡單正則抽取
            import re
            explicit_foods = re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]+鍋|牛肉麵|拉麵|義大利麵|牛排|披薩|漢堡|炸雞|壽司|天婦羅|刺身|燒烤|臭豆腐|雞排|鴨頭|蚵仔煎|滷肉飯|涼麵|蛋餅|三明治|咖啡|甜點|小吃|便當|湯麵|意麵|火鍋|炸物|布丁|蛋糕|雪花冰|芒果冰|果汁|奶茶|美式|拿鐵|沙拉|煲湯|湯品|餐盒|飯盒|烤肉|燒肉|炒菜|合菜|定食|早午餐|宵夜|泡麵|居酒屋|咖啡廳|餐廳", user_input)
            for food in explicit_foods:
                if food not in keywords:
                    keywords.append(food)
            food_prefs["keywords"] = keywords
            parsed_result["food_preferences"] = food_prefs
            return {
                "success": True,
                "analysis": parsed_result,
                "raw_response": result_text
            }
        except json.JSONDecodeError:
            # 如果 JSON 解析失敗，直接回傳錯誤
            return {
                "success": False,
                "error": "JSON parsing failed",
                "raw_response": result_text
            }
    except Exception as e:
        print(f"❌ ChatGPT 分析錯誤: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def extract_search_keywords_from_analysis(analysis_result):
    """
    從分析結果中提取搜尋關鍵字
    """
    if not analysis_result.get("success"):
        return []  # 失敗時不回傳預設關鍵字

    # 取得分析數據
    data = analysis_result["analysis"]

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

    return []  # 不回傳預設關鍵字

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
        return {}
