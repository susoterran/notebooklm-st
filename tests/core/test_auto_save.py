"""자동 저장 건너뛰기 판정 테스트."""

from notebooklm_st.core import auto_save, models


def make_result(
    title: str | None = "어떤 영상", error: str | None = None
) -> models.RunResult:
    """답변 둘짜리 결과를 만든다. 오류를 주면 둘째 답변이 실패한다."""
    return models.RunResult(
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title=title,
        items=(
            models.AnswerItem(
                question_title="핵심 주장",
                question_text="핵심 주장은?",
                answer="세 가지다.",
                citations=(),
                error=None,
            ),
            models.AnswerItem(
                question_title="요약",
                question_text="요약해줘",
                answer=None if error else "짧다.",
                citations=(),
                error=error,
            ),
        ),
    )


def test_a_clean_result_has_no_reason() -> None:
    """제목이 있고 답변이 모두 왔으면 올린다."""
    assert auto_save.skip_reason(make_result()) is None


def test_a_failed_answer_skips() -> None:
    """답변 하나라도 실패하면 건너뛴다."""
    result = make_result(error="응답이 비어 있습니다.")

    assert auto_save.skip_reason(result) == "답변 일부 실패"


def test_a_missing_title_skips() -> None:
    """제목이 없으면 건너뛴다."""
    assert auto_save.skip_reason(make_result(title=None)) == "제목 없음"


def test_a_blank_title_skips() -> None:
    """공백뿐인 제목은 없는 것과 같다."""
    assert auto_save.skip_reason(make_result(title=" \t\n")) == "제목 없음"


def test_a_failed_answer_wins_over_a_missing_title() -> None:
    """둘 다 걸리면 답변 일부 실패를 돌려준다."""
    result = make_result(title=None, error="응답이 비어 있습니다.")

    assert auto_save.skip_reason(result) == "답변 일부 실패"
