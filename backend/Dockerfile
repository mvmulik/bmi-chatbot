FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY crawler/requirements.txt /tmp/crawler-requirements.txt
COPY processor/requirements.txt /tmp/processor-requirements.txt

RUN pip install --upgrade pip \
    && pip install -r /tmp/backend-requirements.txt \
    && pip install -r /tmp/crawler-requirements.txt \
    && pip install -r /tmp/processor-requirements.txt

COPY backend ./backend
COPY crawler ./crawler
COPY processor ./processor
COPY scripts ./scripts
COPY pytest.ini ./pytest.ini

RUN mkdir -p /data/raw /data/processed /data/chroma /data/auth

WORKDIR ${APP_HOME}/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
