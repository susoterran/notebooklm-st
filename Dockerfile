# 앱을 홈서버 컨테이너에서 돌리기 위한 이미지.
#
# 런타임 단계에는 uv 를 넣지 않는다. uv 가 있으면 `uv run` 이 dev
# 그룹을 조용히 다시 동기화해 playwright 가 되살아난다. 없으면 그
# 함정이 성립하지 않는다.

# ── builder ────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── runtime ────────────────────────────────────────────────
# 베이스는 빌더와 같은 계열이어야 한다. /app/.venv 가 빌더의
# 인터프리터 경로를 절대 경로로 참조한다.
FROM python:3.13-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 1000 app \
 && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app
COPY --from=builder /app/.venv /app/.venv
COPY src/ /app/src/
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# 앱 환경변수의 정본. compose 가 아니라 여기에 둔다 — 이미지가
# 단독으로도 옳게 서야 한다.
ENV HOME=/data \
    NOTEBOOKLM_HOME=/data/notebooklm \
    NOTEBOOKLM_ST_DB=/data/questions.db \
    TZ=Asia/Seoul \
    STREAMLIT_SERVER_PORT=8611 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none
WORKDIR /app
USER app
EXPOSE 8611
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8611/_stcore/health', timeout=4).read()"
CMD ["streamlit", "run", "/app/src/notebooklm_st/app.py"]
