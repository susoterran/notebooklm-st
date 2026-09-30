"""실행 핸들을 세션 간에 공유하는 보관소.

화면과 백그라운드 스레드가 같은 핸들을 읽고 고친다. 다른 화면이 보는
판정은 이 보관소를 물려받는 ``run_registry.RunRegistry`` 가 더한다.
"""

import dataclasses
import datetime
import threading
import uuid

from notebooklm_st.core import models
from notebooklm_st.services import runs


class RunStore:
    """실행 핸들을 세션 간에 공유하는 보관소.

    모든 공개 메서드가 락 안에서 동작한다. 화면과 스레드가 동시에
    접근하므로 밖에서 락을 잡을 필요가 없다.
    """

    def __init__(self) -> None:
        """빈 보관소를 만든다."""
        self._lock = threading.Lock()
        self._handles: dict[str, runs.RunHandle] = {}

    def enqueue(
        self,
        url: str,
        video_id: str,
        questions: tuple[models.Question, ...],
        auto_save: bool = False,
    ) -> runs.RunHandle:
        """새 실행을 대기열 끝에 넣는다.

        Args:
            url: 질의할 영상 URL.
            video_id: URL 에서 뽑은 영상 ID.
            questions: 물어볼 질문들.
            auto_save: 답변을 받자마자 Outline 에 올릴지. 사람이
                저장하는 입구(채널 화면)는 기본값을 쓴다.

        Returns:
            넣은 핸들. 보관소가 쥔 것과 같은 객체가 아니라 호출자가
            ``run_id`` 를 얻는 용도다.
        """
        handle = runs.RunHandle(
            run_id=uuid.uuid4().hex[:8],
            url=url,
            video_id=video_id,
            questions=questions,
            auto_save=auto_save,
            queued_at=_now(),
            started_at=None,
            status="queued",
            progress=[],
            result=None,
            save=None,
            error_message=None,
            error_level=None,
            finished_at=None,
        )
        with self._lock:
            self._handles[handle.run_id] = handle
            return _copy(handle)

    def get(self, run_id: str) -> runs.RunHandle | None:
        """실행 하나를 조회한다.

        Args:
            run_id: 조회할 실행 ID.

        Returns:
            복사본. 그런 실행이 없으면 ``None``.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            return _copy(handle) if handle is not None else None

    def list_all(self) -> list[runs.RunHandle]:
        """실행 표에 그릴 순서로 모든 실행을 돌려준다.

        진행 중인 실행, 대기 중인 실행을 넣은 순서대로 먼저 두고, 끝난
        실행을 그 뒤에 최근에 끝난 것부터 둔다. 표를 위에서 아래로
        "지금, 다음, 지난 것" 으로 읽게 하려는 순서다. 대기 줄은 워커가
        가져갈 순서와 같다. 끝난 시각은 초 단위라 자주 겹치며, 겹치면
        나중에 넣은 실행이 앞에 온다.

        Returns:
            복사본 목록. 화면이 순회하는 동안 스레드가 바꿔도 안전하다.
        """
        with self._lock:
            handles = list(self._handles.values())
            running = [
                handle for handle in handles if handle.status == "running"
            ]
            queued = [handle for handle in handles if handle.status == "queued"]
            # 넣은 순서의 역순으로 모은 뒤 안정 정렬한다. 끝난 시각이
            # 같은 실행끼리는 나중에 넣은 것이 앞에 남는다.
            finished = [
                handle
                for handle in reversed(handles)
                if handle.status in runs.FINISHED
            ]
            finished.sort(
                key=lambda handle: handle.finished_at or "", reverse=True
            )
            ordered = running + queued + finished
            return [_copy(handle) for handle in ordered]

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

    def finish(
        self,
        run_id: str,
        result: models.RunResult,
        save: runs.SaveOutcome | None = None,
    ) -> None:
        """실행을 완료로 표시한다. 없는 ID 면 조용히 넘어간다.

        Args:
            run_id: 대상 실행 ID.
            result: 파이프라인이 돌려준 결과.
            save: 자동 저장 결과. 자동 저장을 하지 않았으면 ``None``.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is not None:
                handle.status = "done"
                handle.result = result
                handle.save = save
                handle.finished_at = _now()

    def fail(self, run_id: str, message: str, level: runs.MessageLevel) -> None:
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

    def discard_finished(self) -> int:
        """끝난 실행을 모두 목록에서 지운다.

        진행 중인 실행은 남긴다. 이력은 DB 에 남으므로 기록이 사라지지
        않는다.

        Returns:
            지운 실행 수.
        """
        with self._lock:
            finished = [
                run_id
                for run_id, handle in self._handles.items()
                if handle.status in runs.FINISHED
            ]
            for run_id in finished:
                del self._handles[run_id]
            return len(finished)

    def _first_queued(self) -> runs.RunHandle | None:
        """가장 먼저 넣은 대기 항목. 락을 쥔 채로 부른다."""
        return next(
            (
                handle
                for handle in self._handles.values()
                if handle.status == "queued"
            ),
            None,
        )

    def _start(self, handle: runs.RunHandle) -> runs.RunHandle:
        """대기 항목을 진행 중으로 바꾼다. 락을 쥔 채로 부른다.

        Args:
            handle: 보관소가 쥔 대기 항목.

        Returns:
            바꾼 핸들의 복사본.
        """
        handle.status = "running"
        handle.started_at = _now()
        return _copy(handle)


def _copy(handle: runs.RunHandle) -> runs.RunHandle:
    """진행 목록까지 새로 만든 복사본을 돌려준다."""
    return dataclasses.replace(handle, progress=list(handle.progress))


def _now() -> str:
    """현재 로컬 시각을 초 단위 ISO 문자열로 돌려준다."""
    return datetime.datetime.now().isoformat(timespec="seconds")
