"""원격 로그인 사이드카의 감시 루프.

앱이 공유 볼륨에 쓴 요청을 보고, 가상 화면 위에 ``notebooklm login``
을 띄워 사람이 앱 화면 안에서 구글 로그인을 하게 한다. 결과 쿠키는
CLI 가 앱과 같은 프로필에 직접 저장한다.

표준 라이브러리와 ``core.login_protocol`` 만 쓴다. 이 이미지에는 앱의
의존성(streamlit 등)이 없다.

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §6
"""

import contextlib
import dataclasses
import datetime as dt
import logging
import os
import pathlib
import secrets
import shutil
import signal
import subprocess
import sys
import time
import types
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from notebooklm_st.core import login_protocol

logger = logging.getLogger(__name__)

SESSION_SECONDS = 300
"""사람이 로그인을 마칠 때까지 기다리는 시간(초). 사이드카가 소유한다."""

CLI_BROWSER_TIMEOUT = 900
"""CLI 에 주는 시한(초). 사이드카의 시한이 항상 먼저 오게 더 길게 둔다.

둘이 겹치면 누가 끝냈는지 모호해져 timeout 과 failed 가 섞인다.
"""

TICK_SECONDS = 1.0
STOP_GRACE = 5.0
"""SIGTERM 뒤 SIGKILL 까지 기다리는 시간(초)."""

DISPLAY = ":99"
VNC_PORT = 5900
WEB_PORT = 6080
NOVNC_WEB = "/usr/share/novnc"
PASSWORD_FILE = "vncpass"
LOG_FILE = "login.log"
DETAIL_MAX = 200

DETAIL_RESTARTED = "로그인 브라우저가 재시작되었습니다"
DETAIL_STOPPED = "로그인 브라우저가 멈췄습니다"
DETAIL_RELAY = "화면 중계가 멈췄습니다"


class ProcessLike(Protocol):
    """자식 프로세스에서 이 모듈이 쓰는 부분."""

    def poll(self) -> int | None:
        """끝났으면 종료 코드, 아니면 ``None``."""

    def terminate(self) -> None:
        """SIGTERM 을 보낸다."""

    def kill(self) -> None:
        """SIGKILL 을 보낸다."""

    def wait(self, timeout: float) -> int:
        """끝날 때까지 기다린다. 넘기면 ``TimeoutExpired``."""


Launcher = Callable[
    [Sequence[str], Mapping[str, str], pathlib.Path | None], ProcessLike
]
"""``(argv, env, log_path)`` 로 자식을 띄운다.

``log_path`` 가 있으면 stdout·stderr 를 그 파일로 보낸다.
"""


class _StartError(Exception):
    """세션을 이루는 프로세스 하나를 띄우지 못했다. 인자는 단계 이름."""


@dataclasses.dataclass
class _Session:
    """떠 있는 로그인 세션."""

    request_id: str
    processes: list[ProcessLike]
    deadline: dt.datetime

    @property
    def cli(self) -> ProcessLike:
        """마지막에 띄운 ``notebooklm login``."""
        return self.processes[-1]

    @property
    def helpers(self) -> list[ProcessLike]:
        """가상 화면과 화면 중계."""
        return self.processes[:-1]


def _password() -> str:
    """세션 비밀번호. VNC 인증은 8자까지만 쓰므로 8자로 만든다."""
    return secrets.token_urlsafe(6)


