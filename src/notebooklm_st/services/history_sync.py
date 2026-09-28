"""저장된 이력과 Outline 문서 목록을 맞춘다.

``plan`` 은 두 목록을 받아 무엇을 지우고 만들지 정하는 순수 함수이고,
``apply`` 는 그 계획을 DB 에 쓴다. httpx 도 Streamlit 도 모른다.
목록을 읽는 것은 ``services.outline``, DB 를 읽는 것은
``services.run_history`` 가 한다.
"""

import dataclasses
import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import models, outline_import, youtube
from notebooklm_st.services import run_history_sync

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


@dataclasses.dataclass(frozen=True, slots=True)
class SyncResult:
    """적용이 실제로 바꾼 개수.

    계획의 개수와 다를 수 있다. 미리보기와 적용 사이에 다른 탭이
    먼저 지우거나 저장했을 수 있다.
    """

    deleted: int
    created: int


def apply(
    connection: sqlite3.Connection, sync_plan: models.SyncPlan
) -> SyncResult:
    """계획을 DB 에 쓴다. 삭제와 삽입을 커밋 하나로 묶는다.

    어느 쪽이든 실패하면 전부 되돌리고 다시 던진다. 커넥션은 앱
    전체가 함께 쓰므로 반쪽만 걸린 채 나가면 다른 곳의 commit 이
    그것을 확정해 버린다(``run_history.mark_exported`` 와 같은 이유).

    Args:
        connection: 열린 커넥션.
        sync_plan: ``plan`` 이 세운 계획.

    Returns:
        실제로 지운 개수와 만든 개수.

    Raises:
        sqlite3.Error: 삭제나 삽입이 실패한 경우. 되돌린 뒤 던진다.
    """
    try:
        deleted = run_history_sync.delete_runs(
            connection, [run.id for run in sync_plan.deletes]
        )
        created = 0
        for create in sync_plan.creates:
            inserted = run_history_sync.insert_exported(connection, create)
            if inserted is not None:
                created += 1
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return SyncResult(deleted=deleted, created=created)
