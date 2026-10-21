# 阶段 1：构建前端
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend-build
WORKDIR /app

COPY web/package*.json ./web/
RUN cd web && npm ci

COPY web/ ./web/
RUN cd web && npm run build

# 阶段 2：构建后端运行环境
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app

ARG BUILD_DATE=""
ARG BUILD_VERSION=""
ARG VCS_REF=""

LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.version=$BUILD_VERSION \
      org.opencontainers.image.revision=$VCS_REF

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    DEBIAN_FRONTEND=noninteractive

ARG APT_MIRROR=""
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s@deb.debian.org@$APT_MIRROR@g" /etc/apt/sources.list.d/debian.sources ; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      libgl1 \
      libglib2.0-0 \
      ca-certificates \
      tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY server/requirements.txt ./
ARG PIP_INDEX_URL=""
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      python -m pip install --no-cache-dir -r requirements.txt -i "$PIP_INDEX_URL" ; \
    else \
      python -m pip install --no-cache-dir -r requirements.txt ; \
    fi

COPY server/ ./server/
COPY alembic.ini ./alembic.ini
COPY --from=frontend-build /app/web/dist ./web/dist

ARG DOWNLOAD_MODELS=0
RUN if [ "$DOWNLOAD_MODELS" = "1" ]; then \
      python -c "from server.util.CaptchaUtils import ensure_model_exists, MODEL_URLS; [ensure_model_exists(k,v) for k,v in MODEL_URLS.items()]" ; \
    fi

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser && \
    mkdir -p /app/server/images /app/server/models_onnx && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8147

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8147/healthz', timeout=5).read()" || exit 1

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8147"]
