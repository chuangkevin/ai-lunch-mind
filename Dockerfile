FROM node:20-slim

WORKDIR /app

# Install Chromium (works on ARM64/Raspberry Pi), CJK fonts, and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-noto-cjk \
    curl \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Tell Playwright to use system Chromium instead of downloading its own
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Install npm dependencies (including native better-sqlite3)
COPY package.json ./
# Use npm install instead of ci since we may not have a lockfile yet
RUN npm install --omit=optional

# Build TypeScript
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# Copy frontend (static HTML files)
COPY frontend ./frontend

ENV NODE_ENV=production
ENV PORT=9113

EXPOSE 9113

CMD ["node", "dist/server.js"]
