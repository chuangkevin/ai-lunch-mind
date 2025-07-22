# 使用官方 Python runtime 作為基礎映像
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（Chrome 瀏覽器和相關工具）
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt 並安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .


# 暴露端口（Flask 預設 5000）
EXPOSE 5000

# 設定環境變數（確保 Chrome 在容器中正常運行）
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome

# 啟動流汗指數查詢伺服器
CMD ["python", "sweat_index_server.py"]
