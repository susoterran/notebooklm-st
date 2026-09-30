"""이력 한 건을 Outline 에 올리고 로컬에 링크를 적는다.

이력 화면의 저장 버튼과 러너의 자동 저장이 이 한 벌을 함께 쓴다. 두
길의 실패 처리("다시 저장하면 문서가 둘이 됩니다")가 어긋나지 않게
하려는 것이다. 무엇을 올릴지(제목, 인용을 뺄지)는 부르는 쪽이 정해서
넘긴다.
"""

import sqlite3
from collections.abc import Sequence

from notebooklm_st.core import markdown_export, models
from notebooklm_st.services import outline, run_history


class RecordError(Exception):
    """문서는 만들어졌는데 로컬 기록에 실패했다.

    되돌리지 않는다. 방금 만든 문서를 지우려면 그 삭제도 실패할 수
    있어 틈이 한 겹 더 생길 뿐이다. 사실대로 알리고 사람이 링크를 들고
    판단하게 한다.
    """

    def __init__(
        self, document: outline.SavedDocument, cause: Exception
    ) -> None:
        """만들어진 문서와 기록 실패의 원인을 담는다.

        Args:
            document: 이미 만들어진 문서.
            cause: 로컬 기록이 낸 예외.
        """
        super().__init__(
            f"문서는 만들어졌습니다: {document.url} —"
            " 로컬 기록에 실패했습니다"
            f"({type(cause).__name__})."
            " 다시 저장하면 문서가 둘이 됩니다."
        )
        self.document = document


def save(
    connection: sqlite3.Connection,
    config: outline.OutlineConfig,
    summary: models.RunSummary,
    title: str,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None,
) -> outline.SavedDocument:
    """문서를 만들고 로컬에 링크를 적는다.

    링크를 적으면서 로컬 답변을 지운다(``run_history.mark_exported``).

    Args:
        connection: 열린 커넥션.
        config: 주소·토큰·컬렉션 ID.
        summary: 올릴 실행의 요약. 영상 URL 과 실행 ID 를 쓴다.
        title: 문서 제목. 부르는 쪽이 다듬어 넘긴다.
        items: 문서에 담을 답변. 인용을 뺄지는 부르는 쪽이 정한다.
        metadata: 문서 머리에 적을 영상 메타데이터.

    Returns:
        만들어진 문서.

    Raises:
        outline.OutlineError: 문서를 만들지 못했다. 로컬은 그대로다.
        RecordError: 문서는 만들었는데 로컬 기록에 실패했다.
    """
    document = outline.create_document(
        config,
        title,
        markdown_export.to_markdown(summary, items, title, metadata),
    )
    try:
        run_history.mark_exported(
            connection,
            summary.id,
            document_id=document.id,
            document_title=document.title,
            document_url=document.url,
        )
    except (ValueError, sqlite3.Error) as error:
        # mark_exported 가 실제로 내는 둘만 잡는다. 더 넓게 잡으면
        # 나중에 생길 프로그래밍 오류까지 "문서가 둘이 됩니다" 로
        # 둔갑해 진짜 버그가 드러나지 않는다.
        raise RecordError(document, error) from error
    return document