class Supervisor:
    """요청을 받아 로그인 세션을 하나씩 띄우고 거둔다."""

    def __init__(
        self,
        *,
        login_dir: pathlib.Path,
        profile_dir: pathlib.Path,
        work_dir: pathlib.Path,
        launch: Launcher,
        clock: Callable[[], dt.datetime],
        wait_ready: Callable[[], bool],
        env: Mapping[str, str],
        make_password: Callable[[], str] = _password,
    ) -> None:
        """주변을 받아 둔다.

        Args:
            login_dir: 신호 파일 디렉터리.
            profile_dir: CLI 가 저장하는 notebooklm 프로필 디렉터리.
            work_dir: 비밀번호 파일과 CLI 로그를 두는 임시 디렉터리.
            launch: 자식을 띄우는 함수.
            clock: 지금 시각(UTC, aware).
            wait_ready: 가상 화면이 뜰 때까지 기다린다. 못 뜨면 ``False``.
            env: 자식에게 줄 환경변수의 바탕.
            make_password: 세션 비밀번호를 만든다.
        """
        self._login_dir = login_dir
        self._browser_profile = profile_dir / "browser_profile"
        self._work_dir = work_dir
        self._launch = launch
        self._clock = clock
        self._wait_ready = wait_ready
        self._env = dict(env)
        self._make_password = make_password
        self._session: _Session | None = None
        self._last_request_id: str | None = None

    def recover(self) -> None:
        """기동 직후 한 번 부른다.

        재시작 전의 세션이 남아 있으면 정리하고 실패로 쓴다. 그때 있던
        요청은 처리한 것으로 기록해, 사람 없이 다시 실행되지 않게 한다.
        """
        status = self._read_status()
        if status.state in login_protocol.ACTIVE_STATES:
            self._cleanup_files()
            self._write_status(
                login_protocol.State.FAILED,
                status.request_id,
                DETAIL_RESTARTED,
            )
        request = self._read_request()
        if request is not None:
            self._last_request_id = request.id

    def tick(self) -> None:
        """감시 한 주기. 1초마다 부른다."""
        self._beat()
        request = self._read_request()
        if request is not None and request.id != self._last_request_id:
            self._last_request_id = request.id
            self._handle(request)
        if self._session is not None:
            self._check(self._session)

    def shutdown(self) -> None:
        """컨테이너가 내려갈 때 떠 있는 세션을 정리한다."""
        if self._session is not None:
            self._finish(login_protocol.State.FAILED, DETAIL_STOPPED)

    def _handle(self, request: login_protocol.Request) -> None:
        """새 요청 하나를 처리한다."""
        start = login_protocol.Action.START
        cancel = login_protocol.Action.CANCEL
        if request.action is start and self._session is None:
            self._start(request.id)
        elif request.action is cancel and self._session is not None:
            self._finish(login_protocol.State.CANCELLED, None)

    def _start(self, request_id: str) -> None:
        """가상 화면·화면 중계·CLI 를 차례로 띄운다."""
        self._write_status(login_protocol.State.STARTING, request_id, None)
        password = self._make_password()
        self._work_dir.mkdir(parents=True, exist_ok=True)
        password_file = self._work_dir / PASSWORD_FILE
        login_protocol.write_atomic(password_file, password + "\n")
        processes: list[ProcessLike] = []
        try:
            processes.append(
                self._spawn(
                    "Xvfb",
                    [
                        "Xvfb",
                        DISPLAY,
                        "-screen",
                        "0",
                        "1280x800x24",
                        "-nolisten",
                        "tcp",
                    ],
                    None,
                )
            )
            if not self._wait_ready():
                raise _StartError("가상 화면")
            processes.append(
                self._spawn(
                    "x11vnc",
                    [
                        "x11vnc",
                        "-display",
                        DISPLAY,
                        "-localhost",
                        "-rfbport",
                        str(VNC_PORT),
                        "-passwdfile",
                        f"rm:{password_file}",
                        "-forever",
                        "-shared",
                        "-quiet",
                    ],
                    None,
                )
            )
            processes.append(
                self._spawn(
                    "websockify",
                    [
                        "websockify",
                        "--web",
                        NOVNC_WEB,
                        str(WEB_PORT),
                        f"localhost:{VNC_PORT}",
                    ],
                    None,
                )
            )
            processes.append(
                self._spawn(
                    "notebooklm login",
                    [
                        sys.executable,
                        "-m",
                        "notebooklm",
                        "login",
                        "--fresh",
                        "--browser-timeout",
                        str(CLI_BROWSER_TIMEOUT),
                    ],
                    self._work_dir / LOG_FILE,
                )
            )
        except _StartError as error:
            for process in reversed(processes):
                _stop(process)
            self._cleanup_files()
            self._write_status(
                login_protocol.State.FAILED,
                request_id,
                f"로그인 브라우저를 띄우지 못했습니다({error})",
            )
            return
        deadline = self._clock() + dt.timedelta(seconds=SESSION_SECONDS)
        self._session = _Session(request_id, processes, deadline)
        self._write_status(
            login_protocol.State.RUNNING,
            request_id,
            None,
            password=password,
            deadline=deadline,
        )
        logger.info("로그인 세션을 열었습니다: %s", request_id)

    def _spawn(
        self, stage: str, argv: list[str], log_path: pathlib.Path | None
    ) -> ProcessLike:
        """자식 하나를 띄운다. 못 띄우면 단계 이름으로 알린다."""
        env = {**self._env, "DISPLAY": DISPLAY}
        try:
            return self._launch(argv, env, log_path)
        except OSError as error:
            logger.warning("%s 를 띄우지 못했습니다: %s", stage, error)
            raise _StartError(stage) from error

    def _check(self, session: _Session) -> None:
        """떠 있는 세션이 끝났는지 본다."""
        code = session.cli.poll()
        if code is not None:
            if code == 0:
                self._finish(login_protocol.State.SUCCEEDED, None)
            else:
                detail = self._last_log_line() or f"종료 코드 {code}"
                self._finish(login_protocol.State.FAILED, detail)
            return
        if any(helper.poll() is not None for helper in session.helpers):
            self._finish(login_protocol.State.FAILED, DETAIL_RELAY)
            return
        if self._clock() >= session.deadline:
            self._finish(login_protocol.State.TIMEOUT, None)

    def _finish(self, state: login_protocol.State, detail: str | None) -> None:
        """세션을 내리고 흔적을 지운 뒤 결과를 쓴다."""
        session = self._session
        if session is None:
            return
        self._session = None
        for process in reversed(session.processes):
            _stop(process)
        self._cleanup_files()
        self._write_status(state, session.request_id, detail)
        logger.info(
            "로그인 세션을 닫았습니다: %s %s", session.request_id, state
        )

    def _cleanup_files(self) -> None:
        """비밀번호 파일·CLI 로그·크로미움 프로필을 지운다.

        크로미움 프로필은 계정 동등 자격증명이다. 공유 볼륨에 남기지
        않는다.
        """
        (self._work_dir / PASSWORD_FILE).unlink(missing_ok=True)
        (self._work_dir / LOG_FILE).unlink(missing_ok=True)
        shutil.rmtree(self._browser_profile, ignore_errors=True)
        if self._browser_profile.exists():
            logger.error("브라우저 프로필을 지우지 못했습니다")

    def _last_log_line(self) -> str | None:
        """CLI 로그의 비어 있지 않은 마지막 줄."""
        try:
            text = (self._work_dir / LOG_FILE).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return None
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1][:DETAIL_MAX] if lines else None

    def _beat(self) -> None:
        """Heartbeat 의 수정 시각을 갱신한다."""
        self._login_dir.mkdir(parents=True, exist_ok=True)
        (self._login_dir / login_protocol.HEARTBEAT_FILE).touch()

    def _read_request(self) -> login_protocol.Request | None:
        """요청을 읽는다. 깨졌으면 넘어간다."""
        try:
            return login_protocol.read_request(self._login_dir)
        except (OSError, login_protocol.ProtocolError) as error:
            logger.warning("요청 파일을 읽지 못했습니다: %s", error)
            return None

    def _read_status(self) -> login_protocol.Status:
        """자기가 쓴 상태를 읽는다. 깨졌으면 idle 로 본다."""
        try:
            return login_protocol.read_status(self._login_dir)
        except (OSError, login_protocol.ProtocolError) as error:
            logger.warning("상태 파일을 읽지 못했습니다: %s", error)
            return login_protocol.IDLE

    def _write_status(
        self,
        state: login_protocol.State,
        request_id: str | None,
        detail: str | None,
        *,
        password: str | None = None,
        deadline: dt.datetime | None = None,
    ) -> None:
        """상태를 쓴다. 비밀번호와 마감은 running 일 때만 넘긴다."""
        login_protocol.write_status(
            self._login_dir,
            login_protocol.Status(
                state=state,
                request_id=request_id,
                password=password,
                deadline=(
                    None
                    if deadline is None
                    else deadline.isoformat(timespec="seconds")
                ),
                detail=detail,
                updated_at=self._clock().isoformat(timespec="seconds"),
            ),
        )


