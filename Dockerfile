# Kropka: one small container. Works on Render, Railway and Fly.io.
#
#   docker build -t kropka .
#   docker run -p 8000:8000 -e DEVICE_SALT=change-me kropka
#
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KROPKA_DB=/app/data/kropka.db

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user, not root.
RUN useradd --create-home kropka && chown -R kropka /app
USER kropka

EXPOSE 8000

# 1) seed the database if it is empty, 2) start the web server.
# --proxy-headers: the host terminates HTTPS in front of us; trust its X-Forwarded-Proto
# so the app knows the page is HTTPS (secure cookie). PORT is set by the host (Render: 10000).
CMD ["sh", "-c", "python -m scripts.bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
