"""앱 쪽에서 원격 로그인 사이드카와 이야기한다.

사이드카와는 공유 볼륨의 파일로만 주고받는다(``core.login_protocol``).
이 모듈은 요청을 쓰고 상태를 읽을 뿐 화면 문구를 만들지 않는다.

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §8
"""

import datetime as dt
import logging
import os
import pathlib
import urllib.parse
import uuid

from notebooklm_st.core import login_protocol
from notebooklm_st.services import digest_runner, runs

logger = logging.getLogger(__name__)

VIEWER_URL_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_VIEWER_URL"

HEARTBEAT_STALE_AFTER = 10.0
"""heartbeat 가 이보다 오래 멈춰 있으면 사이드카가 꺼진 것으로 본다(초).

사이드카는 1초마다 갱신한다. 세션을 띄우는 동안 몇 초 멈출 수 있어
넉넉히 잡는다.
"""

START_ACK_TIMEOUT = 30.0
"""시작 요청을 이보다 오래 받지 않으면 더는 기다리지 않는다(초).

사이드카는 1초마다 요청을 보고 받자마자 ``starting`` 을 쓴다. 이만큼
지나도 답이 없으면 사이드카가 그 요청을 처리하지 않은 것이다(재시작
직전에 쓰였거나 다른 탭의 세션 중에 쓰였다). 계속 기다리면 화면이
"준비 중" 에 묶여 시작 버튼이 다시 나오지 않는다.
"""


def viewer_url() -> str | None:
    """사용자 브라우저가 닿는 noVNC 주소.

    컨테이너는 홈서버의 LAN 주소를 모르므로 설정으로 받는다.

    Returns:
        끝의 ``/`` 를 뗀 주소. 설정이 없으면 ``None`` — 원격 로그인을
        쓰지 않는다.
    """
    value = os.environ.get(VIEWER_URL_ENV_VAR, "").strip().rstrip("/")
    return value or None


def login_dir() -> pathlib.Path | None:
    """신호 파일을 두는 디렉터리.

    Returns:
        디렉터리. 설정이 없으면 ``None``.
    """
    value = os.environ.get(login_protocol.DIR_ENV_VAR, "").strip()
    return pathlib.Path(value) if value else None


def read_status(directory: pathlib.Path) -> login_protocol.Status:
    """사이드카의 상태를 읽는다.

    파일이 깨졌거나 읽히지 않으면 ``idle`` 로 본다. 화면이 트레이스백
    대신 시작 버튼을 그리게 하려는 것이다. 사이드카가 다음에 쓸 때
    바로잡힌다.

    Returns:
        상태.
    """
    try:
        return login_protocol.read_status(directory)
    except (OSError, login_protocol.ProtocolError) as error:
        logger.warning("원격 로그인 상태 파일을 읽지 못했습니다: %s", error)
        return login_protocol.IDLE


def sidecar_alive(directory: pathlib.Path, now: float) -> bool:
    """사이드카가 떠 있는지 heartbeat 로 판정한다.

    Args:
        directory: 신호 디렉터리.
        now: 지금 시각(``time.time()``).

    Returns:
        heartbeat 가 ``HEARTBEAT_STALE_AFTER`` 초 안에 갱신됐으면 ``True``.
    """
    heartbeat = directory / login_protocol.HEARTBEAT_FILE
    try:
        modified = heartbeat.stat().st_mtime
    except OSError:
        return False
    return now - modified <= HEARTBEAT_STALE_AFTER


def pending_request(directory: pathlib.Path) -> login_protocol.Request | None:
    """앱이 마지막으로 쓴 요청.

    상태의 ``request_id`` 와 비교해 사이드카가 아직 받지 않은 요청을
    가린다.

    Returns:
        요청. 없거나 깨졌으면 ``None``.
    """
    try:
        return login_protocol.read_request(directory)
    except (OSError, login_protocol.ProtocolError):
        return None


def start_is_stale(request: login_protocol.Request, now: dt.datetime) -> bool:
    """시작 요청이 사이드카의 답을 기다리기엔 너무 오래됐는지.

    Args:
        request: 앱이 마지막으로 쓴 요청.
        now: 지금 시각(UTC, aware).

    Returns:
        ``START_ACK_TIMEOUT`` 초가 지났으면 ``True``. 요청 시각을 읽지
        못해도 ``True`` — 영원히 기다리는 쪽보다 시작 버튼을 다시
        보여 주는 쪽이 낫다.
    """
    try:
        requested = dt.datetime.fromisoformat(request.requested_at)
    except ValueError:
        return True
    if requested.tzinfo is None:
        return True
    return (now - requested).total_seconds() > START_ACK_TIMEOUT


def request_start(directory: pathlib.Path) -> str:
    """로그인 시작을 요청한다.

    Returns:
        새 요청의 ``id``. 화면이 이 요청을 지켜보는 데 쓴다.
    """
    return _write_request(directory, login_protocol.Action.START)


def request_cancel(directory: pathlib.Path) -> str:
    """진행 중인 로그인의 취소를 요청한다.

    Returns:
        새 요청의 ``id``.
    """
    return _write_request(directory, login_protocol.Action.CANCEL)


def busy(
    registry: runs.RunRegistry, digests: digest_runner.DigestRegistry
) -> bool:
    """질의나 정리본이 돌고 있는지.

    돌고 있는 작업은 옛 쿠키를 들고 있다가 회전할 때 파일에 되쓴다.
    새 로그인 직후 그 되쓰기가 일어나면 새 쿠키가 덮일 수 있어 시작을
    막는 데 쓴다.

    Returns:
        하나라도 돌고 있으면 ``True``.
    """
    return registry.running_count() > 0 or digests.is_running()


def viewer_link(base: str, password: str) -> str:
    """Iframe 에 넣을 noVNC 주소.

    비밀번호는 해시에 둔다. 해시는 서버로 전송되지 않아 요청 로그에
    남지 않는다.

    Args:
        base: ``viewer_url()`` 의 값.
        password: 이번 세션의 비밀번호.

    Returns:
        자동 접속·화면 맞춤이 켜진 주소.
    """
    secret = urllib.parse.quote(password, safe="")
    return f"{base}/vnc.html#autoconnect=1&resize=scale&password={secret}"


def remaining_seconds(
    status: login_protocol.Status, now: dt.datetime
) -> int | None:
    """세션 마감까지 남은 초.

    Args:
        status: 사이드카의 상태.
        now: 지금 시각(UTC, aware).

    Returns:
        남은 초. 지났으면 0, 마감이 없으면 ``None``.
    """
    if status.deadline is None:
        return None
    deadline = dt.datetime.fromisoformat(status.deadline)
    return max(0, int((deadline - now).total_seconds()))


def _write_request(
    directory: pathlib.Path, action: login_protocol.Action
) -> str:
    """새 요청을 쓴다."""
    request = login_protocol.Request(
        id=uuid.uuid4().hex,
        action=action,
        requested_at=login_protocol.now_iso(),
    )
    login_protocol.write_request(directory, request)
    return request.id
