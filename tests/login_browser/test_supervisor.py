"""원격 로그인 사이드카 감시 루프 테스트.

실제 Xvfb·크로미움 없이, 프로세스 실행기와 시계를 가짜로 끼워 상태
기계 전체를 검증한다.
"""

import dataclasses
import datetime as dt
import os
import pathlib
import subprocess
import sys
from collections.abc import Mapping, Sequence

import pytest

from notebooklm_st.core import login_protocol
from notebooklm_st.login_browser import supervisor

PASSWORD = "pw123456"


class FakeProcess:
    """자식 프로세스 흉내. 종료 코드를 테스트가 정한다."""

    def __init__(self, argv: Sequence[str]) -> None:
        """실행한 명령줄을 기억해 둔다."""
        self.argv = list(argv)
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self.ignore_term = False

    def poll(self) -> int | None:
        """끝났으면 종료 코드, 아니면 ``None``."""
        return self.returncode

    def terminate(self) -> None:
        """SIGTERM 을 흉내 낸다."""
        self.terminated = True
        if not self.ignore_term and self.returncode is None:
            self.returncode = -15

    def kill(self) -> None:
        """SIGKILL 을 흉내 낸다."""
        self.killed = True
        self.returncode = -9

    def wait(self, timeout: float) -> int:
        """끝날 때까지 기다린다. 안 끝났으면 시간 초과로 본다."""
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        return self.returncode


class FakeLauncher:
    """띄운 프로세스를 기록한다. 이름이 ``fail_on`` 이면 실패한다."""

    def __init__(self, fail_on: str | None = None) -> None:
        """실패시킬 프로세스 이름을 받아 둔다."""
        self.fail_on = fail_on
        self.processes: list[FakeProcess] = []
        self.envs: list[dict[str, str]] = []
        self.logs: list[pathlib.Path | None] = []

    def __call__(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        log_path: pathlib.Path | None,
    ) -> FakeProcess:
        """가짜 프로세스를 하나 띄우고 기록한다."""
        if argv[0] == self.fail_on:
            raise FileNotFoundError(argv[0])
        process = FakeProcess(argv)
        self.processes.append(process)
        self.envs.append(dict(env))
        self.logs.append(log_path)
        return process

    def named(self, name: str) -> FakeProcess:
        """명령 이름으로 띄운 프로세스를 찾는다."""
        return next(p for p in self.processes if p.argv[0] == name)

    @property
    def cli(self) -> FakeProcess:
        """띄운 ``notebooklm login`` 프로세스."""
        return next(
            p for p in self.processes if p.argv[1:3] == ["-m", "notebooklm"]
        )


class Clock:
    """테스트가 돌리는 시계."""

    def __init__(self) -> None:
        """기준 시각을 정한다."""
        self.now = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.UTC)

    def __call__(self) -> dt.datetime:
        """지금 시각을 돌려준다."""
        return self.now

    def advance(self, seconds: float) -> None:
        """시계를 앞으로 돌린다."""
        self.now += dt.timedelta(seconds=seconds)


@dataclasses.dataclass
class Rig:
    """감시 루프와 그 주변."""

    sup: supervisor.Supervisor
    launcher: FakeLauncher
    clock: Clock
    login_dir: pathlib.Path
    browser_profile: pathlib.Path
    work_dir: pathlib.Path

    def request(
        self,
        request_id: str,
        action: login_protocol.Action = login_protocol.Action.START,
    ) -> None:
        """요청 파일을 쓴다."""
        login_protocol.write_request(
            self.login_dir,
            login_protocol.Request(
                id=request_id, action=action, requested_at="t"
            ),
        )

    def status(self) -> login_protocol.Status:
        """상태 파일을 읽는다."""
        return login_protocol.read_status(self.login_dir)


