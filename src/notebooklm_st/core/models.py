"""화면과 저장소가 함께 쓰는 값 객체."""

import dataclasses
import datetime
import json
from collections.abc import Sequence


@dataclasses.dataclass(frozen=True, slots=True)
class Question:
    """저장된 질문 템플릿."""

    id: int
    title: str
    text: str
    created_at: str
    updated_at: str


@dataclasses.dataclass(frozen=True, slots=True)
class Channel:
    """구독 중인 채널 하나."""

    id: int
    channel_id: str
    """``UC`` 로 시작하는 YouTube 채널 ID."""
    title: str
    url: str
    baseline: str
    """``YYYY-MM-DD``. 이 날짜 이후 업로드만 신규로 본다."""
    created_at: str


@dataclasses.dataclass(frozen=True, slots=True)
class FeedEntry:
    """채널 피드의 항목 하나.

    채널이 어느 것인지는 담지 않는다. 호출자가 채널마다 따로 읽어
    쓰므로 중복이 된다.
    """

    video_id: str
    title: str
    published: datetime.datetime
    """타임존이 붙은 시각. 피드가 UTC 로 준다."""


@dataclasses.dataclass(frozen=True, slots=True)
class Citation:
    """답변이 근거로 든 자막 구절."""

    number: int
    text: str
    score: float


@dataclasses.dataclass(frozen=True, slots=True)
class AnswerItem:
    """질문 하나에 대한 실행 결과.

    ``answer`` 와 ``error`` 는 배타적이다. 성공한 항목은 ``error`` 가
    ``None`` 이고, 실패한 항목은 ``answer`` 가 ``None`` 이다.

    ``question_title`` 과 ``question_text`` 를 둘 다 복사해 둔다.
    화면은 제목을 머리글로 쓰고 원문은 접어서 보여준다.

    ``id`` 는 이력에서 읽어온 항목만 가진다. 파이프라인이 갓 만든
    항목은 아직 저장되지 않아 ``None`` 이며, 화면은 이 값이 있을 때만
    편집 상자를 그린다.
    """

    question_title: str
    question_text: str
    answer: str | None
    citations: tuple[Citation, ...]
    error: str | None
    id: int | None = None

    @property
    def succeeded(self) -> bool:
        """실패 메시지가 없으면 참."""
        return self.error is None


@dataclasses.dataclass(frozen=True, slots=True)
class RunResult:
    """영상 하나에 질문들을 던진 결과 전체.

    ``title`` 은 NotebookLM 이 소스에서 읽어 온 영상 제목이다. 못 얻는
    실행이 있으므로 없을 수 있고, 그때는 화면이 ``video_id`` 로
    대신한다.
    """

    url: str
    video_id: str
    items: tuple[AnswerItem, ...]
    title: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    """이력 목록에 한 줄로 보여 줄 실행 요약.

    ``exported_at`` 이 채워져 있으면 이 실행은 Outline 으로 넘어갔고
    로컬에는 링크만 남아 있다. 넷은 항상 함께 채워지거나 함께 비어
    있다.
    """

    id: int
    url: str
    video_id: str
    title: str | None
    created_at: str
    answer_count: int
    outline_id: str | None = None
    outline_url: str | None = None
    outline_title: str | None = None
    exported_at: str | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class VideoMetadata:
    """영상에서 뽑아 온 메타데이터.

    영상명과 URL 은 담지 않는다. ``RunSummary`` 에 이미 있어
    중복이 된다.
    """

    channel: str | None
    upload_date: str | None


@dataclasses.dataclass(frozen=True, slots=True)
class DigestSource:
    """정리 파이프라인에 넣을 글 한 편.

    이 글이 위키에서 왔다는 사실은 담지 않는다. ``services.nlm`` 은
    재료의 출처를 몰라도 되고, 몰라야 Outline 과 엮이지 않는다.
    """

    title: str
    text: str


@dataclasses.dataclass(frozen=True, slots=True)
class DigestDraft:
    """아직 저장하지 않은 정리본.

    로컬 DB 에 남지 않는다. 화면이 세션에 들고 있다가 저장하면
    Outline 이 정본이 되고, 버리면 그대로 사라진다.

    ``sources`` 는 재료가 된 실행들이다. 저장할 문서에 출처 링크를
    적는 데 쓴다.
    """

    body: str
    sources: tuple[RunSummary, ...]
    instruction: str
    created_on: str
    """``2026-09-23`` 형식의 날짜. 문서에 적고, 주제를
    받지 못했을 때 제목 기본값에도 쓴다."""
    topic: str | None = None
    """NotebookLM 이 정리와 함께 지은 주제. 제목
    기본값이 된다. 답변이 제목 줄을 주지 않으면
    ``None`` 이다(→ ``core.digest_title``)."""


@dataclasses.dataclass(frozen=True, slots=True)
class TempNotebook:
    """정리 대상인 임시 노트북."""

    id: str
    title: str


def citations_to_json(citations: Sequence[Citation]) -> str:
    """인용 목록을 저장용 JSON 문자열로 바꾼다.

    한글이 이스케이프되면 DB 를 직접 들여다볼 때 읽기 어려우므로
    ``ensure_ascii`` 를 끈다.

    Args:
        citations: 저장할 인용 목록.

    Returns:
        JSON 배열 문자열.
    """
    payload = [
        {"n": item.number, "text": item.text, "score": item.score}
        for item in citations
    ]
    return json.dumps(payload, ensure_ascii=False)


def citations_from_json(payload: str | None) -> tuple[Citation, ...]:
    """저장된 JSON 문자열을 인용 목록으로 되돌린다.

    Args:
        payload: ``citations_to_json`` 이 만든 문자열. 비어 있거나
            ``None`` 이면 빈 결과를 돌려준다.

    Returns:
        인용 목록.
    """
    if not payload:
        return ()
    raw = json.loads(payload)
    return tuple(
        Citation(number=row["n"], text=row["text"], score=row["score"])
        for row in raw
    )
