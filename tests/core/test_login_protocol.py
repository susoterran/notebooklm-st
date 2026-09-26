"""원격 로그인 신호 파일 계약 테스트."""

import stat
import sys

import pytest

from notebooklm_st.core import login_protocol
from notebooklm_st.core.login_protocol import Action, State


def test_request_round_trips_through_json() -> None:
    """요청은 JSON 으로 갔다 와도 같다."""
    request = login_protocol.Request(
        id="r1", action=Action.START, requested_at="2026-09-26T12:00:00+00:00"
    )

    assert login_protocol.Request.from_json(request.to_json()) == request


def test_status_round_trips_through_json() -> None:
    """상태는 JSON 으로 갔다 와도 같다."""
    status = login_protocol.Status(
        state=State.RUNNING,
        request_id="r1",
        password="pw123456",
        deadline="2026-09-26T12:05:00+00:00",
        updated_at="2026-09-26T12:00:00+00:00",
    )

    assert login_protocol.Status.from_json(status.to_json()) == status


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        '{"action": "start", "requested_at": "x"}',
        '{"id": "r1", "action": "jump", "requested_at": "x"}',
        '{"id": "r1", "action": "start", "requested_at": 3}',
    ],
)
def test_a_malformed_request_raises_a_protocol_error(text: str) -> None:
    """계약과 다른 요청은 ProtocolError 로 알린다."""
    with pytest.raises(login_protocol.ProtocolError):
        login_protocol.Request.from_json(text)


@pytest.mark.parametrize(
    "text",
    ["{", '{"state": "flying"}', '{"state": "running", "password": 1}'],
)
def test_a_malformed_status_raises_a_protocol_error(text: str) -> None:
    """계약과 다른 상태는 ProtocolError 로 알린다."""
    with pytest.raises(login_protocol.ProtocolError):
        login_protocol.Status.from_json(text)


def test_missing_files_read_as_nothing(tmp_path) -> None:
    """아직 아무도 쓰지 않았으면 요청은 없고 상태는 idle 이다."""
    assert login_protocol.read_request(tmp_path) is None
    assert login_protocol.read_status(tmp_path) == login_protocol.IDLE


def test_written_files_read_back(tmp_path) -> None:
    """쓴 것을 그대로 읽는다. 디렉터리가 없으면 만든다."""
    directory = tmp_path / "login"
    request = login_protocol.Request(
        id="r1", action=Action.CANCEL, requested_at="t"
    )
    status = login_protocol.Status(state=State.FAILED, detail="끝")

    login_protocol.write_request(directory, request)
    login_protocol.write_status(directory, status)

    assert login_protocol.read_request(directory) == request
    assert login_protocol.read_status(directory) == status


def test_write_atomic_leaves_no_temporary_file(tmp_path) -> None:
    """바꿔치기가 끝나면 임시 파일이 남지 않는다."""
    login_protocol.write_atomic(tmp_path / "status.json", "{}")

    assert [path.name for path in tmp_path.iterdir()] == ["status.json"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX 권한만 확인한다")
def test_write_atomic_keeps_the_file_private(tmp_path) -> None:
    """세션 비밀번호를 담으므로 소유자만 읽는다."""
    path = tmp_path / "status.json"

    login_protocol.write_atomic(path, "{}")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_active_states_are_the_ones_with_a_live_session() -> None:
    """세션이 떠 있는 상태는 starting 과 running 뿐이다."""
    assert {State.STARTING, State.RUNNING} == login_protocol.ACTIVE_STATES
