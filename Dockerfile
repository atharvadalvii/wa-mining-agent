# Container image for the Streamlit dashboard: runs on Hugging Face Spaces (free) or
# AWS ECS Fargate.
#
# The offline WA street network (~600 MB of tables plus a 109 MB .pbf) is NOT baked into
# the image. The entrypoint downloads it at startup, from a Hugging Face dataset
# (GEOAGENT_DATA_HF_REPO) or an S3 prefix (GEOAGENT_DATA_S3_URI). That keeps the image
# small and lets the data change without a rebuild.
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -e ".[dashboard,local-wa,aws,hf]"

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && useradd --create-home app \
    && mkdir -p /app/maps /app/.cache /app/data \
    && chown -R app:app /app
USER app

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