def make_rig(
    tmp_path: pathlib.Path,
    *,
    fail_on: str | None = None,
    ready: bool = True,
    display_socket: pathlib.Path | None = None,
) -> Rig:
    """감시 루프와 가짜 실행기·시계를 한 벌 엮는다."""
    login_dir = tmp_path / "login"
    profile_dir = tmp_path / "notebooklm" / "profiles" / "default"
    browser_profile = profile_dir / "browser_profile"
    browser_profile.mkdir(parents=True)
    (browser_profile / "Cookies").write_text("secret", encoding="utf-8")
    work_dir = tmp_path / "work"
    launcher = FakeLauncher(fail_on=fail_on)
    clock = Clock()
    sup = supervisor.Supervisor(
        login_dir=login_dir,
        profile_dir=profile_dir,
        work_dir=work_dir,
        launch=launcher,
        clock=clock,
        wait_ready=lambda: ready,
        env={"PATH": "/usr/bin"},
        make_password=lambda: PASSWORD,
        display_socket=display_socket,
    )
    return Rig(sup, launcher, clock, login_dir, browser_profile, work_dir)


@pytest.fixture
def rig(tmp_path) -> Rig:
    """기본 값으로 엮은 감시 루프."""
    return make_rig(tmp_path)


def test_a_start_request_opens_a_session(rig: Rig) -> None:
    """시작 요청을 받으면 네 프로세스를 순서대로 띄우고 running 을 쓴다."""
    rig.request("r1")

    rig.sup.tick()

    names = [p.argv[0] for p in rig.launcher.processes]
    assert names == ["Xvfb", "x11vnc", "websockify", sys.executable]
    status = rig.status()
    assert status.state is login_protocol.State.RUNNING
    assert status.request_id == "r1"
    assert status.password == PASSWORD
    assert status.deadline == "2026-09-26T12:05:00+00:00"


def test_the_cli_logs_in_fresh_on_the_virtual_display(rig: Rig) -> None:
    """CLI 는 깨끗한 프로필로, 가상 화면 위에서, 긴 시한으로 돈다."""
    rig.request("r1")

    rig.sup.tick()

    cli = rig.launcher.cli
    assert cli.argv[3:] == ["login", "--fresh", "--browser-timeout", "900"]
    index = rig.launcher.processes.index(cli)
    assert rig.launcher.envs[index]["DISPLAY"] == ":99"
    assert rig.launcher.logs[index] == rig.work_dir / supervisor.LOG_FILE


def test_x11vnc_reads_the_password_from_a_private_file(rig: Rig) -> None:
    """비밀번호는 명령줄이 아니라 파일로 넘기고, 밖에서 닿지 않게 연다."""
    rig.request("r1")

    rig.sup.tick()

    argv = rig.launcher.named("x11vnc").argv
    password_file = rig.work_dir / supervisor.PASSWORD_FILE
    assert f"rm:{password_file}" in argv
    assert "-localhost" in argv
    assert PASSWORD not in argv
    assert password_file.read_text(encoding="utf-8") == PASSWORD + "\n"


def test_the_same_request_is_handled_once(rig: Rig) -> None:
    """같은 요청을 여러 번 읽어도 세션은 하나다."""
    rig.request("r1")

    rig.sup.tick()
    rig.sup.tick()

    assert len(rig.launcher.processes) == 4


def test_a_second_start_during_a_session_is_ignored(rig: Rig) -> None:
    """세션 중의 새 시작 요청은 무시한다."""
    rig.request("r1")
    rig.sup.tick()

    rig.request("r2")
    rig.sup.tick()

    assert len(rig.launcher.processes) == 4
    assert rig.status().request_id == "r1"


def test_a_successful_login_is_reported_and_cleaned_up(rig: Rig) -> None:
    """CLI 가 0 으로 끝나면 성공이고, 흔적을 모두 지운다."""
    rig.request("r1")
    rig.sup.tick()

    rig.launcher.cli.returncode = 0
    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.SUCCEEDED
    assert status.request_id == "r1"
    assert status.password is None
    assert status.deadline is None
    assert all(p.poll() is not None for p in rig.launcher.processes)
    assert not rig.browser_profile.exists()
    assert not (rig.work_dir / supervisor.PASSWORD_FILE).exists()


