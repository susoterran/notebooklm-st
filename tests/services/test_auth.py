"""인증 확인·게이트·자격증명 반입 테스트."""

import contextlib
import subprocess
import sys

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


class FakeCompleted:
    """``subprocess.run`` 의 반환값을 흉내낸다."""

    def __init__(self, returncode, stdout=b"", stderr=b""):
        """종료 코드와 출력을 저장한다."""
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_runner(result, calls):
    """호출 인자를 기록하고 준비된 결과를 돌려주는 러너를 만든다."""

    def run(args, **kwargs):
        """subprocess.run 을 대신한다."""
        calls.append((args, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    return run


def test_import_credentials_feeds_the_payload_to_stdin() -> None:
    """자기 인터프리터로 CLI 를 부르고 payload 를 stdin 으로 넘긴다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0), calls)

    result = auth.import_credentials(b'{"cookies": []}', runner=runner)

    assert result.ok is True
    args, kwargs = calls[0]
    assert args[0] == sys.executable
    assert args[1:] == [
        "-m",
        "notebooklm",
        "auth",
        "import-cookies",
        "-",
    ]
    assert kwargs["input"] == b'{"cookies": []}'


def test_import_credentials_reports_a_nonzero_exit() -> None:
    """종료 코드가 0 이 아니면 실패로 보고 사유를 담는다."""
    runner = fake_runner(
        FakeCompleted(1, stderr="쿠키가 모자랍니다".encode()), []
    )

    result = auth.import_credentials(b"{}", runner=runner)

    assert result.ok is False
    assert "쿠키가 모자랍니다" in result.detail


def test_import_credentials_reports_a_timeout() -> None:
    """제한 시간 안에 안 끝나면 그 사실을 알린다."""
    runner = fake_runner(
        subprocess.TimeoutExpired(cmd="notebooklm", timeout=30.0), []
    )

    result = auth.import_credentials(b"{}", runner=runner)

    assert result.ok is False
    assert "30" in result.detail


def test_import_credentials_rejects_an_oversized_payload() -> None:
    """상한을 넘는 입력은 CLI 에 넘기기 전에 거절한다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0), calls)
    payload = b"x" * (auth.MAX_PAYLOAD_BYTES + 1)

    result = auth.import_credentials(payload, runner=runner)

    assert result.ok is False
    assert not calls


def test_import_credentials_rejects_an_empty_payload() -> None:
    """빈 파일은 CLI 에 넘기지 않는다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0), calls)

    result = auth.import_credentials(b"", runner=runner)

    assert result.ok is False
    assert not calls


def test_import_credentials_does_not_probe(monkeypatch) -> None:
    """반입은 스스로 인증을 확인하지 않는다. 판정은 recheck 가 한다.

    ``import_credentials`` 가 내부에서 "친절하게" 재확인을 끼워
    넣으면 이 테스트가 실패한다. 판정은 ``AuthGate._verify`` 한
    곳에서만 일어나야 한다(스펙 §5.4).
    """
    calls = 0

    def spy() -> bool:
        """호출 횟수만 세는 가짜 ``is_authenticated``."""
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(auth, "is_authenticated", spy)

    auth.import_credentials(b"{}", runner=fake_runner(FakeCompleted(0), []))

    assert calls == 0
