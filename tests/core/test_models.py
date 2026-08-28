"""도메인 값 객체 테스트."""

import dataclasses

import pytest

from notebooklm_st.core import models


def test_answer_item_succeeded_when_no_error():
    """오류가 없는 답변은 성공으로 판정한다."""
    item = models.AnswerItem(
        question_text="핵심 주장은?",
        answer="세 가지다.",
        citations=(),
        error=None,
    )
    assert item.succeeded is True


def test_answer_item_not_succeeded_when_error_present():
    """오류가 있으면 성공이 아니다."""
    item = models.AnswerItem(
        question_text="핵심 주장은?",
        answer=None,
        citations=(),
        error="답변을 받지 못했습니다.",
    )
    assert item.succeeded is False


def test_value_objects_are_frozen():
    """값 객체는 수정할 수 없어야 한다."""
    citation = models.Citation(number=1, text="인용", score=0.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        citation.number = 2


def test_citations_round_trip():
    """인용을 JSON으로 직렬화하고 역직렬화한다."""
    citations = (
        models.Citation(number=1, text="첫 구절", score=0.82),
        models.Citation(number=2, text="둘째 구절", score=0.41),
    )
    payload = models.citations_to_json(citations)
    assert models.citations_from_json(payload) == citations


def test_citations_json_keeps_hangul_readable():
    """JSON 직렬화 시 한글을 이스케이프하지 않는다."""
    payload = models.citations_to_json(
        (models.Citation(number=1, text="한글", score=1.0),)
    )
    assert "한글" in payload


def test_citations_from_json_handles_empty():
    """빈 JSON 입력을 처리한다."""
    assert models.citations_from_json(None) == ()
    assert models.citations_from_json("") == ()
