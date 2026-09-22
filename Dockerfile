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
ENV DEBIAN_FRONTEND=noninteractive
# apt-get upgrade 로 베이스 태그가 다시 구워지기 전에 나온 보안 패치를
# 받는다. 파이썬은 /usr/local 에 소스 빌드로 들어 있어 apt 가 건드리지
# 않는다.
#
# pip·setuptools 는 지운다. 런타임은 아무것도 설치하지 않고, /app/.venv
# 는 시스템 site-packages 를 보지 않으므로(venv 기본값) 앱에서 임포트
# 되지도 않는다. 남겨 두면 쓰이지도 않는 코드가 취약점 스캔에만 걸린다.
# pip 은 msgpack 을 vendoring 하므로 그것도 함께 사라진다.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/local/lib/python3.*/site-packages/pip* \
           /usr/local/lib/python3.*/site-packages/setuptools* \
           /usr/local/lib/python3.*/site-packages/pkg_resources \
           /usr/local/bin/pip* \
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
