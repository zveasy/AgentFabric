FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AGENTFABRIC_RENOVATION_STORAGE_DIR=/data/renovation-files

COPY pyproject.toml README.md /app/
COPY agentfabric /app/agentfabric
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()" || exit 1

RUN adduser --disabled-password --gecos "" --uid 10001 agentfabric
USER agentfabric

# Production: set AGENTFABRIC_DATABASE_URL, AGENTFABRIC_REDIS_URL, AGENTFABRIC_JWT_SECRET (and optionally
# AGENTFABRIC_ENVIRONMENT=production) via env or config. Mount /data for SQLite state and RenovationOS files.
# AGENTFABRIC_STATE_STORE_PATH and AGENTFABRIC_RENOVATION_STORAGE_DIR should both point at durable volumes.
CMD ["sh", "-c", "exec python -m agentfabric.cli api-run \
  --database-url \"${AGENTFABRIC_DATABASE_URL:-sqlite:///./agentfabric_api.db}\" \
  --redis-url \"${AGENTFABRIC_REDIS_URL:-redis://localhost:6379/0}\" \
  --jwt-secret \"${AGENTFABRIC_JWT_SECRET:-change-me-in-production}\" \
  --host 0.0.0.0 --port 8000"]
