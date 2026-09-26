"""원격 로그인 사이드카와 앱이 주고받는 파일의 계약.

두 컨테이너는 공유 볼륨의 파일 세 개로만 신호를 주고받는다. 파일마다
쓰는 쪽이 하나라 잠금이 필요 없다.

- ``request.json`` — 앱만 쓴다. 로그인 시작·취소 요청
- ``status.json`` — 사이드카만 쓴다. 세션 상태와 마지막 결과
- ``heartbeat`` — 사이드카만 쓴다. 수정 시각만 의미가 있다

표준 라이브러리만 쓴다. 사이드카 이미지에는 앱의 의존성이 없다.

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §5
"""

import dataclasses
import datetime as dt
import enum
import json
import os
import tempfile
from pathlib import Path

DIR_ENV_VAR = "NOTEBOOKLM_ST_LOGIN_DIR"
REQUEST_FILE = "request.json"
STATUS_FILE = "status.json"
HEARTBEAT_FILE = "heartbeat"


class State(enum.StrEnum):
    """로그인 세션의 상태."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


ACTIVE_STATES = frozenset({State.STARTING, State.RUNNING})
"""세션이 떠 있는 상태. 나머지는 대기이거나 마지막 결과다."""


class Action(enum.StrEnum):
    """앱이 사이드카에 보내는 요청의 종류."""

    START = "start"
    CANCEL = "cancel"


class ProtocolError(ValueError):
    """파일 내용이 계약과 다르다."""


@dataclasses.dataclass(frozen=True, slots=True)
class Request:
    """앱이 쓰는 요청.

    ``id`` 는 요청마다 새로 만든다. 사이드카는 같은 ``id`` 를 두 번
    처리하지 않는다.
    """

    id: str
    action: Action
    requested_at: str

    def to_json(self) -> str:
        """JSON 문자열로 바꾼다."""
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Request":
        """JSON 문자열을 읽는다.

        Raises:
            ProtocolError: 계약과 다른 내용일 때.
        """
        data = _load_object(text)
        try:
            action = Action(_required_str(data, "action"))
        except ValueError as error:
            raise ProtocolError(f"알 수 없는 요청입니다: {error}") from error
        return cls(
            id=_required_str(data, "id"),
            action=action,
            requested_at=_required_str(data, "requested_at"),
        )


@dataclasses.dataclass(frozen=True, slots=True)
class Status:
    """사이드카가 쓰는 세션 상태.

    ``password`` 와 ``deadline`` 은 ``running`` 일 때만 값이 있다.
    """

    state: State
    request_id: str | None = None
    password: str | None = None
    deadline: str | None = None
    detail: str | None = None
    updated_at: str | None = None

    def to_json(self) -> str:
        """JSON 문자열로 바꾼다."""
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Status":
        """JSON 문자열을 읽는다.

        Raises:
            ProtocolError: 계약과 다른 내용일 때.
        """
        data = _load_object(text)
        try:
            state = State(_required_str(data, "state"))
        except ValueError as error:
            raise ProtocolError(f"알 수 없는 상태입니다: {error}") from error
        return cls(
            state=state,
            request_id=_optional_str(data, "request_id"),
            password=_optional_str(data, "password"),
            deadline=_optional_str(data, "deadline"),
            detail=_optional_str(data, "detail"),
            updated_at=_optional_str(data, "updated_at"),
        )


IDLE = Status(state=State.IDLE)
"""아직 아무도 상태를 쓰지 않았을 때."""


def now_iso() -> str:
    """지금 시각을 UTC ISO 8601 로 돌려준다.

    두 컨테이너의 시간대 설정과 무관하게 비교할 수 있게 UTC 로 둔다.
    """
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def write_atomic(path: Path, text: str) -> None:
    """읽는 쪽이 반쯤 쓰인 파일을 보지 않게 쓴다.

    같은 디렉터리의 임시 파일에 쓴 뒤 ``os.replace`` 로 바꾼다. 권한은
    ``0600`` 이다. 상태 파일이 세션 비밀번호를 담는다.

    Args:
        path: 쓸 파일.
        text: 내용.
    """
    fd, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_request(directory: Path) -> Request | None:
    """요청 파일을 읽는다.

    Returns:
        요청. 파일이 없으면 ``None``.

    Raises:
        ProtocolError: 계약과 다른 내용일 때.
    """
    try:
        text = (directory / REQUEST_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return Request.from_json(text)


def read_status(directory: Path) -> Status:
    """상태 파일을 읽는다.

    Returns:
        상태. 파일이 없으면 ``IDLE``.

    Raises:
        ProtocolError: 계약과 다른 내용일 때.
    """
    try:
        text = (directory / STATUS_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return IDLE
    return Status.from_json(text)


def write_request(directory: Path, request: Request) -> None:
    """요청 파일을 쓴다. 디렉터리가 없으면 만든다."""
    directory.mkdir(parents=True, exist_ok=True)
    write_atomic(directory / REQUEST_FILE, request.to_json())


def write_status(directory: Path, status: Status) -> None:
    """상태 파일을 쓴다. 디렉터리가 없으면 만든다."""
    directory.mkdir(parents=True, exist_ok=True)
    write_atomic(directory / STATUS_FILE, status.to_json())


def _load_object(text: str) -> dict[str, object]:
    """JSON 객체를 읽는다."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProtocolError(f"JSON 이 아닙니다: {error}") from error
    if not isinstance(data, dict):
        raise ProtocolError("JSON 객체가 아닙니다")
    return data


def _required_str(data: dict[str, object], key: str) -> str:
    """비어 있지 않은 문자열 필드를 꺼낸다."""
    value = data.get(key)
    if isinstance(value, str) and value:
        return value
    raise ProtocolError(f"{key} 가 없거나 문자열이 아닙니다")


def _optional_str(data: dict[str, object], key: str) -> str | None:
    """없어도 되는 문자열 필드를 꺼낸다."""
    value = data.get(key)
    if value is None or isinstance(value, str):
        return value
    raise ProtocolError(f"{key} 는 문자열이어야 합니다")
