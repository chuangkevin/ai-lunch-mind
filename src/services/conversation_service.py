"""
AI 對話理解服務
使用 OpenAI GPT 進行自然語言處理
"""
from openai import AsyncOpenAI
from typing import Dict, Any, Optional
import json
from src.config import settings
from src.models import UserQuery, UserPreferences, PriceLevel, CrowdLevel

class ConversationService:
    """對話理解服務"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def parse_user_query(self, user_input: str) -> Dict[str, Any]:
        """解析使用者輸入，擷取需求條件"""
        
        system_prompt = """
你是一個專業的餐廳推薦助手。請分析使用者的輸入，提取以下資訊並以JSON格式回應：

{
    "budget": "budget|moderate|expensive|luxury",
    "cuisine_preferences": ["中式", "日式", "韓式", "義式", "美式", "泰式", "速食", "咖啡廳"],
    "crowd_preference": "quiet|moderate|busy|very_busy",
    "weather_sensitive": true|false,
    "dietary_restrictions": ["素食", "清真", "無麩質"],
    "meal_type": "breakfast|lunch|dinner|snack",
    "special_requirements": ["約會", "商務", "家庭聚餐", "快速用餐"],
    "mood": "想嘗試新的|想吃熟悉的|隨便都可以",
    "distance_preference": "很近|走路可到|可以搭車"
}

請根據使用者的自然語言輸入推斷這些偏好。如果無法確定某項，請設為null。
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                max_tokens=settings.max_tokens,
                temperature=settings.temperature
            )
            
            content = response.choices[0].message.content
            parsed_data = json.loads(content)
            
            return parsed_data
            
        except Exception as e:
            print(f"查詢解析失敗: {e}")
            return {}
    
    async def generate_recommendation_explanation(
        self, 
        user_query: str,
        weather_info: str,
        recommendations: list
    ) -> str:
        """產生推薦說明"""
        
        system_prompt = """
你是一個親切的餐廳推薦助手。根據使用者的需求、天氣狀況和推薦結果，
生成一段自然、個人化的推薦說明。

說明應該：
1. 考慮天氣因素對用餐的影響
2. 解釋為什麼推薦這些餐廳
3. 提及距離、價格、特色等因素
4. 語調親切、實用

請用繁體中文回應，長度控制在100-200字內。
"""
        
        restaurants_summary = []
        for rec in recommendations[:3]:  # 只取前3個推薦
            restaurants_summary.append({
                "name": rec["restaurant"]["name"],
                "reasons": rec["reasons"],
                "distance": rec["distance"]
            })
        
        user_message = f"""
使用者需求: {user_query}
天氣狀況: {weather_info}
推薦餐廳摘要: {json.dumps(restaurants_summary, ensure_ascii=False)}
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"說明生成失敗: {e}")
            return "根據您的需求和當前天氣，我為您推薦了幾家不錯的餐廳選擇。"
    
    async def analyze_review_sentiment(self, reviews: list) -> Dict[str, Any]:
        """分析評論情緒和特徵"""
        
        if not reviews:
            return {"sentiment": "neutral", "features": {}}
        
        reviews_text = "\n".join([review.text for review in reviews[:10]])  # 取前10則評論
        
        system_prompt = """
分析以下餐廳評論，提取關鍵特徵並以JSON格式回應：

{
    "sentiment": "positive|neutral|negative",
    "features": {
        "air_conditioning": "strong|moderate|weak|unknown",
        "noise_level": "quiet|moderate|noisy|unknown",
        "service_quality": "excellent|good|average|poor|unknown",
        "food_quality": "excellent|good|average|poor|unknown",
        "cleanliness": "excellent|good|average|poor|unknown",
        "good_for_date": true|false|unknown,
        "family_friendly": true|false|unknown,
        "quick_service": true|false|unknown
    },
    "key_points": ["正面評價重點", "負面評價重點"]
}
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": reviews_text}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            print(f"評論分析失敗: {e}")
            return {"sentiment": "neutral", "features": {}}

# 全域服務實例
conversation_service = ConversationService()
