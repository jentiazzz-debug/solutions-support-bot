FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# tini — корректная передача SIGTERM (graceful shutdown),
# fonts-dejavu-core — кириллица на графиках статистики.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN useradd --uid 1000 --create-home bot \
    && mkdir -p /app/data /app/logs \
    && chown -R bot:bot /app/data /app/logs
USER bot

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["tini", "--"]
CMD ["python", "main.py"]
