FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Playwright (Chromium) + Postgres client + utilities the scrapers expect.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg curl ca-certificates postgresql-client \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libdrm2 libdbus-1-3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN python -m playwright install chromium

COPY . .

# Make the entrypoint executable. We rely on a script (not inline CMD) so the
# shell can actually expand ${PORT} that Railway injects at runtime.
RUN chmod +x /app/entrypoint.sh

EXPOSE 8080

CMD ["/app/entrypoint.sh"]
