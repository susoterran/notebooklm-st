"""인증 확인과 재로그인 테스트."""

import contextlib
import subprocess
import sys

import pytest
from notebooklm._auth import extraction as auth_extraction

from notebooklm_st.services import auth


class FakeStdout:
    """자식 프로세스의 표준 출력을 흉내내는 반복자."""

    def __init__(self, lines):
        """돌려줄 줄 목록을 저장한다."""
        self._lines = list(lines)

    def __iter__(self):
        """줄 끝 개행까지 붙여 그대로 흘려 보낸다."""
        return iter(f"{line}\n" for line in self._lines)


class FakeProcess:
    """자식 프로세스를 흉내낸다."""

    def __init__(self, lines=(), code=0, wait_error=None):
        """출력 줄, 종료 코드, wait 가 낼 예외를 저장한다."""
        self.stdout = FakeStdout(lines)
        self.pid = 4242
        self.killed = False
        self._code = code
        self._wait_error = wait_error

    def wait(self, timeout=None):
        """저장된 종료 코드를 돌려주거나 예외를 낸다."""
        if self._wait_error is not None:
            error, self._wait_error = self._wait_error, None
            raise error
        return self._code

    def kill(self):
        """종료 요청을 기록한다."""
        self.killed = True


def fake_popen_factory(process, calls):
    """호출 인자를 기록하고 준비된 가짜 프로세스를 돌려준다."""

    def popen(command, **kwargs):
        """Popen 을 대신한다."""
        calls.append((command, kwargs))
        return process

    return popen


def factory_yielding_client():
    """정상적으로 열리는 클라이언트 팩토리."""

    @contextlib.asynccontextmanager
    async def opened():
        """아무 일도 하지 않는 클라이언트를 내준다."""
        yield object()

    return opened()


def factory_raising(error):
    """열 때 주어진 예외를 내는 클라이언트 팩토리를 만든다."""

    def make():
        """컨텍스트 매니저를 만든다."""

        @contextlib.asynccontextmanager
        async def failing():
            """열자마자 예외를 낸다."""
            raise error
            yield  # pragma: no cover - 도달하지 않는다

        return failing()

    return make


def test_probe_reports_authenticated_when_client_opens() -> None:
    """클라이언트가 열리면 인증된 것으로 본다."""
    assert auth.is_authenticated(factory_yielding_client) is True


def test_probe_reports_expired_on_login_redirect() -> None:
    """로그인 리다이렉트는 인증 만료로 본다."""
    error = auth_extraction._LoginRedirectError("redirect")

    assert auth.is_authenticated(factory_raising(error)) is False


def test_probe_lets_unmapped_errors_through() -> None:
    """화면 문구로 바꿀 수 없는 예외는 삼키지 않는다."""
    with pytest.raises(RuntimeError):
        auth.is_authenticated(factory_raising(RuntimeError("boom")))


def test_login_runs_current_interpreter() -> None:
    """Uv 나 PATH 에 기대지 않고 자기 인터프리터로 CLI 를 부른다."""
    calls: list[tuple] = []
    popen = fake_popen_factory(FakeProcess(), calls)

    auth.run_login(lambda message: None, popen=popen)

    command, _ = calls[0]
    assert command == [sys.executable, "-m", "notebooklm", "login"]


def test_login_reports_each_output_line() -> None:
    """자식의 진행 문구를 한 줄씩 콜백으로 넘긴다."""
    lines = ["Opening Chromium for Google login...", "Already logged in."]
    popen = fake_popen_factory(FakeProcess(lines=lines), [])
    seen: list[str] = []

    auth.run_login(seen.append, popen=popen)

    assert seen == lines


def test_login_succeeds_on_zero_exit() -> None:
    """종료 코드 0 이면 성공이다."""
    popen = fake_popen_factory(FakeProcess(code=0), [])

    assert auth.run_login(lambda message: None, popen=popen) is True


def test_login_fails_on_nonzero_exit() -> None:
    """종료 코드가 0 이 아니면 실패다."""
    popen = fake_popen_factory(FakeProcess(code=1), [])

    assert auth.run_login(lambda message: None, popen=popen) is False


