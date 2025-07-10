# AI 午餐推薦系統 - Docker 部署指南

## 🐳 Docker 容器化部署

### 快速啟動

1. **複製環境變數檔案**
```bash
cp .env.docker .env
```

2. **設定 API Keys**
編輯 `.env` 檔案，填入您的 API Keys：
```bash
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
CWB_API_KEY=your_cwb_api_key_here
```

3. **使用 Docker Compose 啟動**
```bash
docker-compose up -d
```

4. **訪問應用程式**
- 主應用程式: http://localhost:8000
- API 文檔: http://localhost:8000/docs
- 健康檢查: http://localhost:8000/health

### 單獨使用 Docker

```bash
# 建構映像
docker build -t ai-lunch-mind .

# 執行容器
docker run -d \
  --name ai-lunch-mind \
  -p 8000:8000 \
  --env-file .env \
  ai-lunch-mind
```

### 開發模式

```bash
# 開發模式啟動 (掛載本地程式碼)
docker-compose -f docker-compose.dev.yml up
```

### 管理指令

```bash
# 查看日誌
docker-compose logs -f ai-lunch-mind

# 停止服務
docker-compose down

# 重新建構並啟動
docker-compose up --build -d

# 進入容器
docker-compose exec ai-lunch-mind bash
```

## 🏗️ 架構說明

- **Python 3.11**: 最新穩定版本
- **FastAPI**: 高效能 API 框架  
- **Uvicorn**: ASGI 伺服器
- **Redis**: 快取服務 (可選)
- **健康檢查**: 自動監控容器狀態

## 🚀 生產環境部署

### 使用 Docker Swarm
```bash
docker stack deploy -c docker-compose.yml ai-lunch-mind
```

### 使用 Kubernetes
請參考 `k8s/` 目錄中的 YAML 檔案。

## 🔧 環境變數

| 變數名稱 | 說明 | 必需 |
|---------|------|------|
| `OPENAI_API_KEY` | OpenAI API 金鑰 | ✅ |
| `GOOGLE_MAPS_API_KEY` | Google Maps API 金鑰 | ✅ |
| `CWB_API_KEY` | 中央氣象署 API 金鑰 | ✅ |
| `DATABASE_URL` | 資料庫連接字串 | ❌ |
| `DEBUG` | 除錯模式 | ❌ |
| `LOG_LEVEL` | 日誌等級 | ❌ |

## 🛠️ 故障排除

### 健康檢查失敗
```bash
# 檢查容器狀態
docker-compose ps

# 查看詳細日誌
docker-compose logs ai-lunch-mind
```

### API 金鑰問題
確保 `.env` 檔案中的 API 金鑰正確設定且有效。

### 端口衝突
如果 8000 端口被占用，修改 `docker-compose.yml` 中的端口對應：
```yaml
ports:
  - "8080:8000"  # 使用 8080 端口
```
