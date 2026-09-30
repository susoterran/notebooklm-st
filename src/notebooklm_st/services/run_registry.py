"""앱 전체가 공유하는 실행 레지스트리."""

from notebooklm_st.services import run_store, runs


class RunRegistry(run_store.RunStore):
    """실행 보관소에 대기열 규칙과 다른 화면이 보는 판정을 더한다.

    핸들을 넣고 읽고 고치는 일은 ``run_store.RunStore`` 가 한다. 규칙과
    판정은 보관소와 같은 락 안에서 핸들을 본다.

    대기열을 도는 워커는 하나뿐이다. 워커 자리를 잡고 비우는 판정이
    모두 이 락 안에서 일어나므로, 워커가 끝나는 순간과 새 항목이
    들어오는 순간이 겹쳐도 워커가 둘이 되거나 하나도 없게 되지 않는다.
    """

    def __init__(self) -> None:
        """빈 레지스트리를 만든다. 워커 자리는 비었고 멈추지 않았다."""
        super().__init__()
        self._worker_active = False
        self._paused_reason: str | None = None

    def acquire_worker(self) -> bool:
        """워커를 새로 띄워야 하면 워커 자리를 잡는다.

        Returns:
            자리가 비었고, 멈추지 않았고, 대기 항목이 있으면 자리를 잡고
            참. 호출자는 참일 때만 워커를 띄운다.
        """
        with self._lock:
            return self._take_worker_slot()

    def claim_next(self) -> runs.RunHandle | None:
        """가장 먼저 넣은 대기 항목을 진행 중으로 바꿔 돌려준다.

        워커 자리를 쥔 워커만 부른다. 돌려줄 것이 없으면 같은 락 안에서
        자리를 비운다. 그래서 ``None`` 을 받은 뒤에 들어온 항목은 반드시
        새 워커를 띄운다.

        Returns:
            진행 중으로 바꾼 핸들의 복사본. 대기 항목이 없거나 대기열이
            멈췄으면 ``None``.
        """
        with self._lock:
            handle = self._first_queued()
            if handle is None or self._paused_reason is not None:
                self._worker_active = False
                return None
            return self._start(handle)

    def release_worker(self) -> None:
        """워커 자리를 비운다. 워커가 예외로 끝날 때만 쓴다."""
        with self._lock:
            self._worker_active = False

    def pause(self, reason: str) -> None:
        """대기열을 멈춘다. 남은 대기 항목이 없으면 멈추지 않는다.

        멈춤이 홀로 남으면 원인을 푼 뒤 새로 넣은 항목이 이유 없이
        서 있게 된다.

        Args:
            reason: 멈춘 이유. 실행 현황이 그대로 보여 준다.
        """
        with self._lock:
            if self._first_queued() is not None:
                self._paused_reason = reason

    def resume(self) -> bool:
        """멈춤을 풀고, 워커를 새로 띄워야 하면 워커 자리를 잡는다.

        Returns:
            ``acquire_worker`` 와 같은 판정. 참이면 호출자가 워커를
            띄운다.
        """
        with self._lock:
            self._paused_reason = None
            return self._take_worker_slot()

    def paused_reason(self) -> str | None:
        """대기열이 멈춘 이유. 멈추지 않았으면 ``None``."""
        with self._lock:
            return self._paused_reason

    def cancel(self, run_id: str) -> bool:
        """대기 중인 실행을 목록에서 지운다.

        마지막 대기 항목을 지우면 멈춤도 푼다. 멈춤은 대기 항목이 남아
        있는 동안만 산다.

        Args:
            run_id: 지울 실행 ID.

        Returns:
            지웠으면 참. 이미 시작했거나 끝났거나 없는 ID 면 거짓이다.
        """
        with self._lock:
            handle = self._handles.get(run_id)
            if handle is None or handle.status != "queued":
                return False
            del self._handles[run_id]
            if self._first_queued() is None:
                self._paused_reason = None
            return True

    def active_count(self) -> int:
        """곧 NotebookLM 을 쓸 실행 수를 센다.

        멈춘 대기열의 항목은 재개하기 전까지 돌지 않으므로 세지 않는다.
        다른 화면의 가드가 이 수를 본다.

        Returns:
            running 수에, 멈추지 않았으면 queued 수를 더한 값.
        """
        with self._lock:
            paused = self._paused_reason is not None
            counted = frozenset({"running"}) if paused else runs.PENDING
            return sum(
                1
                for handle in self._handles.values()
                if handle.status in counted
            )

    def is_pending(self, video_id: str) -> bool:
        """그 영상이 대기 중이거나 진행 중인지 알려준다.

        Args:
            video_id: 확인할 영상 ID.

        Returns:
            queued 또는 running 인 실행이 있으면 참.
        """
        with self._lock:
            return any(
                handle.video_id == video_id and handle.status in runs.PENDING
                for handle in self._handles.values()
            )

    def _take_worker_slot(self) -> bool:
        """워커 자리를 잡아야 하면 잡는다. 락을 쥔 채로 부른다."""
        if self._worker_active or self._paused_reason is not None:
            return False
        if self._first_queued() is None:
            return False
        self._worker_active = True
        return True