def test_a_failed_login_reports_the_last_log_line(rig: Rig) -> None:
    """CLI 가 실패하면 로그 마지막 줄을 사유로 남기고 로그를 지운다."""
    rig.request("r1")
    rig.sup.tick()
    log = rig.work_dir / supervisor.LOG_FILE
    log.write_text("시작\n\nError: boom  \n\n", encoding="utf-8")

    rig.launcher.cli.returncode = 1
    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.detail == "Error: boom"
    assert not log.exists()
    assert not rig.browser_profile.exists()


def test_a_failed_login_without_output_reports_the_exit_code(rig: Rig) -> None:
    """로그가 비었으면 종료 코드를 사유로 쓴다."""
    rig.request("r1")
    rig.sup.tick()

    rig.launcher.cli.returncode = 2
    rig.sup.tick()

    assert rig.status().detail == "종료 코드 2"


def test_the_session_times_out_at_the_deadline(rig: Rig) -> None:
    """300초가 지나면 사이드카가 끝낸다."""
    rig.request("r1")
    rig.sup.tick()

    rig.clock.advance(299)
    rig.sup.tick()
    assert rig.status().state is login_protocol.State.RUNNING

    rig.clock.advance(1)
    rig.sup.tick()

    assert rig.status().state is login_protocol.State.TIMEOUT
    assert rig.launcher.cli.terminated
    assert not rig.browser_profile.exists()


def test_a_cancel_request_ends_the_session(rig: Rig) -> None:
    """취소 요청을 받으면 세션을 끝내고 cancelled 를 쓴다."""
    rig.request("r1")
    rig.sup.tick()

    rig.request("r2", login_protocol.Action.CANCEL)
    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.CANCELLED
    assert status.request_id == "r1"
    assert not rig.browser_profile.exists()


def test_a_cancel_without_a_session_is_ignored(rig: Rig) -> None:
    """세션이 없을 때의 취소는 아무 일도 하지 않는다."""
    rig.request("r1", login_protocol.Action.CANCEL)

    rig.sup.tick()

    assert rig.launcher.processes == []
    assert rig.status() == login_protocol.IDLE


def test_a_dead_relay_fails_the_session(rig: Rig) -> None:
    """화면 중계가 죽으면 사람이 로그인할 수 없으므로 실패로 끝낸다."""
    rig.request("r1")
    rig.sup.tick()

    rig.launcher.named("websockify").returncode = 1
    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.detail == supervisor.DETAIL_RELAY
    assert rig.launcher.cli.terminated


def test_a_launch_failure_cleans_up_what_started(tmp_path) -> None:
    """하나라도 못 띄우면 이미 뜬 것을 내리고 실패를 쓴다."""
    rig = make_rig(tmp_path, fail_on="websockify")
    rig.request("r1")

    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert "websockify" in (status.detail or "")
    assert status.password is None
    assert rig.launcher.named("Xvfb").terminated
    assert rig.launcher.named("x11vnc").terminated
    assert not rig.browser_profile.exists()
    assert not (rig.work_dir / supervisor.PASSWORD_FILE).exists()


def test_a_display_that_never_comes_up_fails_the_session(tmp_path) -> None:
    """가상 화면이 뜨지 않으면 나머지를 띄우지 않는다."""
    rig = make_rig(tmp_path, ready=False)
    rig.request("r1")

    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert "가상 화면" in (status.detail or "")
    assert [p.argv[0] for p in rig.launcher.processes] == ["Xvfb"]
    assert rig.launcher.named("Xvfb").terminated


def test_an_unexpected_os_error_mid_start_cleans_up(tmp_path) -> None:
    """시작 도중의 예상 밖 OSError 도 띄운 것을 내리고 실패를 쓴다.

    잡지 않으면 상태가 starting 에 남고 띄운 프로세스가 샌다.
    """
    rig = make_rig(tmp_path)

    def broken_display() -> bool:
        """가상 화면 소켓을 보다가 권한 오류가 난다."""
        raise PermissionError("/tmp/.X11-unix/X99")

    rig.sup._wait_ready = broken_display
    rig.request("r1")

    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.request_id == "r1"
    assert status.password is None
    assert rig.launcher.named("Xvfb").terminated
    assert not rig.browser_profile.exists()
    assert not (rig.work_dir / supervisor.PASSWORD_FILE).exists()

    rig.request("r2")
    rig.sup.tick()

    assert rig.status().request_id == "r2"


