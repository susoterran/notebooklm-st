"""답변 텍스트 필터 테스트."""

from notebooklm_st.core import answer_text, models


def test_strips_a_single_marker() -> None:
    """번호 하나짜리 인용을 앞 공백까지 지운다."""
    assert answer_text.strip_citation_markers("판단 기준 [1]") == "판단 기준"


def test_strips_a_list_marker() -> None:
    """쉼표로 나열된 인용을 지우고 문장부호를 남긴다."""
    assert (
        answer_text.strip_citation_markers("결정되며[2, 3], 멀티플은")
        == "결정되며, 멀티플은"
    )


def test_strips_a_range_marker() -> None:
    """하이픈 범위 인용을 지운다."""
    assert answer_text.strip_citation_markers("판단 기준 [1-3]") == "판단 기준"


def test_keeps_non_numeric_brackets() -> None:
    """[추론] 같은 표기는 인용이 아니므로 남긴다."""
    assert answer_text.strip_citation_markers("[추론] 전제") == "[추론] 전제"


def test_keeps_markdown_links() -> None:
    """[1](url) 은 마크다운 링크이므로 건드리지 않는다."""
    text = "출처 [1](https://example.com)"
    assert answer_text.strip_citation_markers(text) == text


def test_cuts_from_the_last_rule() -> None:
    """수평선부터 끝까지 버린다."""
    text = "## 태그\n#주식\n\n---\n💡 **다음으로?**\n제안 문단"
    assert answer_text.strip_trailing_block(text) == "## 태그\n#주식"


def test_cuts_only_the_last_rule() -> None:
    """수평선이 여러 개면 마지막 것만 기준으로 삼는다."""
    text = "앞\n\n---\n\n중간\n\n---\n꼬리"
    assert answer_text.strip_trailing_block(text) == "앞\n\n---\n\n중간"


def test_keeps_text_without_a_rule() -> None:
    """수평선이 없으면 원본 그대로 돌려준다."""
    assert answer_text.strip_trailing_block("본문뿐") == "본문뿐"


def test_keeps_the_original_when_cutting_empties_it() -> None:
    """잘라 봐야 남는 게 없으면 원본을 지킨다."""
    text = "---\n꼬리뿐"
    assert answer_text.strip_trailing_block(text) == text


def test_for_display_filters_and_empties_citations() -> None:
    """표시용 사본은 본문을 거르고 인용을 비운다."""
    item = models.AnswerItem(
        question_title="핵심 주장",
        question_text="핵심 주장은?",
        answer="세 가지다 [1, 2].\n\n---\n💡 다음으로?",
        citations=(models.Citation(number=1, text="근거", score=0.9),),
        error=None,
    )

    displayed = answer_text.for_display(item)

    assert displayed.answer == "세 가지다."
    assert displayed.citations == ()
    assert displayed.question_title == "핵심 주장"
    assert displayed.question_text == "핵심 주장은?"


def test_for_display_keeps_a_failed_item_intact() -> None:
    """본문이 없는 실패 항목은 오류 문구를 그대로 둔다."""
    item = models.AnswerItem(
        question_title="결론",
        question_text="결론은?",
        answer=None,
        citations=(),
        error="답변을 받지 못했습니다.",
    )

    displayed = answer_text.for_display(item)

    assert displayed.answer is None
    assert displayed.error == "답변을 받지 못했습니다."
