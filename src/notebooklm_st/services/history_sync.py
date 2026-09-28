"""저장된 이력과 Outline 문서 목록을 맞춘다.

``plan`` 은 두 목록을 받아 무엇을 지우고 만들지 정하는
순수 함수다. httpx 도 Streamlit 도 모른다. 목록을 읽는
것은 ``services.outline``, DB 를 읽는 것은
``services.run_history`` 가 한다.
"""

from collections.abc import Sequence

from notebooklm_st.core import models, outline_import, youtube

SKIP_NO_SOURCE_URL = "영상 URL 없음"
"""정리본이나 손으로 쓴 문서. 이력 문서가 아니다."""

SKIP_BAD_SOURCE_URL = "영상 URL 인식 불가"
"""영상 URL 줄은 있는데 YouTube 영상 ID 를 뽑지 못했다."""


def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[models.ListedDocument],
) -> models.SyncPlan:
    """두 목록을 문서 ID 로 맞춰 동기화 계획을 세운다.

    문서 목록에 없는 행은 지우고, 어떤 행도 가리키지 않는
    문서는 본문에 영상 URL 이 있을 때만 만든다. 같은 문서를
    가리키는 행이 둘이어도, 같은 영상의 문서가 둘이어도
    정리하지 않는다 — 동기화는 중복을 만들지 않을 뿐이다.

    Args:
        exported: ``exported_at`` 이 있는 행들. 미저장
            실행은 여기 들어오지 않으므로 삭제될 수 없다.
        documents: 컬렉션의 문서 전부.

    Returns:
        입력 순서를 지킨 계획.
    """
    known_ids = {run.outline_id for run in exported}
    listed_ids = {document.id for document in documents}
    deletes = tuple(run for run in exported if run.outline_id not in listed_ids)
    creates: list[models.SyncCreate] = []
    skips: list[models.SyncSkip] = []
    for document in documents:
        if document.id in known_ids:
            continue
        url = outline_import.find_source_url(document.markdown)
        if url is None:
            skips.append(
                models.SyncSkip(document=document, reason=SKIP_NO_SOURCE_URL)
            )
            continue
        video_id = youtube.extract_video_id(url)
        if video_id is None:
            skips.append(
                models.SyncSkip(document=document, reason=SKIP_BAD_SOURCE_URL)
            )
            continue
        creates.append(
            models.SyncCreate(document=document, url=url, video_id=video_id)
        )
    return models.SyncPlan(
        deletes=deletes, creates=tuple(creates), skips=tuple(skips)
    )
