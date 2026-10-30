FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    MUJ_CONFIG=/state/config/config.json \
    MUJ_DATA_DIR=/state/data \
    MUJ_PRIVATE_DIR=/state/private \
    MUJ_DEPLOYED=1 \
    PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /opt/studyspace
COPY pyproject.toml requirements.txt config.example.json dashboard.py README.md ./
COPY muj_study/ ./muj_study/
COPY assets/ ./assets/
COPY deploy/ ./deploy/
RUN python -m pip install -e . \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 studyspace \
    && useradd --uid 10001 --gid studyspace --create-home studyspace \
    && mkdir -p /state/config /state/data /state/private \
    && chown -R studyspace:studyspace /state /opt/playwright

USER studyspace
WORKDIR /state/config
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8501')+'/_stcore/health', timeout=4)"
CMD ["python", "/opt/studyspace/deploy/start.py"]
