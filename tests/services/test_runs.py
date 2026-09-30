"""실행 값 객체 테스트."""

from notebooklm_st.services import runs


def test_finished_names_done_and_failed() -> None:
    """끝난 상태는 done 과 failed 둘이다."""
    assert frozenset({"done", "failed"}) == runs.FINISHED
