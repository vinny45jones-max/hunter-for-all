FROM python:3.11-slim

# Playwright dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-liberation \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 \
    libnss3 libxcomposite1 libxdamage1 libxrandr2 xdg-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps

# App
COPY src/ src/

# Railway Volume mount point: /data
# В Railway dashboard: добавить Volume с mount path /data
RUN mkdir -p /data/screenshots

ENV DB_PATH=/data/hunter.db
ENV SESSION_PATH=/data/rabota_session.json

CMD ["python", "-m", "src.main"]
