FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HHIP_DATA_DIR=/tmp/hhip-data
ENV FIREBASE_CREDENTIALS=/app/credentials/firebase-adminsdk.json
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/firebase-adminsdk.json
ENV COOKIE_SECURE=true
ENV COOKIE_SAMESITE=none
ENV HHIP_FIRMWARE_DRY_RUN=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/hhip-data

EXPOSE 8080

CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}
