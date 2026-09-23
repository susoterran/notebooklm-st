"""정리본 화면 — 저장된 요약본 여럿을 문서 하나로."""

import sqlite3

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import digest_markdown, digest_title, labels, models
from notebooklm_st.services import (
    digest_runner,
    nlm,
    outline,
    questions,
    run_history,
)

_SELECTED_KEY = "digest_selected"
_INSTRUCTION_KEY = "digest_instruction"
_TITLE_KEY = "digest_title"
_SAVED_KEY = "digest_saved"

_POLL_INTERVAL = "1s"


def render() -> None:
    """정리본 화면을 상태에 맞게 그린다.

    상태는 넷이다 — 방금 저장함 · 진행 중 · 끝남(초안 또는 실패) ·
    아무것도 없음(재료 선택).
    """
    st.title("정리본")
    registry = session.get_digest_registry()
    if _SAVED_KEY in st.session_state:
        _render_saved()
        return
    if registry.is_running():
        _render_running()
        return
    handle = registry.get()
    if handle is not None:
        _render_finished(registry, handle)
        return
    _render_form(registry)


@st.fragment(run_every=_POLL_INTERVAL)
def _render_running() -> None:
    """진행 문구를 1초마다 갱신한다.

    **레지스트리를 읽기만 한다.** 안에서 상태를 바꾸면 그 변경이 다음
    재실행을 부르고 다시 상태를 바꿔 무한 루프가 된다(실행 현황 화면의
    같은 주석 참고).
    """
    handle = session.get_digest_registry().get()
    if handle is None:
        return
    if handle.status != "running":
        # 끝났다. 프래그먼트 밖을 다시 그려 결과 화면으로 넘어간다.
        st.rerun(scope="app")
        return
    latest = handle.progress[-1] if handle.progress else "시작하는 중"
    st.info(f"정리 중 — {latest}")
    st.caption("이 화면을 떠나도 작성은 계속됩니다.")


def _render_form(registry: digest_runner.DigestRegistry) -> None:
    """설정과 재료를 확인하고 시작 버튼을 그린다."""
    config = outline.config_from_env()
    if config is None:
        st.info(
            "Outline 연결이 설정되지 않았습니다."
            f" {outline.URL_ENV_VAR}·{outline.TOKEN_ENV_VAR}"
            f"·{outline.COLLECTION_ENV_VAR} 를 설정하세요."
        )
        return
    connection = session.get_connection()
    saved = [
        run
        for run in run_history.list_runs(connection)
        if run.exported_at is not None
    ]
    if not saved:
        st.info(
            "재료로 쓸 요약본이 없습니다."
            " 이력 화면에서 요약본을 Outline 에 먼저 저장하세요."
        )
        return

    by_id = {run.id: run for run in saved}
    selected_ids = st.multiselect(
        "재료 선택",
        options=list(by_id),
        format_func=lambda run_id: _format_run(by_id[run_id]),
        key=_SELECTED_KEY,
        help=f"최대 {nlm.DIGEST_SOURCE_LIMIT}건까지 고를 수 있습니다.",
    )
    # 다른 탭에서 그 사이 이력이 지워지면 선택값이 남은 채로 위젯이
    # 되살아나고, Streamlit 은 그 자리에 원본 라벨 문자열을 끼워
    # 넣는다. by_id 에 없는 값은 조용히 걸러 트레이스백을 막는다.
    selected = [by_id[key] for key in selected_ids if key in by_id]
    instruction = _render_instruction(connection)
    if instruction is None:
        return
    _render_start(registry, config, selected, instruction)


def _render_instruction(connection: sqlite3.Connection) -> str | None:
    """정리 지시를 질문 목록에서 고르게 한다.

    지시를 이 화면에서 따로 쓰지 않는다. 질문 관리가 이미 지시를
    등록·수정·삭제하는 자리이므로, 목록을 공유하면 같은 지시를 두 곳에
    두지 않아도 된다.

    Args:
        connection: 열린 커넥션.

    Returns:
        고른 질문의 본문. 등록된 질문이 없으면 ``None``.
    """
    question_list = questions.list_questions(connection)
    if not question_list:
        st.info(
            "정리 지시로 쓸 질문이 없습니다."
            " 질문 관리 화면에서 먼저 등록하세요."
        )
        return None
    chosen = st.selectbox(
        "정리 지시",
        options=question_list,
        format_func=lambda question: question.title,
        key=_INSTRUCTION_KEY,
        help="질문 관리 화면에 등록된 질문을 그대로 씁니다.",
    )
    if chosen is None:
        return None
    with st.expander("지시 내용"):
        st.markdown(chosen.text)
    return chosen.text


def _render_start(
    registry: digest_runner.DigestRegistry,
    config: outline.OutlineConfig,
    selected: list[models.RunSummary],
    instruction: str,
) -> None:
    """막을 이유를 먼저 보여 주고 시작 버튼을 그린다."""
    too_many = len(selected) > nlm.DIGEST_SOURCE_LIMIT
    if too_many:
        st.warning(
            f"재료는 최대 {nlm.DIGEST_SOURCE_LIMIT}건입니다."
            " 소스 하나마다 등록을 기다리므로 그 이상은 너무 오래"
            " 걸립니다."
        )
    busy = session.get_registry().running_count() > 0
    if busy:
        st.info(
            "질의가 실행 중입니다. 실행 현황에서 완료를 확인한 뒤"
            " 시작하세요 — 둘이 같은 자격증명으로 NotebookLM 을"
            " 동시에 쓰지 않게 막습니다."
        )
    if st.button(
        "정리 시작",
        key="digest_start",
        disabled=not selected or too_many or busy,
    ):
        digest_runner.start_digest(
            registry, config, selected, instruction.strip()
        )
        st.rerun()


