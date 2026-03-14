FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md /app/
COPY agentfabric /app/agentfabric
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && ARCH="$(dpkg --print-architecture)" \
    && case "${ARCH}" in \
        amd64) COSIGN_ARCH="amd64" ;; \
        arm64) COSIGN_ARCH="arm64" ;; \
        *) echo "Unsupported architecture for cosign: ${ARCH}" && exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/sigstore/cosign/releases/latest/download/cosign-linux-${COSIGN_ARCH}" -o /usr/local/bin/cosign \
    && chmod +x /usr/local/bin/cosign \
    && cosign version \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "agentfabric.cli", "api-run", "--database-url", "sqlite:///./agentfabric_api.db", "--host", "0.0.0.0", "--port", "8000"]
