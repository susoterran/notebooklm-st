"""질의 실행을 백그라운드로 돌리고 그 상태를 보관한다."""

import dataclasses
import datetime
import threading
import uuid
from typing import Literal

from notebooklm_st.core import models

RunStatus = Literal["running", "done", "failed"]
MessageLevel = Literal["info", "error"]


@dataclasses.dataclass(slots=True)
class RunHandle:
    """진행 중이거나 끝난 실행 하나.

    다른 값 객체와 달리 frozen 이 아니다. 백그라운드 스레드가 상태를
    갱신하며, 동시 접근은 ``RunRegistry`` 의 락이 막는다.
    """

    run_id: str
    url: str
    video_id: str
    question_texts: tuple[str, ...]
    started_at: str
    status: RunStatus
    progress: list[str]
    result: models.RunResult | None
    error_message: str | None
    error_level: MessageLevel | None
    finished_at: str | None


class RunRegistry:
    """실행 핸들을 세션 간에 공유하는 보관소.

    모든 공개 메서드가 락 안에서 동작한다. 화면과 스레드가 동시에
    접근하므로 밖에서 락을 잡을 필요가 없다.
    """

    def __init__(self) -> None:
        """빈 보관소를 만든다."""
        self._lock = threading.Lock()
        self._handles: dict[str, RunHandle] = {}

    def create(
        self,
        url: str,
        video_id: str,
        question_texts: tuple[str, ...],
    ) -> RunHandle:
        """새 실행을 running 상태로 등록한다.

        Args:
            url: 질의할 영상 URL.
            video_id: URL 에서 뽑은 영상 ID.
            question_texts: 물어볼 질문 본문들.

        Returns:
            등록된 핸들. 레지스트리가 보관하는 것과 같은 객체가 아니라
            호출자가 ``run_id`` 를 얻는 용도다.
        """
        handle = RunHandle(
            run_id=uuid.uuid4().hex[:8],
            url=url,
            video_id=video_id,
            question_texts=question_texts,
            started_at=_now(),
            status="running",
            progress=[],
            result=None,
            error_message=None,
            error_level=None,
            finished_at=None,
        )
        with self._lock:
            self._handles[handle.run_id] = handle
            return _copy(handle)

    def get(self, run_id: str) -> RunHandle | None:
        """실행 하나를 조회한다.

        Args:
            run_id: 조회할 실행 ID.

        Returns:
            복사본. 그런 실행이 없으면 ``None``.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            return _copy(handle) if handle is not None else None

    def list_all(self) -> list[RunHandle]:
        """모든 실행을 최근 것부터 돌려준다.

        Returns:
            복사본 목록. 화면이 순회하는 동안 스레드가 바꿔도 안전하다.
        """
        with self._lock:
            return [
                _copy(handle) for handle in reversed(self._handles.values())
            ]

    def running_count(self) -> int:
        """진행 중인 실행 개수를 센다.

        Returns:
            ``status`` 가 running 인 실행 수.
        """
        with self._lock:
            return sum(
                1
                for handle in self._handles.values()
                if handle.status == "running"
            )

    def append_progress(self, run_id: str, message: str) -> None:
        """진행 문구를 덧붙인다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            message: 기록할 진행 문구.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.progress.append(message)

    def finish(self, run_id: str, result: models.RunResult) -> None:
        """실행을 완료로 표시한다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            result: 파이프라인이 돌려준 결과.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.status = "done"
                handle.result = result
                handle.finished_at = _now()

    def fail(self, run_id: str, message: str, level: MessageLevel) -> None:
        """실행을 실패로 표시한다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            message: 화면에 보여 줄 사용자 문구.
            level: 표시 수준. 자막 없는 영상 같은 정상 결과는 info 다.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.status = "failed"
                handle.error_message = message
                handle.error_level = level
                handle.finished_at = _now()

    def discard(self, run_id: str) -> None:
        """실행을 목록에서 지운다. 없는 ID 면 조용히 넘어간다.

        이력은 DB 에 남으므로 여기서 지워도 기록이 사라지지 않는다.

        Args:
            run_id: 지울 실행 ID.
        """
        with self._lock:
            self._handles.pop(run_id, None)


def _copy(handle: RunHandle) -> RunHandle:
    """진행 목록까지 새로 만든 복사본을 돌려준다."""
    return dataclasses.replace(handle, progress=list(handle.progress))


def _now() -> str:
    """현재 로컬 시각을 초 단위 ISO 문자열로 돌려준다."""
    return datetime.datetime.now().isoformat(timespec="seconds")
