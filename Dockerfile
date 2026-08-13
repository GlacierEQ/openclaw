FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 openclaw && mkdir -p /app/.openclaw && chown -R openclaw:openclaw /app
USER openclaw
EXPOSE 8088 8089
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=2).read()" || exit 1
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8088"]
