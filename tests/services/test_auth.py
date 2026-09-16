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
    """호출 횟수를 세는 가짜 probe.

    결과 목록에 예외를 섞어 두면 그 차례에 그 예외를 던진다.
    """

    def __init__(self, results):
        """돌려줄 결과 목록을 저장한다."""
        self._results = list(results)
        self.calls = 0

    def __call__(self):
        """다음 결과를 돌려주거나 던지고 호출을 센다."""
        self.calls += 1
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_gate(probe_results):
    """정해진 결과를 내는 게이트와 그 가짜 probe 를 만든다."""
    probe = Recorder(probe_results)
    return auth.AuthGate(probe=probe), probe


def test_gate_checks_only_once() -> None:
    """앱이 떠 있는 동안 자동 확인은 한 번만 돈다."""
    gate, probe = make_gate([True])

    gate.ensure()
    gate.ensure()

    assert probe.calls == 1


def test_gate_caches_the_probe_result() -> None:
    """두 번째 ensure 는 캐시된 판정을 그대로 돌려준다."""
    gate, _ = make_gate([True])

    assert gate.ensure() is True
    assert gate.ensure() is True
    assert gate.ok is True


def test_gate_reports_whether_it_has_run() -> None:
    """자동 확인을 이미 돌렸는지 알려 준다."""
    gate, _ = make_gate([True])

    assert gate.tried is False
    gate.ensure()
    assert gate.tried is True


def test_recheck_probes_again_ignoring_the_cache() -> None:
    """다시 확인은 캐시를 무시하고 probe 를 또 부른다."""
    gate, probe = make_gate([False, False])
    gate.ensure()

    gate.recheck()

    assert probe.calls == 2


def test_recheck_revives_a_failed_gate() -> None:
    """프로필을 갈아 끼운 뒤 다시 확인하면 인증이 되살아난다."""
    gate, _ = make_gate([False, True])
    assert gate.ensure() is False

    assert gate.recheck() is True
    assert gate.ok is True


def test_gate_records_a_failed_probe() -> None:
    """확인 자체가 실패하면 예외를 보관하고 만료로 본다."""
    boom = RuntimeError("boom")
    gate, _ = make_gate([boom])

    assert gate.ensure() is False
    assert gate.probe_error is boom


def test_gate_keeps_the_probe_error_cached() -> None:
    """재실행으로 ensure 를 또 불러도 확인 불가 상태가 남는다."""
    boom = RuntimeError("boom")
    gate, probe = make_gate([boom])
    gate.ensure()

    gate.ensure()

    assert probe.calls == 1
    assert gate.probe_error is boom


def test_recheck_clears_a_stale_probe_error() -> None:
    """되살아나면 보관하던 예외도 지운다."""
    gate, _ = make_gate([RuntimeError("boom"), True])
    gate.ensure()

    assert gate.recheck() is True
    assert gate.probe_error is None
