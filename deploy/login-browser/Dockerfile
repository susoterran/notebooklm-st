# 원격 구글 로그인 사이드카 이미지.
#
# 앱 이미지와 따로 굽는다. 크로미움·가상 화면·화면 중계를 앱 이미지에
# 넣으면 수백 MB 가 늘고, 앱 이미지에 playwright 가 없다는 불변식이
# 깨진다(build.yml 이 단언한다).
#
# 설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §6

# ── builder ────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
# 앱과 같은 락, login-browser 그룹만. streamlit 등 앱 의존성은 들어오지
# 않는다.
RUN uv sync --frozen --only-group login-browser --no-install-project

# ── runtime ────────────────────────────────────────────────
# 빌더와 같은 계열이어야 한다. /app/.venv 가 빌더의 인터프리터 경로를
# 절대 경로로 참조한다.
FROM python:3.13-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH
# playwright install --with-deps 는 apt 로 크로미움의 공유 라이브러리를
# 받으므로 root 인 이 단계에서 돈다. 브라우저는 /ms-playwright 에 두어
# 비root 사용자도 읽게 한다.
#
# 베이스 이미지의 pip·setuptools 는 앱 이미지와 같은 이유로 지운다.
# 감시 루프는 /app/.venv 를, websockify 는 Debian 의 /usr/bin/python3
# 를 쓰므로 /usr/local 의 pip 은 아무도 쓰지 않는다. 남겨 두면 pip 이
# vendoring 한 msgpack·pkg_resources 가 취약점 스캔에만 걸린다.
RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify tzdata \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/local/lib/python3.*/site-packages/pip* \
           /usr/local/lib/python3.*/site-packages/setuptools* \
           /usr/local/lib/python3.*/site-packages/pkg_resources \
           /usr/local/bin/pip* \
 && groupadd -g 1000 app \
 && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin app
# HOME 은 tmpfs(/tmp)다. 루트 파일시스템이 read_only 라 크로미움과
# x11vnc 가 쓸 곳이 필요하다. 프로필 경로는 앱 이미지와 같아야 한다.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    NOTEBOOKLM_HOME=/data/notebooklm \
    NOTEBOOKLM_ST_LOGIN_DIR=/data/login \
    TZ=Asia/Seoul
# 앱 패키지 중 감시 루프와 신호 계약만 싣는다. 두 __init__.py 는
# docstring 뿐이라 다른 모듈을 끌어오지 않는다.
COPY src/notebooklm_st/__init__.py /app/src/notebooklm_st/__init__.py
COPY src/notebooklm_st/core/__init__.py /app/src/notebooklm_st/core/__init__.py
COPY src/notebooklm_st/core/login_protocol.py /app/src/notebooklm_st/core/login_protocol.py
COPY src/notebooklm_st/login_browser/ /app/src/notebooklm_st/login_browser/
ENV PYTHONPATH=/app/src
USER app
EXPOSE 6080
CMD ["python", "-m", "notebooklm_st.login_browser.supervisor"]
