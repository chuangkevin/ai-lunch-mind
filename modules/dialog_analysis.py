# 對話理解與條件分析模組
# 使用 OpenAI GPT-4o-mini 進行自然語言處理

import openai
import os

# 初始化 OpenAI API 金鑰
openai.api_key = os.getenv("OPENAI_API_KEY")

def analyze_user_input(user_input):
    """
    分析使用者輸入的自然語言，提取需求條件。
    :param user_input: str, 使用者的輸入文字
    :return: dict, 提取的需求條件
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個專業的需求分析助手。"},
                {"role": "user", "content": f"分析以下文字並提取需求條件：{user_input}"}
            ]
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Error in analyzing user input: {e}")
        return {}

# TODO: 添加更多對話分析功能
