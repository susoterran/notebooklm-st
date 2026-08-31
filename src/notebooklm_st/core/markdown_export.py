"""이력 한 건을 마크다운 문서와 파일명으로 옮기는 순수 함수들.

화면이 다운로드 버튼에 넘길 문자열을 만든다. 저장된 답변은 손대지
않으며, 인용을 걸러 내려받는 경우에도 걸러진 사본이 여기로 들어올
뿐이다(→ ``core.answer_text``).
"""

import re
from collections.abc import Sequence

from notebooklm_st.core import models

MAX_STEM_CHARS = 100
"""파일명에서 확장자를 뺀 부분의 최대 글자 수.

파일 시스템 한계는 보통 255 바이트인데 한글은 한 자가 UTF-8 로 3
바이트다. 100 자면 300 바이트에 확장자까지 얹혀 한계에 닿으므로 실제
한계보다 넉넉히 낮춰 잡는다.
"""

_FORBIDDEN = re.compile(r'[<>:"/\|?*\x00-\x1f]')
"""윈도우가 파일명에 허용하지 않는 문자와 제어 문자.

유튜브 제목에는 ``:`` 와 ``?`` 가 흔해서 거르지 않으면 저장이
실패한다.
"""

_REPEATED_SPACE = re.compile(r"\s+")


def to_markdown(
    summary: models.RunSummary, items: Sequence[models.AnswerItem]
) -> str:
    """실행 하나를 마크다운 문서 한 장으로 만든다.

    Args:
        summary: 머리글과 출처에 쓸 실행 요약.
        items: 문서에 담을 답변 목록. 화면이 그리는 것과 같은 목록을
            받으므로 인용을 숨긴 상태면 인용이 비어 들어온다.

    Returns:
        줄바꿈 하나로 끝나는 마크다운 문서.
    """
    blocks = [
        f"# {summary.title or summary.video_id}",
        f"- 출처: {summary.url}\n- 실행: {summary.created_at}",
    ]
    blocks.extend(_item_block(item) for item in items)
    return "\n\n".join(blocks) + "\n"


def to_filename(title: str | None, video_id: str) -> str:
    """영상 제목을 내려받을 파일 이름으로 바꾼다.

    Args:
        title: 저장된 영상 제목. 없을 수 있다.
        video_id: 제목이 없거나 못 쓸 문자뿐일 때 대신 쓸 영상 ID.

    Returns:
        ``.md`` 로 끝나는 파일 이름.
    """
    stem = _sanitize(title or "") or _sanitize(video_id) or "run"
    return f"{stem}.md"


def _item_block(item: models.AnswerItem) -> str:
    """답변 하나를 제목, 질문 원문, 본문, 인용 순으로 적는다."""
    parts = [f"## {item.question_title}", _quote(item.question_text)]
    if item.error is not None:
        parts.append(f"**답변을 받지 못했습니다:** {item.error}")
        return "\n\n".join(parts)
    if item.answer:
        parts.append(item.answer)
    if item.citations:
        parts.append(f"### 인용 {len(item.citations)}건")
        parts.append(
            "\n".join(
                f"- **[{citation.number}]** {citation.text}"
                for citation in item.citations
            )
        )
    return "\n\n".join(parts)


def _quote(text: str) -> str:
    """질문 원문을 줄마다 인용 기호를 붙인 블록으로 만든다.

    화면은 원문을 접어 두지만 마크다운에는 접기가 없다. 인용 블록으로
    두면 답변 본문과 눈으로 갈린다.
    """
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _sanitize(text: str) -> str:
    """파일명으로 쓸 수 있게 다듬는다.

    못 쓰는 문자를 지우지 않고 공백으로 바꾼다. 지우면 ``어떻게?
    AI는`` 이 ``어떻게AI는`` 으로 붙어 읽기 어려워진다. 자르기는 겹친
    공백을 접은 뒤에 하고, 윈도우가 싫어하는 끝의 마침표와 공백은
    마지막에 뗀다.
    """
    cleaned = _REPEATED_SPACE.sub(" ", _FORBIDDEN.sub(" ", text)).strip()
    return cleaned[:MAX_STEM_CHARS].strip(" .")
