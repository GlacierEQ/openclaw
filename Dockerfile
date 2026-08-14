FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /build
COPY pyproject.toml README.md LICENSE LICENSE_NOTICE.md ./
COPY src ./src
COPY cli.py server.py mcp_server.py mastermind_sidecar.py ./
RUN python -m pip wheel --no-cache-dir . -w /wheels

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* && rm -rf /wheels \
    && useradd --create-home --uid 10001 openclaw \
    && mkdir -p /app/.openclaw \
    && chown -R openclaw:openclaw /app
USER openclaw
EXPOSE 8088 8089
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=2).read()" || exit 1
CMD ["openclaw-api", "--host", "0.0.0.0", "--port", "8088"]