def _format_run(run: models.RunSummary) -> str:
    """재료 하나를 목록에 보여 줄 한 줄로 만든다.

    위키에 붙은 문서 제목을 앞에 둔다. 고르는 사람이 찾는 이름이
    그것이다.
    """
    label = run.outline_title or run.title or run.video_id
    return f"{labels.shorten(label)} · {run.created_at}"


def _render_finished(
    registry: digest_runner.DigestRegistry,
    handle: digest_runner.DigestHandle,
) -> None:
    """끝난 정리를 초안 또는 실패로 그린다."""
    if handle.status == "failed":
        text = handle.error_message or "알 수 없는 오류로 실패했습니다."
        if handle.error_level == "info":
            st.info(text)
        else:
            st.error(text)
        _retry_button(registry)
        return
    if handle.draft is None:
        # mypy 는 ``draft: DigestDraft | None`` 만 보고 이 분기를 아직
        # 좁히지 못한다. 지금은 도달하지 않아도 타입 좁히기에 필요해
        # 남겨 둔다.
        st.warning("작성이 끝났지만 결과가 비어 있습니다.")
        _retry_button(registry)
        return
    _render_draft(registry, handle.draft)


def _retry_button(registry: digest_runner.DigestRegistry) -> None:
    """끝난 정리를 지우고 재료 선택으로 돌아가는 버튼을 그린다."""
    if st.button("재료 다시 고르기", key="digest_retry"):
        _reset(registry)
        st.rerun()


def _render_draft(
    registry: digest_runner.DigestRegistry, draft: models.DigestDraft
) -> None:
    """초안을 확인하고 저장하는 화면을 그린다."""
    config = outline.config_from_env()
    title = st.text_input(
        "문서 제목",
        value=digest_title.compose(draft.topic, draft.created_on),
        key=_TITLE_KEY,
        help="Outline 문서의 제목이 됩니다. 고쳐 쓸 수 있습니다.",
    )
    left, right = st.columns(2)
    save_clicked = left.button(
        "Outline 에 저장",
        key="digest_save",
        disabled=config is None or not title.strip(),
        help="지금 보이는 그대로 올립니다.",
    )
    if right.button("버리기", key="digest_discard"):
        _reset(registry)
        st.rerun()
    st.caption(
        f"재료 {len(draft.sources)}건 ·"
        " 저장하면 Outline 이 정본이 되고 이 정리본은 로컬에 남지"
        " 않습니다."
    )
    st.markdown(draft.body)
    if save_clicked and config is not None:
        _save(registry, config, draft, title.strip())


def _save(
    registry: digest_runner.DigestRegistry,
    config: outline.OutlineConfig,
    draft: models.DigestDraft,
    title: str,
) -> None:
    """문서를 만들고 슬롯을 비운다.

    실패하면 아무것도 건드리지 않는다. 초안이 화면에 그대로 남아
    원인을 고친 뒤 같은 버튼을 다시 누르면 된다. 로컬에 쓸 것이
    없으므로 "문서는 만들어졌는데 기록이 실패" 같은 틈이 없다.
    """
    with st.spinner("Outline 에 저장 중"):
        try:
            document = outline.create_document(
                config, title, digest_markdown.to_markdown(draft)
            )
        except outline.OutlineError as error:
            st.error(str(error))
            return
    _reset(registry)
    st.session_state[_SAVED_KEY] = (document.title, document.url)
    st.rerun()


def _reset(registry: digest_runner.DigestRegistry) -> None:
    """슬롯을 비우고 이번 초안에 쓰던 제목 입력을 지운다.

    ``_TITLE_KEY`` 위젯 값은 한 번 ``session_state`` 에 들어가면
    그다음부터는 ``value=`` 기본값이 무시되고 저장된 값이 이긴다.
    지우지 않으면 다음 초안의 제목 칸에 이전 정리본의 제목이 남을
    여지가 생긴다. 저장·버리기·재시도, 정리를 끝내는 모든 자리에서
    이 함수 하나로 슬롯과 제목 입력을 같이 정리한다.
    """
    registry.clear()
    st.session_state.pop(_TITLE_KEY, None)


def _render_saved() -> None:
    """방금 저장한 정리본의 링크를 보여 준다."""
    title, url = st.session_state[_SAVED_KEY]
    st.success("Outline 에 저장했습니다.")
    st.markdown(f"**{title}**")
    st.link_button("Outline 에서 열기", url, key="digest_open")
    st.caption(
        "이 정리본은 로컬에 남지 않습니다. 수정·삭제·검색은 Outline"
        " 에서 하세요."
    )
    if st.button("새 정리본 만들기", key="digest_new"):
        st.session_state.pop(_SAVED_KEY, None)
        st.rerun()
