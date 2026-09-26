"""앱 쪽 원격 로그인 세션 조회 테스트."""

import datetime as dt
import logging
import os

from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State
from notebooklm_st.services import digest_runner, login_session, runs


def test_viewer_url_is_none_when_unset() -> None:
    """설정이 없으면 원격 로그인을 끈다."""
    assert login_session.viewer_url() is None


def test_viewer_url_drops_a_trailing_slash(monkeypatch) -> None:
    """끝의 / 를 떼어 경로를 이어 붙이기 쉽게 한다."""
    monkeypatch.setenv(
        login_session.VIEWER_URL_ENV_VAR, " http://192.168.0.10:9005/ "
    )

    assert login_session.viewer_url() == "http://192.168.0.10:9005"


def test_login_dir_follows_the_environment(monkeypatch, tmp_path) -> None:
    """신호 디렉터리는 환경변수가 정한다."""
    assert login_session.login_dir() is None

    monkeypatch.setenv(login_protocol.DIR_ENV_VAR, str(tmp_path))

    assert login_session.login_dir() == tmp_path


def test_read_status_treats_a_missing_file_as_idle(tmp_path) -> None:
    """사이드카가 아직 아무것도 쓰지 않았으면 idle 이다."""
    assert login_session.read_status(tmp_path).state is State.IDLE


def test_read_status_treats_a_broken_file_as_idle(tmp_path, caplog) -> None:
    """깨진 상태 파일은 idle 로 보고 경고만 남긴다."""
    (tmp_path / login_protocol.STATUS_FILE).write_text("{", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        status = login_session.read_status(tmp_path)

    assert status.state is State.IDLE
    assert "상태 파일" in caplog.text


def test_sidecar_alive_checks_the_heartbeat_age(tmp_path) -> None:
    """Heartbeat 가 10초 안에 갱신됐으면 살아 있다."""
    heartbeat = tmp_path / login_protocol.HEARTBEAT_FILE
    assert login_session.sidecar_alive(tmp_path, now=1000.0) is False

    heartbeat.touch()
    os.utime(heartbeat, (1000.0, 1000.0))

    assert login_session.sidecar_alive(tmp_path, now=1010.0) is True
    assert login_session.sidecar_alive(tmp_path, now=1010.5) is False


def test_request_start_writes_a_fresh_request(tmp_path) -> None:
    """시작 요청은 매번 새 id 로 쓴다."""
    directory = tmp_path / "login"

    first = login_session.request_start(directory)
    second = login_session.request_start(directory)

    request = login_session.pending_request(directory)
    assert first != second
    assert request is not None
    assert request.id == second
    assert request.action is Action.START


def test_request_cancel_writes_a_cancel(tmp_path) -> None:
    """취소 요청도 새 id 를 갖는다."""
    request_id = login_session.request_cancel(tmp_path)

    request = login_session.pending_request(tmp_path)
    assert request is not None
    assert request.id == request_id
    assert request.action is Action.CANCEL


def test_pending_request_ignores_a_broken_file(tmp_path) -> None:
    """깨진 요청 파일은 없는 것으로 본다."""
    (tmp_path / login_protocol.REQUEST_FILE).write_text("[", encoding="utf-8")

    assert login_session.pending_request(tmp_path) is None


def test_busy_sees_a_running_query() -> None:
    """질의가 돌고 있으면 바쁘다."""
    registry = runs.RunRegistry()
    registry.create("https://youtu.be/x", "x", ("q",))

    assert login_session.busy(registry, digest_runner.DigestRegistry())


def test_busy_sees_a_running_digest() -> None:
    """정리본을 쓰고 있으면 바쁘다."""
    digests = digest_runner.DigestRegistry()
    digests.start()

    assert login_session.busy(runs.RunRegistry(), digests)


def test_not_busy_when_nothing_runs() -> None:
    """아무것도 돌지 않으면 한가하다."""
    assert not login_session.busy(
        runs.RunRegistry(), digest_runner.DigestRegistry()
    )


def test_viewer_link_puts_the_password_in_the_hash() -> None:
    """비밀번호는 서버로 가지 않는 해시에 둔다."""
    link = login_session.viewer_link("http://h:9005", "pw123456")

    assert link == (
        "http://h:9005/vnc.html#autoconnect=1&resize=scale&password=pw123456"
    )


def test_remaining_seconds_counts_down_to_the_deadline() -> None:
    """마감까지 남은 초. 지났으면 0, 마감이 없으면 None."""
    now = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.UTC)
    status = login_protocol.Status(
        state=State.RUNNING, deadline="2026-09-26T12:01:30+00:00"
    )

    assert login_session.remaining_seconds(status, now) == 90
    assert (
        login_session.remaining_seconds(status, now + dt.timedelta(minutes=5))
        == 0
    )
    assert login_session.remaining_seconds(login_protocol.IDLE, now) is None
