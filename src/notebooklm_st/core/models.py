"""화면과 저장소가 함께 쓰는 값 객체."""

import dataclasses
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
    """

    question_title: str
    question_text: str
    answer: str | None
    citations: tuple[Citation, ...]
    error: str | None

    @property
    def succeeded(self) -> bool:
        """실패 메시지가 없으면 참."""
        return self.error is None


@dataclasses.dataclass(frozen=True, slots=True)
class RunResult:
    """영상 하나에 질문들을 던진 결과 전체."""

    url: str
    video_id: str
    items: tuple[AnswerItem, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class RunSummary:
    """이력 목록에 한 줄로 보여 줄 실행 요약."""

    id: int
    url: str
    video_id: str
    created_at: str
    answer_count: int


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
