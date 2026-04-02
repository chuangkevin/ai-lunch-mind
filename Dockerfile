FROM python:3.12-slim

WORKDIR /app

# Install Chromium (works on ARM64/Raspberry Pi) + CJK fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver \
    fonts-noto-cjk \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV CHROME_BIN=/usr/bin/chromium

EXPOSE 9113

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9113", "--log-level", "info"]
