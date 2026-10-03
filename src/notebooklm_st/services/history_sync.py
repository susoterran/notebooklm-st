"""저장된 이력과 Outline 문서 목록을 맞춘다.

``plan`` 은 두 목록을 받아 무엇을 지우고 만들지 정하는 순수 함수이고,
``apply`` 는 그 계획을 DB 에 쓴다. httpx 도 Streamlit 도 모른다.
목록을 읽는 것은 ``services.outline``, DB 를 읽고 쓰는 것은
``services.run_history_sync`` 가 한다.
"""

import dataclasses
import itertools
import sqlite3
from collections.abc import Collection, Iterator, Mapping, Sequence

from notebooklm_st.core import (
    category_names,
    models,
    outline_import,
    sync_models,
    youtube,
)
from notebooklm_st.services import categories, run_history_sync

SKIP_NO_SOURCE_URL = "영상 URL 없음"
"""정리본이나 손으로 쓴 문서. 이력 문서가 아니다."""

SKIP_BAD_SOURCE_URL = "영상 URL 인식 불가"
"""영상 URL 줄은 있는데 YouTube 영상 ID 를 뽑지 못했다."""


def plan(
    exported: Sequence[models.RunSummary],
    documents: Sequence[sync_models.ListedDocument],
    known_categories: Collection[str] = frozenset(),
) -> sync_models.SyncPlan:
    """두 목록을 문서 ID 로 맞춰 동기화 계획을 세운다.

    문서 목록에 없는 행은 지우고, 어떤 행도 가리키지 않는
    문서는 본문에 영상 URL 이 있을 때만 만든다. 둘 다 있는 행은
    문서 머리의 채널·업로드 일자가 로컬과 다를 때만 메타데이터를
    갱신하고, 카테고리 이름 집합이 다를 때만 카테고리를 바꾼다. 같은
    문서를 가리키는 행이 둘이어도, 같은 영상의 문서가 둘이어도
    정리하지 않는다 — 동기화는 중복을 만들지 않을 뿐이다.

    Args:
        exported: ``exported_at`` 이 있는 행들. 미저장
            실행은 여기 들어오지 않으므로 삭제될 수 없다.
        documents: 컬렉션의 문서 전부.
        known_categories: 로컬에 등록된 카테고리 이름. 문서에 나온
            이름 중 여기 없는 것이 새로 등록할 이름이 된다.

    Returns:
        입력 순서를 지킨 계획.
    """
    known_ids = {run.outline_id for run in exported}
    listed = {document.id: document for document in documents}
    deletes = tuple(run for run in exported if run.outline_id not in listed)
    creates: list[sync_models.SyncCreate] = []
    skips: list[sync_models.SyncSkip] = []
    for document in documents:
        if document.id in known_ids:
            continue
        url = outline_import.find_source_url(document.markdown)
        if url is None:
            skips.append(
                sync_models.SyncSkip(
                    document=document, reason=SKIP_NO_SOURCE_URL
                )
            )
            continue
        video_id = youtube.extract_video_id(url)
        if video_id is None:
            skips.append(
                sync_models.SyncSkip(
                    document=document, reason=SKIP_BAD_SOURCE_URL
                )
            )
            continue
        creates.append(
            sync_models.SyncCreate(
                document=document,
                url=url,
                video_id=video_id,
                metadata=outline_import.find_metadata(document.markdown),
                categories=(
                    outline_import.find_categories(document.markdown) or ()
                ),
            )
        )
    category_updates = tuple(_category_updates(exported, listed))
    return sync_models.SyncPlan(
        deletes=deletes,
        creates=tuple(creates),
        skips=tuple(skips),
        updates=tuple(_updates(exported, listed)),
        category_updates=category_updates,
        new_categories=_new_categories(
            creates, category_updates, known_categories
        ),
    )


def _updates(
    exported: Sequence[models.RunSummary],
    listed: Mapping[str, sync_models.ListedDocument],
) -> Iterator[sync_models.SyncUpdate]:
    """문서 머리의 메타데이터가 로컬과 다른 기존 행을 입력 순서로 고른다.

    문서에서 두 값을 모두 못 읽으면 그 행은 건드리지 않는다.
    직렬화가 바뀌어 파싱이 실패할 때 멀쩡한 로컬 값이 한꺼번에 비지
    않게 한다.
    """
    for run in exported:
        document = listed.get(run.outline_id or "")
        if document is None:
            continue
        found = outline_import.find_metadata(document.markdown)
        if found is None:
            continue
        merged = _merge(run.metadata, found)
        if merged != run.metadata:
            yield sync_models.SyncUpdate(run=run, metadata=merged)


