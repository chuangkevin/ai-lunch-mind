REM 本地開發環境依賴安裝腳本
REM 注意：此腳本僅用於本地開發，容器化部署請使用 Docker

echo "🚀 安裝 AI 餐廳推薦系統本地開發依賴..."

REM 核心框架
pip install fastapi uvicorn[standard] python-dotenv

REM 餐廳搜尋相關依賴
pip install selenium beautifulsoup4 geopy requests urllib3 webdriver-manager

echo "✅ 依賴安裝完成！"
echo "📝 接下來："
echo "   1. 設定 .env 檔案（CWB_API_TOKEN）"
echo "   2. 執行 python main.py 啟動服務"
echo "   3. 容器化部署請使用: docker-compose up --build"
