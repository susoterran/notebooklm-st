"""실제 계정으로 파이프라인을 한 번 돌려 보는 점검 스크립트.

사용법:
    uv run python scripts/smoke_check.py <YouTube URL>
"""

import asyncio
import sys
import time
from collections.abc import Callable

from notebooklm_st.core import models
from notebooklm_st.services import nlm

_QUESTIONS = (
    ("핵심 주장", "이 영상의 핵심 주장을 3가지로 정리해 주세요."),
    ("결론", "발표자의 결론은 무엇인가요?"),
)


def main() -> int:
    """점검을 실행하고 결과를 표준 출력에 찍는다.

    Returns:
        정상 종료면 0, 사용법이 틀리면 1.
    """
    if len(sys.argv) != 2:
        print("사용법: uv run python scripts/smoke_check.py <YouTube URL>")
        return 1

    url = sys.argv[1]
    questions = [
        models.Question(
            id=index,
            title=title,
            text=text,
            created_at="",
            updated_at="",
        )
        for index, (title, text) in enumerate(_QUESTIONS, start=1)
    ]

    started = time.monotonic()
    result = asyncio.run(nlm.run_pipeline(url, questions, _report(started)))
    print(f"\n총 소요 {time.monotonic() - started:.1f}초")

    for item in result.items:
        print("=" * 60)
        print("질문:", item.question_text)
        print("오류:", item.error)
        print("답변:", item.answer)
        print("인용:", len(item.citations), "건")
        for citation in item.citations:
            preview = citation.text[:120]
            print(
                f"  [{citation.number}] score={citation.score:.2f}"
                f" 길이={len(citation.text)}자"
            )
            print(f"      {preview}")
    return 0


def _report(started: float) -> Callable[[str], None]:
    """경과 시간을 함께 찍는 진행 콜백을 만든다."""

    def report(message: str) -> None:
        """진행 문구 앞에 경과 초를 붙여 찍는다."""
        print(f"[{time.monotonic() - started:6.1f}s] {message}")

    return report


if __name__ == "__main__":
    raise SystemExit(main())