def _category_updates(
    exported: Sequence[models.RunSummary],
    listed: Mapping[str, sync_models.ListedDocument],
) -> Iterator[sync_models.SyncCategoryUpdate]:
    """문서의 카테고리 이름 집합이 로컬과 다른 행을 입력 순서로 고른다.

    문서에서 카테고리를 못 읽으면 그 행은 건드리지 않는다. 메타데이터와
    같은 이유다 — 직렬화가 바뀌어 파싱이 실패할 때 멀쩡한 로컬 값이
    한꺼번에 비지 않게 한다.
    """
    for run in exported:
        document = listed.get(run.outline_id or "")
        if document is None:
            continue
        found = outline_import.find_categories(document.markdown)
        if found is None:
            continue
        if set(found) != set(run.categories):
            yield sync_models.SyncCategoryUpdate(run=run, categories=found)


def _new_categories(
    creates: Sequence[sync_models.SyncCreate],
    category_updates: Sequence[sync_models.SyncCategoryUpdate],
    known: Collection[str],
) -> tuple[str, ...]:
    """생성·카테고리 갱신 대상의 이름 중 로컬에 없는 것을 모은다."""
    names = _referenced_names(creates, category_updates)
    return category_names.ordered(name for name in names if name not in known)


def _referenced_names(
    creates: Sequence[sync_models.SyncCreate],
    category_updates: Sequence[sync_models.SyncCategoryUpdate],
) -> Iterator[str]:
    """생성·카테고리 갱신 대상이 가리키는 이름을 모두 낸다."""
    return itertools.chain(
        (name for create in creates for name in create.categories),
        (name for change in category_updates for name in change.categories),
    )


def _merge(
    local: models.VideoMetadata | None, found: models.VideoMetadata
) -> models.VideoMetadata:
    """문서가 준 칸은 문서 값, 주지 않은 칸은 로컬 값으로 합친다."""
    kept = local or models.VideoMetadata(channel=None, upload_date=None)
    return models.VideoMetadata(
        channel=found.channel if found.channel is not None else kept.channel,
        upload_date=(
            found.upload_date
            if found.upload_date is not None
            else kept.upload_date
        ),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class SyncResult:
    """적용이 실제로 바꾼 개수.

    계획의 개수와 다를 수 있다. 미리보기와 적용 사이에 다른 탭이
    먼저 지우거나 저장했을 수 있다.
    """

    deleted: int
    created: int
    updated: int = 0
    """메타데이터를 새로 넣거나 값을 바꾼 행 수."""
    recategorized: int = 0
    """카테고리를 바꾼 행 수."""
    categories_added: int = 0
    """새로 등록한 카테고리 수. 다른 탭이 먼저 등록했으면 계획보다
    작고, 미리보기 때 있던 이름을 다른 탭이 지웠으면 계획보다 크다."""


def apply(
    connection: sqlite3.Connection, sync_plan: sync_models.SyncPlan
) -> SyncResult:
    """계획을 DB 에 쓴다. 등록·삭제·삽입·갱신을 커밋 하나로 묶는다.

    카테고리를 먼저 등록한다. 삽입과 카테고리 교체가 이름으로 잇기
    때문이다. 계획의 새 이름만이 아니라 생성·카테고리 갱신 대상이
    가리키는 이름을 모두 넘긴다. 미리보기 때 있던 이름을 그사이 다른
    탭이 지웠어도 다시 등록해 잇는다. 이미 있는 이름은 건너뛴다.

    어느 것이든 실패하면 전부 되돌리고 다시 던진다. 커넥션은 앱
    전체가 함께 쓰므로 반쪽만 걸린 채 나가면 다른 곳의 commit 이
    그것을 확정해 버린다(``run_links.mark_exported`` 와 같은 이유).

    삭제는 ``(실행 ID, 문서 ID)`` 쌍으로 맞춘다. 계획이 세션에 남아
    있는 사이 SQLite 가 지워진 ID 를 새 미저장 실행에 다시 줄 수
    있어서다. 문서 ID 까지 맞으면 그 실행은 지워지지 않는다.

    Args:
        connection: 열린 커넥션.
        sync_plan: ``plan`` 이 세운 계획.

    Returns:
        실제로 지운·만든·갱신·등록한 개수.

    Raises:
        sqlite3.Error: 등록·삭제·삽입·갱신이 실패한 경우. 되돌린 뒤
            던진다.
    """
    try:
        categories_added = categories.ensure(
            connection,
            category_names.ordered(
                _referenced_names(sync_plan.creates, sync_plan.category_updates)
            ),
        )
        deleted = run_history_sync.delete_runs(
            connection,
            [(run.id, run.outline_id or "") for run in sync_plan.deletes],
        )
        created = 0
        for create in sync_plan.creates:
            inserted = run_history_sync.insert_exported(connection, create)
            if inserted is not None:
                created += 1
        updated = 0
        for update in sync_plan.updates:
            if run_history_sync.write_metadata(
                connection,
                update.run.id,
                update.run.outline_id or "",
                update.metadata,
            ):
                updated += 1
        recategorized = 0
        for change in sync_plan.category_updates:
            if run_history_sync.replace_categories(
                connection,
                change.run.id,
                change.run.outline_id or "",
                change.categories,
            ):
                recategorized += 1
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return SyncResult(
        deleted=deleted,
        created=created,
        updated=updated,
        recategorized=recategorized,
        categories_added=categories_added,
    )
