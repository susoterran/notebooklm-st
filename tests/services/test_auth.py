"""인증 확인과 재로그인 테스트."""

import contextlib

import pytest
from notebooklm._auth import extraction as auth_extraction

from notebooklm_st.services import auth


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
