"""이력 화면의 "Outline 과 동기화" 영역.

``pages/history.py`` 가 이 모듈을 부른다. 네비게이션에 직접 등록되지
않으므로 이름 앞에 밑줄을 둔다.

확인 → 미리보기 → 적용의 2단계다. 계획은 우리가 소유한 세션 키에
두고, 적용·취소 뒤 지운다. Outline 은 사람이 확인을 눌렀을 때만
읽는다 — Outline 이 죽어도 이력 화면은 뜬다.
"""

import sqlite3

import streamlit as st

from notebooklm_st.core import labels, models
from notebooklm_st.services import history_sync, outline, run_history_sync

_PLAN_KEY = "history_sync_plan"
_RESULT_KEY = "history_sync_result"


def render(connection: sqlite3.Connection) -> None:
    """동기화 영역을 그린다.

    Args:
        connection: 열린 커넥션.
    """
    result = st.session_state.pop(_RESULT_KEY, None)
    if result is not None:
        st.success(result)
    with st.expander("Outline 과 동기화"):
        st.caption(
            "Outline 컬렉션의 문서 목록과 저장된 이력을 맞춥니다."
            " Outline 에 없는 이력은 지우고, 이력에 없는 문서는 새로"
            " 만듭니다."
        )
        config = outline.config_from_env()
        if config is None:
            st.info(
                "Outline 연결이 설정되지 않았습니다."
                f" {outline.URL_ENV_VAR}·{outline.TOKEN_ENV_VAR}"
                f"·{outline.COLLECTION_ENV_VAR} 를 설정하세요."
            )
            return
        if st.button("확인", key="history_sync_check"):
            _check(connection, config)
        sync_plan = st.session_state.get(_PLAN_KEY)
        if sync_plan is not None:
            _render_plan(connection, sync_plan)


def _check(
    connection: sqlite3.Connection, config: outline.OutlineConfig
) -> None:
    """목록을 읽어 계획을 세우고 세션에 담는다.

    실패하면 문구만 내고 계획은 남기지 않는다. 지난 계획이 남아 있으면
    실패한 뒤에도 적용 버튼이 보이게 되므로 함께 지운다. 목록은 여러
    페이지를 이어 부를 수 있어 읽는 동안 스피너를 띄운다.
    """
    try:
        with st.spinner("Outline 문서 목록을 읽는 중"):
            documents = outline.list_documents(config)
    except outline.OutlineError as error:
        st.session_state.pop(_PLAN_KEY, None)
        st.error(str(error))
        return
    exported = run_history_sync.list_exported(connection)
    st.session_state[_PLAN_KEY] = history_sync.plan(exported, documents)


def _render_plan(
    connection: sqlite3.Connection, sync_plan: models.SyncPlan
) -> None:
    """미리보기와 적용·취소 버튼을 그린다.

    expander 는 중첩할 수 없으므로 세 목록은 마크다운으로 그린다.
    """
    st.markdown(
        f"지울 이력 {len(sync_plan.deletes)}건"
        f" · 만들 문서 {len(sync_plan.creates)}건"
        f" · 건너뛴 문서 {len(sync_plan.skips)}건"
    )
    if sync_plan.deletes:
        st.markdown(
            "**지울 이력**\n"
            + "\n".join(
                f"- {labels.shorten(run.outline_title or run.video_id)}"
                f" · {run.created_at}"
                for run in sync_plan.deletes
            )
        )
    if sync_plan.creates:
        st.markdown(
            "**만들 문서**\n"
            + "\n".join(
                f"- {labels.shorten(create.document.title)}"
                f" · {create.document.created_at} · {create.url}"
                for create in sync_plan.creates
            )
        )
    if sync_plan.skips:
        st.markdown(
            "**건너뛴 문서**\n"
            + "\n".join(
                f"- {labels.shorten(skip.document.title)} · {skip.reason}"
                for skip in sync_plan.skips
            )
        )
    if sync_plan.is_empty:
        st.info(f"이미 맞습니다. 건너뛴 문서 {len(sync_plan.skips)}건.")
        return
    left, right = st.columns(2)
    if left.button("적용", key="history_sync_apply"):
        _apply(connection, sync_plan)
    if right.button("취소", key="history_sync_cancel"):
        st.session_state.pop(_PLAN_KEY, None)
        st.rerun()


def _apply(connection: sqlite3.Connection, sync_plan: models.SyncPlan) -> None:
    """계획을 적용하고 결과 문구를 남긴 뒤 다시 그린다.

    실패하면 계획을 남긴다. 원인을 고친 뒤 같은 버튼을 다시 누르면
    된다.
    """
    try:
        result = history_sync.apply(connection, sync_plan)
    except sqlite3.Error as error:
        st.error(
            f"적용에 실패했습니다({type(error).__name__})."
            " 다시 적용할 수 있습니다."
        )
        return
    st.session_state.pop(_PLAN_KEY, None)
    st.session_state[_RESULT_KEY] = (
        f"동기화 완료 · 지움 {result.deleted}건 · 만듦 {result.created}건"
    )
    st.rerun()
