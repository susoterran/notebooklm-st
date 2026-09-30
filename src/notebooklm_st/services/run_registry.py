"""앱 전체가 공유하는 실행 레지스트리."""

from notebooklm_st.services import run_store


class RunRegistry(run_store.RunStore):
    """실행 보관소에 대기열 규칙과 다른 화면이 보는 판정을 더한다.

    핸들을 넣고 읽고 고치는 일은 ``run_store.RunStore`` 가 한다. 규칙과
    판정은 보관소와 같은 락 안에서 핸들을 본다.
    """

    def cancel(self, run_id: str) -> bool:
        """대기 중인 실행을 목록에서 지운다.

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
            return True

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