def _stop(process: ProcessLike) -> None:
    """SIGTERM 으로 끝내 보고, 안 끝나면 SIGKILL 한다."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(STOP_GRACE)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(STOP_GRACE)
        except subprocess.TimeoutExpired:
            logger.error("자식 프로세스가 끝나지 않습니다")


X_SOCKET = pathlib.Path("/tmp/.X11-unix/X99")
READY_TIMEOUT = 5.0
WORK_DIR = pathlib.Path("/tmp/login-browser")


class _GroupProcess:
    """자식과 그 자손을 한 프로세스 그룹으로 다룬다.

    크로미움은 CLI 의 자손이다. CLI 에만 신호를 보내면 크로미움이
    남는다.
    """

    def __init__(self, popen: subprocess.Popen[bytes]) -> None:
        """감쌀 ``Popen`` 을 받아 둔다."""
        self._popen = popen

    def poll(self) -> int | None:
        """끝났으면 종료 코드, 아니면 ``None``."""
        return self._popen.poll()

    def wait(self, timeout: float) -> int:
        """끝날 때까지 기다린다."""
        return self._popen.wait(timeout)

    def terminate(self) -> None:
        """그룹 전체에 SIGTERM 을 보낸다."""
        if sys.platform == "win32":
            self._popen.terminate()
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._popen.pid, signal.SIGTERM)

    def kill(self) -> None:
        """그룹 전체에 SIGKILL 을 보낸다."""
        if sys.platform == "win32":
            self._popen.kill()
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._popen.pid, signal.SIGKILL)


def _launch(
    argv: Sequence[str],
    env: Mapping[str, str],
    log_path: pathlib.Path | None,
) -> ProcessLike:
    """자식을 새 세션(프로세스 그룹)으로 띄운다."""
    if log_path is None:
        popen = subprocess.Popen(
            list(argv),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    else:
        with log_path.open("wb") as log:
            popen = subprocess.Popen(
                list(argv),
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    return _GroupProcess(popen)


def _wait_for_display() -> bool:
    """Xvfb 의 소켓이 생길 때까지 기다린다."""
    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        if X_SOCKET.exists():
            return True
        time.sleep(0.1)
    return False


def _utc_now() -> dt.datetime:
    """지금 시각(UTC)."""
    return dt.datetime.now(dt.UTC)


def build() -> Supervisor:
    """이미지의 환경변수로 감시 루프를 조립한다."""
    home = pathlib.Path(os.environ["NOTEBOOKLM_HOME"])
    return Supervisor(
        login_dir=pathlib.Path(os.environ[login_protocol.DIR_ENV_VAR]),
        profile_dir=home / "profiles" / "default",
        work_dir=WORK_DIR,
        launch=_launch,
        clock=_utc_now,
        wait_ready=_wait_for_display,
        # rich 의 색 코드가 CLI 로그 마지막 줄(화면에 보이는 사유)에
        # 섞이지 않게 한다.
        env={**os.environ, "NO_COLOR": "1", "TERM": "dumb"},
    )


def _exit_on_signal(signum: int, frame: types.FrameType | None) -> None:
    """Docker stop 의 SIGTERM 을 정상 종료로 바꾼다."""
    raise SystemExit(0)


def main() -> None:
    """감시 루프를 돈다. 컨테이너의 진입점이다."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    supervisor = build()
    signal.signal(signal.SIGTERM, _exit_on_signal)
    supervisor.recover()
    logger.info("원격 로그인 요청을 기다립니다")
    try:
        while True:
            try:
                supervisor.tick()
            except Exception:
                # 한 주기가 실패해도 루프는 산다. 죽으면 앱이 "꺼져
                # 있음" 만 보여 주고 사람은 원인을 모른다.
                logger.exception("감시 주기가 실패했습니다")
            time.sleep(TICK_SECONDS)
    finally:
        supervisor.shutdown()


if __name__ == "__main__":
    main()
