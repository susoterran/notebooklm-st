"""진행 콜백을 화면 진행 상자에 연결한다."""

import contextlib
from collections.abc import Callable, Iterator

import streamlit as st


@contextlib.contextmanager
def progress_status(label: str) -> Iterator[Callable[[str], None]]:
    """진행 상자를 열고 문구 갱신 콜백을 넘긴다.

    ``services`` 계층은 Streamlit 을 모른 채 이 콜백만 부른다.
    파이프라인이 스크립트와 같은 스레드에서 돌기 때문에 콜백 안에서
    화면을 갱신해도 그대로 전달된다.

    Args:
        label: 상자에 처음 표시할 문구.

    Yields:
        진행 문구를 받는 콜백.
    """
    with st.status(label, expanded=True) as status:

        def report(message: str) -> None:
            """진행 문구를 갱신하고 로그 줄을 남긴다."""
            status.update(label=message)
            st.write(message)

        yield report
        status.update(label="완료", state="complete")
