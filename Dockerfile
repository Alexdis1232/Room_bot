FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY room_bot.py .

# ROOM_BOT_STORAGE=mongo, MONGODB_URI, TG_BOT_TOKEN, TG_MY_CHAT_ID,
# TELEGRAM_WEBHOOK_SECRET, SCAN_SECRET — заданы через переменные окружения
# хостинга (Render Dashboard → Environment), не здесь: тот же образ подходит
# и для файлового режима (тогда просто не передавай ROOM_BOT_STORAGE и
# смонтируй диск), не нужно пересобирать под разные бэкенды хранения.
# Порт хостинг передаёт через $PORT (Render/Cloud Run — оба так делают,
# по умолчанию 8080, если переменной нет)
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 4 --timeout 0 room_bot:app