def test_login_kills_child_on_timeout() -> None:
    """제한 시간을 넘기면 자식을 죽이고 실패로 돌려준다."""
    expired = subprocess.TimeoutExpired(cmd="notebooklm login", timeout=1)
    process = FakeProcess(code=0, wait_error=expired)
    popen = fake_popen_factory(process, [])

    result = auth.run_login(lambda message: None, popen=popen)

    assert result is False
    assert process.killed is True


def test_login_reports_the_exit_code_when_the_child_says_nothing() -> None:
    """아무 말 없이 죽은 자식도 종료 코드는 알려 준다."""
    popen = fake_popen_factory(FakeProcess(code=9), [])
    seen: list[str] = []

    auth.run_login(seen.append, popen=popen)

    assert seen
    assert "9" in seen[-1]


def test_login_reports_the_timeout() -> None:
    """제한 시간 초과도 화면에 남긴다."""
    expired = subprocess.TimeoutExpired(cmd="notebooklm login", timeout=1)
    popen = fake_popen_factory(FakeProcess(wait_error=expired), [])
    seen: list[str] = []

    auth.run_login(seen.append, timeout=30.0, popen=popen)

    assert seen
    assert "30" in seen[-1]


class Recorder:
    """호출 횟수를 세는 가짜 함수."""

    def __init__(self, results):
        """돌려줄 결과 목록을 저장한다."""
        self._results = list(results)
        self.calls = 0

    def __call__(self, *args):
        """다음 결과를 돌려주고 호출을 센다."""
        self.calls += 1
        return self._results.pop(0)


def make_gate(probe_results, login_results=()):
    """정해진 결과를 내는 게이트와 그 가짜들을 만든다."""
    probe = Recorder(probe_results)
    login = Recorder(login_results)
    return auth.AuthGate(probe=probe, login=login), probe, login


def test_gate_checks_only_once() -> None:
    """앱이 떠 있는 동안 자동 확인은 한 번만 돈다."""
    gate, probe, _ = make_gate([True])

    gate.ensure(lambda message: None)
    gate.ensure(lambda message: None)

    assert probe.calls == 1


def test_gate_skips_login_when_already_authenticated() -> None:
    """인증이 살아 있으면 브라우저를 띄우지 않는다."""
    gate, _, login = make_gate([True])

    assert gate.ensure(lambda message: None) is True
    assert login.calls == 0


def test_gate_logs_in_when_check_fails() -> None:
    """확인이 실패하면 브라우저 로그인으로 되살린다."""
    gate, _, login = make_gate([False], [True])

    assert gate.ensure(lambda message: None) is True
    assert login.calls == 1


def test_gate_reports_failure_when_login_also_fails() -> None:
    """로그인까지 실패하면 실패로 남는다."""
    gate, _, _ = make_gate([False], [False])

    assert gate.ensure(lambda message: None) is False
    assert gate.ok is False


def test_relogin_rechecks_before_opening_a_browser() -> None:
    """자동 확인이 실패한 뒤 인증이 되살아났으면 브라우저를 안 띄운다."""
    gate, probe, login = make_gate([False, True], [False])
    gate.ensure(lambda message: None)

    assert gate.relogin(lambda message: None) is True
    assert probe.calls == 2
    assert login.calls == 1


def test_relogin_logs_in_when_the_recheck_also_fails() -> None:
    """다시 확인해도 만료면 그때 브라우저 로그인을 돌린다."""
    gate, probe, login = make_gate([False, False], [False, True])
    gate.ensure(lambda message: None)

    assert gate.relogin(lambda message: None) is True
    assert probe.calls == 2
    assert login.calls == 2


def test_gate_never_leaves_the_progress_box_empty() -> None:
    """확인만 하고 끝나도 진행 문구를 한 줄은 남긴다."""
    gate, _, _ = make_gate([True])
    seen: list[str] = []

    gate.ensure(seen.append)

    assert seen


def test_gate_reports_whether_it_has_run() -> None:
    """자동 확인을 이미 돌렸는지 알려 준다."""
    gate, _, _ = make_gate([True])

    assert gate.tried is False
    gate.ensure(lambda message: None)
    assert gate.tried is True
