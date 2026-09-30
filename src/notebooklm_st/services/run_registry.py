"""앱 전체가 공유하는 실행 레지스트리."""

from notebooklm_st.services import run_store


class RunRegistry(run_store.RunStore):
    """실행 보관소에 다른 화면이 보는 판정을 더한 레지스트리.

    핸들을 넣고 읽고 고치는 일은 ``run_store.RunStore`` 가 한다. 판정은
    보관소와 같은 락 안에서 핸들을 본다.
    """

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
