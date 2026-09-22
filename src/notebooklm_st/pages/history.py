"""실행 이력 화면."""

import sqlite3
from collections.abc import Sequence

import streamlit as st

from notebooklm_st import session
from notebooklm_st.components import answer_view
from notebooklm_st.core import answer_text, markdown_export, models
from notebooklm_st.services import outline, run_history

_SELECTED_KEY = "history_selected"

# 목록은 한 줄로 읽혀야 값을 한다. 질문 관리 화면과 같은 상한을
# 쓴다.
_TITLE_MAX_CHARS = 60

# 위젯 키가 아니라 우리가 소유한 세션 키다. 위젯이 만들어진 뒤 그
# 위젯의 키를 건드리면 Streamlit 이 예외를 던지므로, 삭제 후 상태를
# 되돌리려면 우리 것이어야 한다.
_DELETE_ARMED_KEY = "history_delete_armed"


def render() -> None:
    """최근 실행을 고르고 그 답변들을 보여 준다.

    인용 포함 체크박스를 끄면 ``answer_text.for_display`` 가 만든
    사본을 그린다.
    삭제는 실수로 한 번에 지워지지 않도록 확인 버튼을 한 번 더
    거치는 2단계로 되어 있다(``_render_delete`` 참고).
    """
    st.title("이력")
    connection = session.get_connection()
    runs = run_history.list_runs(connection)
    if not runs:
        st.info("아직 저장된 실행이 없습니다.")
        return

    selected = st.selectbox(
        "실행 선택",
        options=runs,
        format_func=_format_run,
        key=_SELECTED_KEY,
    )
    if selected is None:
        return
    st.caption(selected.url)
    _render_delete(connection, selected)
    if selected.exported_at is not None:
        _render_saved(selected)
        return
    title = st.text_input(
        "문서 제목",
        value=selected.title or selected.video_id,
        key=f"history_title_{selected.id}",
        help="Outline 문서의 제목이 됩니다.",
    )
    included = st.checkbox(
        "인용 포함",
        value=True,
        key=f"history_include_{selected.id}",
        help="끄면 인용 번호와 인용 본문, 맨 아래 후속 제안을 뺀 채로"
        " 올립니다. 화면도 같은 상태로 보입니다.",
    )
    items = run_history.load_run_items(connection, selected.id)
    if not included:
        items = [answer_text.for_display(item) for item in items]
    metadata = run_history.load_metadata(connection, selected.id)
    _render_export(connection, selected, title, items, metadata)
    answer_view.render_items(items)


def _format_run(run: models.RunSummary) -> str:
    """실행 하나를 목록에 보여 줄 한 줄로 만든다.

    제목을 앞에 둔다. 목록에서 고르는 사람이 먼저 알고 싶은 것은
    시각이 아니라 어떤 영상이었는지다. 목록은 최신순으로 고정되어
    있으므로 시각은 뒤에 있어도 읽는 데 지장이 없다.

    저장된 실행은 위키에 붙은 이름으로 찾게 된다. 그래서 영상 제목이
    아니라 문서 제목을 쓴다.
    """
    if run.exported_at is not None:
        label = _shorten(run.outline_title or run.video_id)
        return f"{label} · {run.created_at} · 문서"
    label = _shorten(run.title) if run.title else run.video_id
    return f"{label} · {run.created_at} · 미저장 · 답변 {run.answer_count}건"


def _shorten(title: str) -> str:
    """목록 한 줄에 들어가도록 제목을 자른다.

    자르기는 라벨을 만드는 이 자리에서만 한다. 저장된 제목은 그대로
    둔다.
    """
    if len(title) <= _TITLE_MAX_CHARS:
        return title
    return f"{title[: _TITLE_MAX_CHARS - 1]}…"


