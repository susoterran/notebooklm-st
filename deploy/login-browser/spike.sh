#!/usr/bin/env bash
# 원격 로그인 스파이크 — 사이드카 이미지만으로 구글 로그인이 되는지 본다.
#
# 감시 루프 없이, 사이드카가 세션마다 띄울 것(Xvfb → x11vnc →
# websockify → notebooklm login)을 운영과 같은 조건(비root 1000,
# read_only, /tmp tmpfs, shm 1GB)으로 손수 띄운다.
#
#   spike.sh up <데이터 디렉터리>     이미지를 굽고 세션을 띄운다
#   spike.sh check                    프로세스·포트·결과를 본다
#   spike.sh down <데이터 디렉터리>   내리고 스파이크 자격증명을 지운다
#
# 데이터 디렉터리에는 계정 동등 자격증명이 생긴다. 저장소 밖만 받는다.
# Docker 가 PATH 에 없으면 DOCKER 에 전체 경로를 준다.
#
# 설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §13
set -euo pipefail

DOCKER="${DOCKER:-docker}"
IMAGE=notebooklm-st-login-browser:spike
NAME=notebooklm-st-login-spike
PORT="${SPIKE_PORT:-9005}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

# Git Bash 가 /data 같은 컨테이너 경로를 윈도우 경로로 바꾸지 않게 한다.
export MSYS_NO_PATHCONV=1

usage() {
  sed -n '8,10p' "$0" >&2
  exit 2
}

# 데이터 디렉터리를 만들고, docker -v 에 넘길 호스트 경로를 출력한다.
data_dir() {
  [ -n "${1:-}" ] || usage
  mkdir -p "$1"
  local dir
  dir="$(cd "$1" && pwd)"
  case "$dir/" in
    "$REPO"/*)
      echo "저장소 안에는 둘 수 없습니다: $dir" >&2
      exit 2
      ;;
  esac
  # Docker Desktop(윈도우)은 윈도우 경로를 받는다.
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$dir"
  else
    echo "$dir"
  fi
}

# MSYS_NO_PATHCONV 이 켜져 있어 posix 경로가 docker.exe 로 넘어갈 때
# 자동 변환되지 않는다(컨테이너 쪽 /data 경로를 보호하려고 켠 것이라
# 껄 수 없다). -f·빌드 컨텍스트처럼 호스트 경로를 받는 인자는 여기서
# 직접 윈도우 경로로 바꿔 준다. 이게 없으면
# "unable to prepare context: path ... not found" 로 빌드가 실패한다.
winpath() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    echo "$1"
  fi
}

up() {
  local data password dockerfile context
  data="$(data_dir "${1:-}")"
  # 경로 전체(파일 하나)를 통째로 변환한다. 이미 변환된 윈도우 경로 뒤에
  # 백슬래시를 이어 붙이면 리눅스(cygpath 없음)에서는 winpath() 가 원본
  # posix 경로를 그대로 돌려주므로 "/repo\deploy\login-browser\Dockerfile"
  # 처럼 백슬래시가 섞여 build 가 실패한다.
  dockerfile="$(winpath "$REPO/deploy/login-browser/Dockerfile")"
  context="$(winpath "$REPO")"
  "$DOCKER" build -f "$dockerfile" -t "$IMAGE" "$context"
  # 호스트에서 sudo chown 하지 않아도 되게, 컨테이너의 root 로 맞춘다.
  "$DOCKER" run --rm --user 0:0 -v "$data:/data" "$IMAGE" \
    chown 1000:1000 /data
  # head -c 8 가 8바이트를 읽고 먼저 닫으면 tr 이 SIGPIPE(141)로 죽는다.
  # pipefail 이 이 141 을 파이프라인 종료 코드로 골라 set -e 를 태운다
  # (비밀번호 자체는 문제없이 만들어진다). 마지막에 true 를 둬 파이프
  # 실패를 무시한다.
  password="$(
    LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 8
    true
  )"
  "$DOCKER" run -d --name "$NAME" -p "$PORT:6080" -v "$data:/data" \
    --shm-size=1g --read-only --tmpfs /tmp --user 1000:1000 \
    -e SPIKE_PASSWORD="$password" "$IMAGE" bash -c '
      Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
      for _ in $(seq 50); do
        [ -S /tmp/.X11-unix/X99 ] && break
        sleep 0.1
      done
      printf "%s\n" "$SPIKE_PASSWORD" > /tmp/vncpass
      chmod 600 /tmp/vncpass
      x11vnc -display :99 -localhost -rfbport 5900 \
        -passwdfile rm:/tmp/vncpass -forever -shared -quiet &
      websockify --web /usr/share/novnc 6080 localhost:5900 &
      DISPLAY=:99 NO_COLOR=1 python -m notebooklm login --fresh \
        --browser-timeout 900 > /tmp/login.log 2>&1
      echo $? > /tmp/exit
      sleep infinity'
  echo
  echo "뷰어: http://localhost:$PORT/vnc.html#autoconnect=1&resize=scale&password=$password"
  echo "다른 기기에서는 localhost 대신 이 기기의 LAN 주소를 쓴다."
}

check() {
  "$DOCKER" exec -i "$NAME" python - <<'EOF'
import os
from pathlib import Path

procs = sorted(
    {
        p.joinpath("comm").read_text().strip()
        for p in Path("/proc").glob("[0-9]*")
        if p.joinpath("comm").exists()
    }
)
print("uid:", os.getuid())
print("processes:", ", ".join(procs))


def listening(table):
    for line in Path(table).read_text().splitlines()[1:]:
        cols = line.split()
        if cols[3] != "0A":  # LISTEN
            continue
        host, port = cols[1].split(":")
        yield host, int(port, 16)


for host, port in sorted(set(listening("/proc/net/tcp"))):
    addr = ".".join(str(int(host[i : i + 2], 16)) for i in (6, 4, 2, 0))
    print(f"listen: {addr}:{port}")

try:
    Path("/etc/spike-write-test").write_text("x")
    print("rootfs: WRITABLE")
except OSError:
    print("rootfs: read-only")

exit_file = Path("/tmp/exit")
code = exit_file.read_text().strip() if exit_file.exists() else "(running)"
print("login exit:", code)
log_file = Path("/tmp/login.log")
text = log_file.read_text(errors="replace") if log_file.exists() else ""
lines = [line.strip() for line in text.splitlines() if line.strip()]
print("login log last line:", lines[-1] if lines else "(empty)")

# 파일 이름만 보인다. 내용은 자격증명이다.
profile = Path("/data/notebooklm/profiles/default")
names = sorted(p.name for p in profile.iterdir()) if profile.exists() else []
print("profile files:", ", ".join(names) or "(none)")
EOF
}

down() {
  local data
  data="$(data_dir "${1:-}")"
  "$DOCKER" rm -f "$NAME" >/dev/null 2>&1 || true
  # 1000 소유 파일을 sudo 없이 지운다. find 로 /data 자체는 남긴다.
  "$DOCKER" run --rm --user 0:0 -v "$data:/data" "$IMAGE" \
    sh -c 'find /data -mindepth 1 -delete && ls -A /data'
  echo "스파이크 컨테이너와 자격증명을 지웠습니다."
}

case "${1:-}" in
  up) up "${2:-}" ;;
  check) check ;;
  down) down "${2:-}" ;;
  *) usage ;;
esac