def test_an_unusable_work_dir_fails_the_session(tmp_path) -> None:
    """임시 디렉터리를 만들지 못하면 아무것도 띄우지 않고 실패를 쓴다."""
    rig = make_rig(tmp_path)
    rig.work_dir.write_text("not a directory", encoding="utf-8")
    rig.request("r1")

    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.request_id == "r1"
    assert rig.launcher.processes == []
    assert not rig.browser_profile.exists()


def test_a_stubborn_process_is_killed(rig: Rig) -> None:
    """SIGTERM 을 무시하는 자식은 SIGKILL 로 끝낸다."""
    rig.request("r1")
    rig.sup.tick()
    rig.launcher.cli.ignore_term = True

    rig.request("r2", login_protocol.Action.CANCEL)
    rig.sup.tick()

    assert rig.launcher.cli.killed
    assert rig.status().state is login_protocol.State.CANCELLED


def test_recover_marks_a_leftover_session_failed(rig: Rig) -> None:
    """재시작 전의 세션이 남아 있으면 정리하고 실패로 쓴다."""
    login_protocol.write_status(
        rig.login_dir,
        login_protocol.Status(
            state=login_protocol.State.RUNNING,
            request_id="r0",
            password="old",
        ),
    )

    rig.sup.recover()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.request_id == "r0"
    assert status.detail == supervisor.DETAIL_RESTARTED
    assert status.password is None
    assert not rig.browser_profile.exists()


def test_recover_leaves_a_finished_result_alone(rig: Rig) -> None:
    """이미 끝난 결과는 그대로 둔다."""
    finished = login_protocol.Status(
        state=login_protocol.State.SUCCEEDED, request_id="r0"
    )
    login_protocol.write_status(rig.login_dir, finished)

    rig.sup.recover()

    assert rig.status() == finished


def test_recover_always_removes_the_browser_profile(rig: Rig) -> None:
    """끝난 결과만 남아 있어도 크로미움 프로필은 지운다.

    프로필은 계정 동등 자격증명이다. 지우는 것은 멱등하고 싸다.
    """
    login_protocol.write_status(
        rig.login_dir,
        login_protocol.Status(
            state=login_protocol.State.SUCCEEDED, request_id="r0"
        ),
    )

    rig.sup.recover()

    assert not rig.browser_profile.exists()


def test_a_stale_display_socket_is_removed_before_xvfb(tmp_path) -> None:
    """이전 Xvfb 가 남긴 소켓을 지운 뒤 새 Xvfb 를 띄운다.

    남아 있으면 가상 화면이 뜨기도 전에 떴다고 판정한다.
    """
    socket = tmp_path / "X99"
    socket.write_text("", encoding="utf-8")
    seen: list[bool] = []
    rig = make_rig(tmp_path, display_socket=socket)
    launcher = rig.launcher

    def launch(argv, env, log_path) -> FakeProcess:
        """Xvfb 를 띄우는 순간 소켓이 남아 있는지 기록한다."""
        if argv[0] == "Xvfb":
            seen.append(socket.exists())
        return launcher(argv, env, log_path)

    rig.sup._launch = launch
    rig.request("r1")

    rig.sup.tick()

    assert seen == [False]
    assert rig.status().state is login_protocol.State.RUNNING


def test_recover_does_not_replay_the_last_request(rig: Rig) -> None:
    """재시작 전의 시작 요청이 사람 없이 다시 실행되지 않는다."""
    rig.request("r0")

    rig.sup.recover()
    rig.sup.tick()

    assert rig.launcher.processes == []


