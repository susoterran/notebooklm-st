"""정리본 화면 — 저장된 요약본 여럿을 문서 하나로."""

import streamlit as st

from notebooklm_st import session
from notebooklm_st.core import labels, models
from notebooklm_st.services import digest_runner, nlm, outline, run_history

_SELECTED_KEY = "digest_selected"
_INSTRUCTION_KEY = "digest_instruction"

_POLL_INTERVAL = "1s"

DEFAULT_INSTRUCTION = (
    "아래 문서들은 각각 다른 영상의 요약본이다. 공통된 주장과"
    " 엇갈리는 지점을 찾아 하나의 글로 정리해 줘. 각 주장이 어느"
    " 문서에서 나온 것인지 문서 제목으로 밝히고, 마지막에 남은"
    " 의문을 적어 줘."
)
"""화면에 채워 두는 기본 정리 지시.

정본은 이 한 줄이다. 사람이 이번 정리에만 고쳐 쓸 수 있고, 고친
값은 저장되지 않는다 — 정리는 매번 목적이 다르다.
"""


def render() -> None:
    """재료를 고르고 정리를 시작한다. 진행 중이면 진행을 보여 준다."""
    st.title("정리본")
    registry = session.get_digest_registry()
    if registry.is_running():
        _render_running()
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
    instruction = st.text_area(
        "정리 지시",
        value=DEFAULT_INSTRUCTION,
        key=_INSTRUCTION_KEY,
        help="이번 정리에만 적용됩니다. 저장되지 않습니다.",
    )
    _render_start(
        registry, config, [by_id[key] for key in selected_ids], instruction
    )


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
        disabled=not selected or too_many or busy or not instruction.strip(),
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
