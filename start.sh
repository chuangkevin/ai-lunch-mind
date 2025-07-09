#!/bin/bash

echo "🍱 AI 午餐推薦系統 - 快速啟動腳本"
echo "=================================="

# 檢查 Python
if ! command -v python &> /dev/null; then
    echo "❌ Python 未安裝，請先安裝 Python 3.8+"
    exit 1
fi

# 建立虛擬環境 (如果不存在)
if [ ! -d "venv" ]; then
    echo "📦 建立虛擬環境..."
    python -m venv venv
fi

# 啟動虛擬環境
echo "🔧 啟動虛擬環境..."
source venv/bin/activate

# 安裝依賴
echo "📥 安裝依賴套件..."
pip install -r requirements.txt

# 檢查環境變數檔案
if [ ! -f ".env" ]; then
    echo "⚠️  請先設定 .env 檔案 (可從 .env.example 複製)"
    echo "需要設定以下 API Keys:"
    echo "- OPENAI_API_KEY"
    echo "- GOOGLE_MAPS_API_KEY" 
    echo "- OPENWEATHER_API_KEY"
    exit 1
fi

# 執行測試
echo "🧪 執行基本測試..."
python tests/test_basic.py

# 啟動服務
echo "🚀 啟動 API 服務..."
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
