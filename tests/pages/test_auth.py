"""인증 페이지 테스트."""

from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.services import auth


def _script():
    """AppTest 진입점 — 인증 페이지를 그린다."""
    from notebooklm_st.pages import auth as auth_page

    auth_page.render()


def test_page_says_so_when_authenticated(stub_auth_gate) -> None:
    """인증이 살아 있으면 그렇다고 알린다."""
    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert any("인증되어 있습니다" in box.value for box in app.success)


def test_page_reports_an_expiry(monkeypatch) -> None:
    """만료되면 경고로 알린다."""
    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert any("만료" in box.value for box in app.warning)


def test_page_separates_a_failed_probe(monkeypatch) -> None:
    """확인 자체가 실패하면 타입 이름만 담아 알린다."""

    def probe() -> bool:
        """매핑되지 않은 예외를 던진다."""
        raise RuntimeError("https://accounts.google.com/secret")

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert len(app.error) == 1
    assert "RuntimeError" in app.error[0].value
    assert "accounts.google.com" not in app.error[0].value


def test_recheck_probes_again(monkeypatch) -> None:
    """다시 확인은 판정을 새로 돌린다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 계속 만료로 답한다."""
        calls.append(1)
        return False

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="auth_page_recheck").click().run()

    assert not app.exception
    assert len(calls) == 2


def test_the_page_imports_an_uploaded_credential(monkeypatch) -> None:
    """올린 자격증명을 반입하고 곧바로 다시 확인한다."""
    seen: list[bytes] = []
    results = iter([False, True])

    def fake_import(payload: bytes) -> auth.ImportResult:
        """반입 호출을 기록하고 성공으로 답한다."""
        seen.append(payload)
        return auth.ImportResult(ok=True, detail="반입했습니다")

    gate = auth.AuthGate(probe=lambda: next(results, True))
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.file_uploader(key="auth_page_upload").set_value(
        ("storage_state.json", b'{"cookies": []}', "application/json")
    )
    app.run()
    app.button(key="auth_page_import").click().run()

    assert not app.exception
    assert seen == [b'{"cookies": []}']
    assert gate.ok is True


def test_an_import_that_stays_expired_is_not_a_success(monkeypatch) -> None:
    """반입은 성공해도 다시 확인이 실패하면 성공 취급하지 않는다.

    ``st.rerun()`` 은 ``NoReturn`` 이라 타입 체커가 이 분기 순서를
    지켜 주지 않는다. 분기가 뒤집히면 이 테스트만 잡아낸다.
    """

    def fake_import(payload: bytes) -> auth.ImportResult:
        """성공으로 답한다."""
        return auth.ImportResult(ok=True, detail="반입했습니다")

    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.file_uploader(key="auth_page_upload").set_value(
        ("storage_state.json", b"{}", "application/json")
    )
    app.run()
    app.button(key="auth_page_import").click().run()

    assert not app.exception
    assert any("살아나지 않았습니다" in box.value for box in app.error)
    assert gate.ok is False


def test_a_failed_import_is_reported(monkeypatch) -> None:
    """반입이 실패하면 사유를 보여 주고 판정을 바꾸지 않는다."""

    def fake_import(payload: bytes) -> auth.ImportResult:
        """실패로 답한다."""
        return auth.ImportResult(ok=False, detail="쿠키가 모자랍니다")

    gate = auth.AuthGate(probe=lambda: False)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    monkeypatch.setattr(auth, "import_credentials", fake_import)

    app = v1.AppTest.from_function(_script)
    app.run()
    app.file_uploader(key="auth_page_upload").set_value(
        ("storage_state.json", b"{}", "application/json")
    )
    app.run()
    app.button(key="auth_page_import").click().run()

    assert not app.exception
    assert any("쿠키가 모자랍니다" in box.value for box in app.error)
    assert gate.ok is False