def _render_delete(
    connection: sqlite3.Connection, selected: models.RunSummary
) -> None:
    """접은 영역 안에 2단계 삭제를 그린다.

    첫 누름은 지우려는 실행 ID 를 세션에 적어 둘 뿐이다. 다시 그려진
    화면에서 확인을 눌러야 실제로 지운다. 선택한 실행이 바뀌면 적어
    둔 ID 와 어긋나므로 확인이 저절로 풀린다.
    """
    with st.expander("이 이력 삭제"):
        if st.session_state.get(_DELETE_ARMED_KEY) != selected.id:
            if st.button("삭제 준비", key="history_delete"):
                st.session_state[_DELETE_ARMED_KEY] = selected.id
                st.rerun()
            return
        if selected.exported_at is not None:
            st.warning("로컬 링크만 지웁니다. Outline 문서는 그대로 남습니다.")
        else:
            st.warning("딸린 답변도 함께 사라집니다. 되돌릴 수 없습니다.")
        left, right = st.columns(2)
        if left.button("정말 삭제", key="history_delete_confirm"):
            _delete(connection, selected.id)
        if right.button("취소", key="history_delete_cancel"):
            _disarm()
            st.rerun()


def _render_saved(selected: models.RunSummary) -> None:
    """저장된 실행을 문서명과 링크로 그린다.

    본문은 로컬에 없다. 수정·삭제·검색은 Outline 이 맡는다.
    """
    st.success(f"Outline 에 저장됨 · {selected.exported_at}")
    st.markdown(f"**{selected.outline_title}**")
    if selected.outline_url:
        st.link_button(
            "Outline 에서 열기",
            selected.outline_url,
            key=f"history_open_{selected.id}",
        )


def _render_export(
    connection: sqlite3.Connection,
    selected: models.RunSummary,
    title: str,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> None:
    """저장 버튼을 그린다. 설정이 없으면 안내로 대신한다.

    이력 열람 자체는 막지 않는다. Outline 을 아직 붙이지 않았어도
    지난 실행을 읽는 데에는 아무 문제가 없다.
    """
    config = outline.config_from_env()
    if config is None:
        st.info(
            "Outline 연결이 설정되지 않았습니다."
            f" {outline.URL_ENV_VAR}·{outline.TOKEN_ENV_VAR}"
            f"·{outline.COLLECTION_ENV_VAR} 를 설정하세요."
        )
        return
    if st.button(
        "Outline 에 저장",
        key=f"history_export_{selected.id}",
        disabled=not title.strip(),
        help="지금 보이는 그대로 올립니다. 올린 뒤에는 로컬에 링크만 남습니다.",
    ):
        _export(connection, config, selected, title.strip(), items, metadata)


def _export(
    connection: sqlite3.Connection,
    config: outline.OutlineConfig,
    selected: models.RunSummary,
    title: str,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> None:
    """문서를 만들고 링크를 기록한다.

    실패하면 로컬을 손대지 않는다. 원인을 고친 뒤 같은 버튼을 다시
    누르면 된다.
    """
    with st.spinner("Outline 에 저장 중"):
        try:
            document = outline.create_document(
                config,
                title,
                markdown_export.to_markdown(selected, items, title, metadata),
            )
        except outline.OutlineError as error:
            st.error(str(error))
            return
        try:
            run_history.mark_exported(
                connection,
                selected.id,
                document_id=document.id,
                document_title=document.title,
                document_url=document.url,
            )
        except Exception as error:
            # 화면 경계의 최후 방어선이다: mark_exported 가 무엇을
            # 던지든(잠긴 DB 등) 문서는 이미 Outline 에 만들어져
            # 있으므로 구체적 예외로 좁히지 않고 넓게 잡는다.
            # 되돌리지 않는다. 방금 만든 문서를 지우려면 그 삭제도
            # 실패할 수 있어 틈이 한 겹 더 생길 뿐이다. 사실대로
            # 보여 주고 사람이 링크를 들고 판단하게 한다.
            st.error(
                f"문서는 만들어졌습니다: {document.url} —"
                " 로컬 기록에 실패했습니다"
                f"({type(error).__name__})."
                " 다시 저장하면 문서가 둘이 됩니다."
            )
            return
    st.rerun()


def _delete(connection: sqlite3.Connection, run_id: int) -> None:
    """실행을 지우고 확인 상태를 풀고 화면을 다시 그린다.

    선택 위젯의 키는 건드리지 않는다. 고른 항목이 목록에서 사라져도
    Streamlit 은 예외 없이 남은 첫 항목으로 되돌린다.
    """
    run_history.delete_run(connection, run_id)
    _disarm()
    st.rerun()


def _disarm() -> None:
    """적어 둔 삭제 대상을 지운다."""
    st.session_state.pop(_DELETE_ARMED_KEY, None)
