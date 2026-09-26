"""인증 페이지의 원격 구글 로그인 영역 테스트."""

import datetime as dt
import os
import pathlib

import pytest
from streamlit.testing import v1

from notebooklm_st import session
from notebooklm_st.core import login_protocol
from notebooklm_st.services import auth, login_session

VIEWER = "http://192.168.0.10:9005"


def _script():
    """AppTest 진입점 — 원격 로그인 영역만 그린다."""
    from notebooklm_st import session
    from notebooklm_st.pages import _remote_login

    _remote_login.render(session.get_auth_gate())


@pytest.fixture
def login_dir(monkeypatch, tmp_path) -> pathlib.Path:
    """원격 로그인을 켜고, 살아 있는 사이드카를 흉내 낸다."""
    directory = tmp_path / "login"
    directory.mkdir()
    monkeypatch.setenv(login_session.VIEWER_URL_ENV_VAR, VIEWER)
    monkeypatch.setenv(login_protocol.DIR_ENV_VAR, str(directory))
    (directory / login_protocol.HEARTBEAT_FILE).touch()
    return directory


def _write(directory: pathlib.Path, **fields) -> None:
    """사이드카 대신 상태를 쓴다."""
    login_protocol.write_status(directory, login_protocol.Status(**fields))


def test_nothing_is_drawn_without_a_viewer_url() -> None:
    """설정이 없으면 영역 자체를 그리지 않는다."""
    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert len(app.subheader) == 0
    assert len(app.button) == 0


def test_a_silent_sidecar_is_reported(login_dir) -> None:
    """Heartbeat 가 멈췄으면 꺼져 있다고 알리고 시작 버튼을 숨긴다."""
    os.utime(login_dir / login_protocol.HEARTBEAT_FILE, (0, 0))

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert any("꺼져 있습니다" in box.value for box in app.warning)
    assert len(app.button) == 0


def test_idle_offers_the_start_button(login_dir) -> None:
    """대기 중이면 시작 버튼을 켠다."""
    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert app.button(key="remote_login_start").disabled is False


def test_a_busy_app_disables_the_start_button(login_dir, monkeypatch) -> None:
    """질의·정리본이 돌고 있으면 시작을 막는다."""
    monkeypatch.setattr(login_session, "busy", lambda *args: True)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert app.button(key="remote_login_start").disabled is True
    assert any("끝난 뒤" in text.value for text in app.caption)


def test_start_writes_a_request_and_waits(login_dir) -> None:
    """시작을 누르면 요청을 쓰고 준비 중으로 바뀐다."""
    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_start").click().run()

    request = login_protocol.read_request(login_dir)
    assert not app.exception
    assert request is not None
    assert request.action is login_protocol.Action.START
    assert any("준비하는 중" in box.value for box in app.info)


def test_a_running_session_shows_the_viewer(login_dir) -> None:
    """세션이 뜨면 비밀번호를 해시에 담은 iframe 과 취소 버튼을 그린다."""
    deadline = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=2)
    _write(
        login_dir,
        state=login_protocol.State.RUNNING,
        request_id="r1",
        password="pw123456",
        deadline=deadline.isoformat(timespec="seconds"),
    )

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    frames = [frame.proto.src for frame in app.get("iframe")]
    assert frames == [
        f"{VIEWER}/vnc.html#autoconnect=1&resize=scale&password=pw123456"
    ]
    assert app.button(key="remote_login_cancel") is not None
    shown = " ".join(
        element.value for element in [*app.caption, *app.info, *app.markdown]
    )
    assert "pw123456" not in shown


def test_cancel_writes_a_cancel_request(login_dir) -> None:
    """취소를 누르면 취소 요청을 쓴다."""
    _write(
        login_dir,
        state=login_protocol.State.RUNNING,
        request_id="r1",
        password="pw",
    )

    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_cancel").click().run()

    request = login_protocol.read_request(login_dir)
    assert not app.exception
    assert request is not None
    assert request.action is login_protocol.Action.CANCEL


def test_a_watched_success_rechecks_once(login_dir, monkeypatch) -> None:
    """지켜보던 로그인이 성공하면 한 번만 다시 확인하고 알린다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 살아 있다고 답한다."""
        calls.append(1)
        return True

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_start").click().run()
    request = login_protocol.read_request(login_dir)
    assert request is not None

    _write(
        login_dir, state=login_protocol.State.SUCCEEDED, request_id=request.id
    )
    app.run()

    assert not app.exception
    assert len(calls) == 1
    assert any("인증되었습니다" in box.value for box in app.success)

    app.run()

    assert len(calls) == 1


def test_a_watched_failure_shows_the_reason(login_dir) -> None:
    """지켜보던 로그인이 실패하면 사유를 보여 준다."""
    app = v1.AppTest.from_function(_script)
    app.run()
    app.button(key="remote_login_start").click().run()
    request = login_protocol.read_request(login_dir)
    assert request is not None

    _write(
        login_dir,
        state=login_protocol.State.FAILED,
        request_id=request.id,
        detail="Error: boom",
    )
    app.run()

    assert not app.exception
    assert any("Error: boom" in box.value for box in app.error)


def test_an_unwatched_success_is_only_reported(login_dir, monkeypatch) -> None:
    """지켜보지 않던 결과는 한 줄로만 보여 주고 다시 확인하지 않는다."""
    calls = []

    def probe() -> bool:
        """호출을 세고 살아 있다고 답한다."""
        calls.append(1)
        return True

    gate = auth.AuthGate(probe=probe)
    monkeypatch.setattr(session, "get_auth_gate", lambda: gate)
    _write(login_dir, state=login_protocol.State.SUCCEEDED, request_id="old")

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert calls == []
    assert len(app.success) == 0
    assert any("마지막 로그인: 성공" in text.value for text in app.caption)


def test_a_leftover_cancel_does_not_look_pending(login_dir) -> None:
    """세션 없이 남은 취소 요청은 준비 중으로 보이지 않는다."""
    login_session.request_cancel(login_dir)

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert len(app.info) == 0
    assert app.button(key="remote_login_start") is not None


def test_a_broken_status_file_still_offers_the_start_button(login_dir) -> None:
    """상태 파일이 깨져도 트레이스백 없이 시작 버튼을 그린다."""
    (login_dir / login_protocol.STATUS_FILE).write_text("{", encoding="utf-8")

    app = v1.AppTest.from_function(_script).run()

    assert not app.exception
    assert app.button(key="remote_login_start") is not None
