"""고른 요약본들을 재료로 정리본 초안을 만든다.

Outline 과 NotebookLM 을 **둘 다 아는 유일한 모듈**이다. 그 둘은
서로를 모른다. 여기서 위키의 글이 파이프라인의 재료로 바뀐다.
"""

import asyncio
import datetime
from collections.abc import Callable, Sequence

from notebooklm_st.core import models
from notebooklm_st.services import nlm, outline


def build(
    config: outline.OutlineConfig,
    runs: Sequence[models.RunSummary],
    instruction: str,
    on_progress: Callable[[str], None],
) -> models.DigestDraft:
    """재료를 읽어 정리본 초안을 만든다.

    Args:
        config: Outline 주소·토큰.
        runs: 재료가 될 실행들. 모두 Outline 에
              저장된 것이어야 한다.
        instruction: 던질 정리 지시.
        on_progress: 진행 문구를 받는 콜백.

    Returns:
        저장 전 초안.

    Raises:
        outline.OutlineError: 재료를 한 건이라도
                              읽지 못한 경우. 메시지 앞에
                              막힌 재료의 이름이 붙는다.
        exceptions.NotebookLMError: 파이프라인이
                                    실패한 경우.
    """
    sources = _read_sources(config, runs, on_progress)
    topic, body = asyncio.run(
        nlm.run_digest_pipeline(sources, instruction, on_progress)
    )
    return models.DigestDraft(
        body=body,
        sources=tuple(runs),
        instruction=instruction,
        created_on=datetime.date.today().isoformat(),
        topic=topic,
    )


def _read_sources(
    config: outline.OutlineConfig,
    runs: Sequence[models.RunSummary],
    on_progress: Callable[[str], None],
) -> list[models.DigestSource]:
    """재료들의 본문을 위키에서 읽어 온다.

    **한 건이라도 못 읽으면 거기서 멈춘다.** 넷 중 셋으로
    만든 정리본은 넷을 정리한 것과 같은 모양이고,
    문서에는 그 사실을 알아차릴 단서가 남지 않는다.

    ``outline_id`` 가 있다고 전제한다. 화면이
    ``exported_at`` 이 있는 실행만 넘기고, ``RunSummary``
    의 계약상 그 넷은 함께 채워지거나 함께 빈다.

    Args:
        config: Outline 주소·토큰.
        runs: 읽어 올 실행들.
        on_progress: 진행 문구를 받는 콜백.

    Returns:
        파이프라인에 넣을 재료들.

    Raises:
        outline.OutlineError: 어느 한 건이라도
                              읽지 못한 경우.
    """
    sources: list[models.DigestSource] = []
    total = len(runs)
    for index, run in enumerate(runs, start=1):
        on_progress(f"재료 {index}/{total} 읽는 중")
        try:
            document = outline.fetch_document(config, run.outline_id or "")
        except outline.OutlineError as error:
            label = run.outline_title or run.title or run.video_id
            raise outline.OutlineError(
                f"'{label}' 을 읽지 못했습니다. {error}"
            ) from error
        sources.append(
            models.DigestSource(title=document.title, text=document.markdown)
        )
    return sources
