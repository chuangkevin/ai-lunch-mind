@echo off
echo 🍱 AI 午餐推薦系統 - Windows 快速啟動腳本
echo ==========================================

REM 檢查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安裝，請先安裝 Python 3.8+
    pause
    exit /b 1
)

REM 建立虛擬環境 (如果不存在)
if not exist "venv" (
    echo 📦 建立虛擬環境...
    python -m venv venv
)

REM 啟動虛擬環境
echo 🔧 啟動虛擬環境...
call venv\Scripts\activate.bat

REM 安裝依賴
echo 📥 安裝依賴套件...
pip install -r requirements.txt

REM 檢查環境變數檔案
if not exist ".env" (
    echo ⚠️  請先設定 .env 檔案 (可從 .env.example 複製)
    echo 需要設定以下 API Keys:
    echo - OPENAI_API_KEY
    echo - GOOGLE_MAPS_API_KEY
    echo - OPENWEATHER_API_KEY
    pause
    exit /b 1
)

REM 執行測試
echo 🧪 執行基本測試...
python tests\test_basic.py

REM 啟動服務
echo 🚀 啟動 API 服務...
echo 前端頁面: http://localhost:8000 (將在瀏覽器中打開)
echo API 文件: http://localhost:8000/docs
echo.

REM 啟動瀏覽器
start http://localhost:8000

REM 啟動服務
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

pause
