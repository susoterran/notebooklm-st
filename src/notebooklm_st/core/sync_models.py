"""이력 동기화가 쓰는 값 객체.

Outline 문서 목록과 저장된 이력을 맞추는 계획을 담는다. 동기화만
쓰므로 ``core.models`` 에서 떼어 둔다(→ ``services.history_sync``).
"""

import dataclasses

from notebooklm_st.core import models


@dataclasses.dataclass(frozen=True, slots=True)
class ListedDocument:
    """Outline 목록에서 읽어 온 문서 하나.

    정리본이 쓰는 ``services.outline.OutlineDocument`` 와
    다르다. 동기화는 링크와 생성 시각도 필요하다.
    """

    id: str
    title: str
    url: str
    """절대 URL. 상대 경로는 ``services.outline`` 이 붙여서 넘긴다."""
    created_at: str
    """로컬 시각의 초 단위 ISO 문자열. ``store.now()`` 와
    같은 형식."""
    markdown: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncCreate:
    """동기화가 새로 만들 이력 한 건."""

    document: ListedDocument
    url: str
    """본문에서 읽은 영상 URL."""
    video_id: str
    metadata: models.VideoMetadata | None = None
    """문서 머리에서 읽은 채널·업로드 일자. 두 줄이 다 없으면
    ``None``."""
    categories: tuple[str, ...] = ()
    """문서 머리에서 읽은 카테고리 이름. 줄이 없으면 비어 있다."""


@dataclasses.dataclass(frozen=True, slots=True)
class SyncSkip:
    """동기화가 건너뛴 문서 한 건과 그 사유."""

    document: ListedDocument
    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class SyncUpdate:
    """동기화가 메타데이터를 갱신할 기존 행 한 건."""

    run: models.RunSummary
    metadata: models.VideoMetadata
    """쓸 값. 문서가 준 칸과 로컬에 남길 칸을 합친 결과다."""


@dataclasses.dataclass(frozen=True, slots=True)
class SyncCategoryUpdate:
    """동기화가 카테고리를 바꿀 기존 행 한 건."""

    run: models.RunSummary
    categories: tuple[str, ...]
    """문서 머리에서 읽은 이름. 이 집합으로 바꾼다."""


@dataclasses.dataclass(frozen=True, slots=True)
class SyncPlan:
    """미리보기와 적용이 함께 쓰는 동기화 계획.

    기존 행 중 손대지 않는 것은 담지 않는다. 화면이
    보여 줄 것은 바뀌는 것뿐이다.
    """

    deletes: tuple[models.RunSummary, ...]
    creates: tuple[SyncCreate, ...]
    skips: tuple[SyncSkip, ...]
    updates: tuple[SyncUpdate, ...] = ()
    category_updates: tuple[SyncCategoryUpdate, ...] = ()
    new_categories: tuple[str, ...] = ()
    """로컬에 없어 새로 등록할 이름. 이름 순이다."""

    @property
    def is_empty(self) -> bool:
        """지울 것도 만들 것도 갱신할 것도 없다.

        ``new_categories`` 는 보지 않는다. 새 이름은 생성 대상이나
        카테고리 갱신 대상에서만 나온다.
        """
        return not (
            self.deletes
            or self.creates
            or self.updates
            or self.category_updates
        )
