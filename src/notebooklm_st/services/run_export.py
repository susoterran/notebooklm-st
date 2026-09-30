"""이력 한 건을 Outline 에 올리고 로컬에 링크를 적는다.

이력 화면의 저장 버튼과 러너의 자동 저장이 이 한 벌을 함께 쓴다. 두
길의 실패 처리("다시 저장하면 문서가 둘이 됩니다")가 어긋나지 않게
하려는 것이다. 무엇을 올릴지(제목, 인용을 뺄지)는 부르는 쪽이 정해서
넘긴다.

러너가 답변을 받자마자 부르는 자동 저장 한 번(``save_automatically``)
도 여기 둔다. 건너뛸지 가르고, 이력을 다시 읽어 인용을 빼고, 저장한
뒤 결과를 실행 현황 표의 저장 칸에 그릴 값으로 바꾼다. 러너는 스레드
순서만 갖는다.
"""

import contextlib
import logging
import pathlib
import sqlite3
import threading
from collections.abc import Iterator, Sequence

from notebooklm_st.core import answer_text, auto_save, markdown_export, models
from notebooklm_st.services import outline, run_history, runs, store

logger = logging.getLogger(__name__)

_CONFLICT_MESSAGE = (
    "이미 Outline 에 저장했거나 저장 중인 실행입니다."
    " 화면을 새로 고쳐 확인하세요."
)

# 이력 화면과 러너 스레드는 커넥션이 따로지만 이 모듈 객체는 함께
# 본다. 그래서 선점을 커넥션이 아니라 프로세스에 둔다.
_saving_lock = threading.Lock()
_saving: set[int] = set()


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


class SaveConflictError(Exception):
    """같은 실행을 이미 저장했거나 다른 길이 저장하고 있다."""

    def __init__(self) -> None:
        """사람에게 보일 문구 하나로 만든다."""
        super().__init__(_CONFLICT_MESSAGE)


@contextlib.contextmanager
def _claimed(run_id: int) -> Iterator[None]:
    """실행 하나를 이 프로세스 안에서 선점하고, 어떻게 끝나든 푼다.

    Args:
        run_id: 선점할 실행 ID.

    Yields:
        선점한 동안 한 번.

    Raises:
        SaveConflictError: 다른 길이 그 실행을 저장하고 있다.
    """
    with _saving_lock:
        if run_id in _saving:
            raise SaveConflictError()
        _saving.add(run_id)
    try:
        yield
    finally:
        with _saving_lock:
            _saving.discard(run_id)


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

    이력 화면과 자동 저장이 같은 실행을 겹쳐 올리지 않도록 실행 ID 를
    먼저 선점하고, 선점한 뒤 저장 여부를 DB 에서 다시 읽는다. 부르는
    쪽이 든 요약은 저장 전의 것일 수 있다.

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
        SaveConflictError: 이미 저장했거나 다른 길이 저장하고 있다.
            문서를 만들지 않는다.
        outline.OutlineError: 문서를 만들지 못했다. 로컬은 그대로다.
        RecordError: 문서는 만들었는데 로컬 기록에 실패했다.
    """
    with _claimed(summary.id):
        current = run_history.load_run(connection, summary.id)
        # 없는 실행은 그대로 보낸다. mark_exported 의 ValueError 가
        # RecordError 로 드러난다.
        if current is not None and current.exported_at is not None:
            raise SaveConflictError()
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


def save_automatically(
    db_path: pathlib.Path,
    history_id: int,
    result: models.RunResult,
    metadata: models.VideoMetadata | None,
) -> runs.SaveOutcome:
    """방금 남긴 이력 한 건을 인용을 뺀 채 Outline 에 올린다.

    러너 스레드가 이력을 남긴 직후 부른다. 어떻게 끝나든 예외를 밖으로
    내지 않고 결과로 돌려준다. 건너뛰거나 실패한 실행은 이력에
    미저장으로 남아 이력 화면의 저장 버튼이 다음 길이 된다.

    Args:
        db_path: 이력 DB 경로. 부른 스레드가 자기 커넥션을 연다.
        history_id: 방금 남긴 이력의 ID.
        result: 파이프라인이 돌려준 결과. 건너뛸지와 제목을 본다.
        metadata: 문서 머리에 적을 영상 메타데이터.

    Returns:
        표의 저장 칸에 그릴 결과.
    """
    reason = auto_save.skip_reason(result)
    if reason is not None:
        return runs.SaveOutcome("skipped", f"미저장 · {reason}", None)
    config = outline.config_from_env()
    if config is None:
        return runs.SaveOutcome("skipped", "미저장 · Outline 설정 없음", None)
    # skip_reason 이 빈 제목을 이미 걸렀다. ``or ""`` 는 mypy 용이다.
    title = (result.title or "").strip()
    try:
        document = _upload(config, history_id, title, metadata, db_path)
    except SaveConflictError:
        return runs.SaveOutcome("skipped", "이미 저장했거나 저장 중", None)
    except outline.OutlineError as error:
        logger.warning("이력 %s 자동 저장 실패: %s", history_id, error)
        return runs.SaveOutcome("failed", f"미저장 · 저장 실패: {error}", None)
    except RecordError as error:
        logger.warning("이력 %s 자동 저장 실패: %s", history_id, error)
        return runs.SaveOutcome("failed", str(error), error.document.url)
    except Exception as error:
        # 러너 스레드 최상위와 같은 이유로 넓게 잡는다. 여기서 예외가
        # 새면 이미 이력에 남은 실행이 "실행 중" 에 멈춘다.
        logger.exception("이력 %s 자동 저장 실패", history_id)
        return runs.SaveOutcome(
            "failed",
            f"미저장 · 예상 못 한 오류({type(error).__name__})",
            None,
        )
    return runs.SaveOutcome("saved", "저장됨", document.url)


def _upload(
    config: outline.OutlineConfig,
    history_id: int,
    title: str,
    metadata: models.VideoMetadata | None,
    db_path: pathlib.Path,
) -> outline.SavedDocument:
    """이력에서 요약과 답변을 읽어 인용을 빼고 저장한다.

    올라가는 본문이 이력에 남은 것과 같도록 결과 객체가 아니라 DB 에서
    다시 읽는다. 인용을 빼는 것은 이력 화면의 "인용 포함" 을 끈 것과
    같은 사본이다.

    Raises:
        SaveConflictError: 이미 저장했거나 다른 길이 저장하고 있다.
        outline.OutlineError: 문서를 만들지 못했다.
        RecordError: 문서는 만들었는데 기록에 실패했다.
        LookupError: 방금 남긴 이력을 찾지 못했다.
    """
    connection = store.connect(db_path)
    try:
        summary = run_history.load_run(connection, history_id)
        if summary is None:
            raise LookupError(
                f"방금 남긴 이력 {history_id} 을 찾지 못했습니다."
            )
        items = [
            answer_text.for_display(item)
            for item in run_history.load_run_items(connection, history_id)
        ]
        return save(connection, config, summary, title, items, metadata)
    finally:
        connection.close()