@pytest.mark.parametrize(
    "leftover",
    [
        None,
        login_protocol.Status(
            state=login_protocol.State.SUCCEEDED, request_id="old"
        ),
    ],
)
def test_recover_answers_a_swallowed_start(
    rig: Rig, leftover: login_protocol.Status | None
) -> None:
    """재시작 직전의 시작 요청에는 그 id 로 실패를 써서 답한다.

    답하지 않으면 그 요청을 지켜보는 탭이 결과를 영영 받지 못한다.
    다시 실행하지는 않는다.
    """
    if leftover is not None:
        login_protocol.write_status(rig.login_dir, leftover)
    rig.request("r0")

    rig.sup.recover()
    rig.sup.tick()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.request_id == "r0"
    assert status.detail == supervisor.DETAIL_RESTARTED
    assert rig.launcher.processes == []


def test_recover_leaves_an_answered_start_alone(rig: Rig) -> None:
    """이미 그 id 로 결과를 썼으면 상태를 바꾸지 않는다."""
    finished = login_protocol.Status(
        state=login_protocol.State.SUCCEEDED, request_id="r0"
    )
    login_protocol.write_status(rig.login_dir, finished)
    rig.request("r0")

    rig.sup.recover()

    assert rig.status() == finished


def test_recover_leaves_a_leftover_cancel_alone(rig: Rig) -> None:
    """남은 취소 요청에는 답하지 않는다. 기다리는 탭이 없다."""
    rig.request("r0", login_protocol.Action.CANCEL)

    rig.sup.recover()

    assert rig.status() == login_protocol.IDLE


def test_recover_answers_a_start_left_by_a_restarted_session(
    rig: Rig,
) -> None:
    """세션 r1 중에 들어온 시작 r2 는 r1 을 정리한 뒤 r2 로 답한다."""
    login_protocol.write_status(
        rig.login_dir,
        login_protocol.Status(
            state=login_protocol.State.RUNNING, request_id="r1", password="p"
        ),
    )
    rig.request("r2")

    rig.sup.recover()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.request_id == "r2"
    assert status.detail == supervisor.DETAIL_RESTARTED


def test_every_tick_refreshes_the_heartbeat(rig: Rig) -> None:
    """앱이 사이드카의 생사를 알 수 있게 매 틱 heartbeat 를 갱신한다."""
    heartbeat = rig.login_dir / login_protocol.HEARTBEAT_FILE

    rig.sup.tick()
    os.utime(heartbeat, (0, 0))
    rig.sup.tick()

    assert heartbeat.stat().st_mtime > 0


def test_a_broken_request_is_ignored(rig: Rig) -> None:
    """반쯤 쓰였거나 깨진 요청은 넘어간다."""
    rig.login_dir.mkdir(parents=True, exist_ok=True)
    (rig.login_dir / login_protocol.REQUEST_FILE).write_text(
        "{", encoding="utf-8"
    )

    rig.sup.tick()

    assert rig.launcher.processes == []


def test_shutdown_ends_a_live_session(rig: Rig) -> None:
    """컨테이너가 내려가면 세션을 정리하고 실패로 남긴다."""
    rig.request("r1")
    rig.sup.tick()

    rig.sup.shutdown()

    status = rig.status()
    assert status.state is login_protocol.State.FAILED
    assert status.detail == supervisor.DETAIL_STOPPED
    assert not rig.browser_profile.exists()


def test_build_wires_the_container_paths(monkeypatch) -> None:
    """진입점은 이미지의 환경변수에서 경로를 잡는다."""
    monkeypatch.setenv(login_protocol.DIR_ENV_VAR, "/data/login")
    monkeypatch.setenv("NOTEBOOKLM_HOME", "/data/notebooklm")

    built = supervisor.build()

    assert built._login_dir == pathlib.Path("/data/login")
    assert built._browser_profile == pathlib.Path(
        "/data/notebooklm/profiles/default/browser_profile"
    )
    assert built._env["NO_COLOR"] == "1"
    assert built._display_socket == supervisor.X_SOCKET
