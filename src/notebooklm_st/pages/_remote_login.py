"""인증 페이지의 원격 구글 로그인 영역.

홈서버의 사이드카(login-browser)가 띄운 크로미움 화면을 iframe 으로
보여 준다. 사람은 앱 화면 안에서 구글 로그인을 하고, CLI 가 결과를
앱의 프로필에 직접 저장한다. 사이드카와는 공유 볼륨의 파일로만
이야기한다(``core.login_protocol``).

설계: docs/superpowers/specs/2026-09-26-remote-login-design.md §7
"""

import datetime as dt
import pathlib
import time

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import login_protocol
from notebooklm_st.services import auth, login_session

_START_KEY = "remote_login_start"
_CANCEL_KEY = "remote_login_cancel"
_WATCHING_KEY = "remote_login_watching"
"""이 탭이 결과를 기다리는 요청의 ``id``.

지켜보던 요청의 결과만 처리한다. 며칠 전의 ``succeeded`` 를 새 탭이
"인증되었습니다" 로 오해하지 않게 한다.
"""
_OUTCOME_KEY = "remote_login_outcome"

IFRAME_HEIGHT = 700

_RESULT_TEXT = {
    login_protocol.State.SUCCEEDED: "성공",
    login_protocol.State.FAILED: "실패",
    login_protocol.State.TIMEOUT: "시간 초과",
    login_protocol.State.CANCELLED: "취소됨",
}


def render(gate: auth.AuthGate) -> None:
    """원격 로그인 영역을 그린다. 설정이 없으면 아무것도 그리지 않는다.

    사이드카를 기다리는 동안에만 1초마다 영역을 다시 그린다. 평소에는
    폴링하지 않는다.

    Args:
        gate: 로그인이 끝나면 다시 확인할 게이트.
    """
    base = login_session.viewer_url()
    directory = login_session.login_dir()
    if base is None or directory is None:
        return
    st.subheader("구글 로그인")
    polling = _waiting(directory)
    st.fragment(run_every=1 if polling else None)(_area)(gate, base, directory)


def _waiting(directory: pathlib.Path) -> bool:
    """사이드카의 응답을 기다리는 중인지."""
    if not login_session.sidecar_alive(directory, time.time()):
        return False
    status = login_session.read_status(directory)
    if status.state in login_protocol.ACTIVE_STATES:
        return True
    return _unaccepted(login_session.pending_request(directory), status)


def _unaccepted(
    request: login_protocol.Request | None, status: login_protocol.Status
) -> bool:
    """사이드카가 아직 받지 않은 시작 요청이 있는지.

    취소는 넣지 않는다. 사이드카는 세션이 없으면 취소를 무시하므로,
    넣으면 영원히 "준비 중" 으로 보인다.
    """
    return (
        request is not None
        and request.action is login_protocol.Action.START
        and request.id != status.request_id
    )


def _area(gate: auth.AuthGate, base: str, directory: pathlib.Path) -> None:
    """상태에 맞는 화면을 그린다. 기다리는 동안 1초마다 다시 돈다."""
    _show_outcome()
    if not login_session.sidecar_alive(directory, time.time()):
        st.warning(
            "로그인 브라우저가 꺼져 있습니다. 홈서버에서"
            " notebooklm-st-login-browser 컨테이너가 떠 있는지 확인하세요."
        )
        return
    status = login_session.read_status(directory)
    if status.state is login_protocol.State.RUNNING and status.password:
        _render_running(base, directory, status)
        return
    if status.state is login_protocol.State.STARTING or _unaccepted(
        login_session.pending_request(directory), status
    ):
        st.info("로그인 브라우저를 준비하는 중입니다.")
        return
    if _finish_watched(gate, status):
        # 배너와 페이지 상태 줄까지 새 판정으로 다시 그리고, 폴링을
        # 멈춘다.
        st.rerun(scope="app")
    _render_idle(directory, status)


def _render_running(
    base: str, directory: pathlib.Path, status: login_protocol.Status
) -> None:
    """떠 있는 세션의 화면을 iframe 으로 그린다."""
    if status.request_id is not None:
        st.session_state.setdefault(_WATCHING_KEY, status.request_id)
    # RUNNING 이면 비밀번호가 있다(호출 조건). mypy 좁히기용.
    link = login_session.viewer_link(base, status.password or "")
    remaining = login_session.remaining_seconds(status, dt.datetime.now(dt.UTC))
    if remaining is not None:
        st.caption(
            f"남은 시간 {remaining // 60}:{remaining % 60:02d}"
            " · 로그인을 마치면 이 창은 자동으로 닫힙니다."
        )
    st.iframe(link, height=IFRAME_HEIGHT)
    left, right = st.columns(2)
    left.link_button("새 탭에서 열기", link)
    if right.button("취소", key=_CANCEL_KEY):
        login_session.request_cancel(directory)
        st.rerun(scope="app")


def _render_idle(
    directory: pathlib.Path, status: login_protocol.Status
) -> None:
    """마지막 결과 한 줄과 시작 버튼을 그린다."""
    if status.state in _RESULT_TEXT:
        line = f"마지막 로그인: {_RESULT_TEXT[status.state]}"
        if status.detail:
            line += f" — {status.detail}"
        st.caption(line)
    busy = login_session.busy(
        session.get_registry(), session.get_digest_registry()
    )
    if busy:
        st.caption(
            "진행 중인 질의·정리본이 끝난 뒤 로그인하세요. 실행 중인"
            " 작업이 옛 자격증명을 되써 새 로그인을 덮을 수 있습니다."
        )
    if st.button("구글 로그인 시작", key=_START_KEY, disabled=busy):
        st.session_state[_WATCHING_KEY] = login_session.request_start(directory)
        st.rerun(scope="app")


def _finish_watched(gate: auth.AuthGate, status: login_protocol.Status) -> bool:
    """이 탭이 지켜보던 요청이 끝났으면 결과를 처리한다.

    Returns:
        처리했으면 ``True``. 호출자가 앱 전체를 다시 그린다.
    """
    if status.state not in _RESULT_TEXT:
        # 아직 결과가 아니다(running 인데 비밀번호가 없는 순간 등).
        return False
    watching = st.session_state.get(_WATCHING_KEY)
    if watching is None or status.request_id != watching:
        return False
    del st.session_state[_WATCHING_KEY]
    if status.state is login_protocol.State.SUCCEEDED:
        if gate.recheck():
            outcome = ("success", "인증되었습니다.")
        else:
            outcome = (
                "error",
                "로그인은 끝났지만 인증이 살아나지 않았습니다."
                " 다시 시작하세요.",
            )
    else:
        reason = _RESULT_TEXT.get(status.state, str(status.state))
        if status.detail:
            reason += f" — {status.detail}"
        outcome = ("error", f"로그인하지 못했습니다: {reason}")
    st.session_state[_OUTCOME_KEY] = outcome
    return True


def _show_outcome() -> None:
    """직전에 처리한 결과를 한 번 보여 준다."""
    outcome = st.session_state.pop(_OUTCOME_KEY, None)
    if outcome is None:
        return
    level, text = outcome
    if level == "success":
        st.success(text)
    else:
        st.error(text)
