"""답변 본문에서 인용 흔적을 걷어내는 순수 함수들.

결과물만 뽑아 쓰려는 사용자를 위해 화면이 표시 직전에 부른다. 저장된
원문은 절대 바꾸지 않는다 — 여기서 만든 문자열이 DB 로 되돌아가는
경로가 있으면 안 된다.
"""

import dataclasses
import re

from notebooklm_st.core import models

_TRAILING_RULE = re.compile(r"^\s*---\s*$")
"""후속 제안 블록을 여는 수평선.

NotebookLM 은 답변 끝에 다음 할 일을 제안하는 블록을 붙이는데 그
문구가 매번 다르다. 실측한 두 건은 각각 ``💡 **다음으로 무엇을 하기를
원하시나요?**`` 와 ``📊 분석된 …`` 로 시작했다. 고정 문구로 자르면
한쪽을 놓치므로, 둘 앞에 공통으로 놓인 수평선을 기준으로 삼는다.
"""

_CITATION_MARKER = re.compile(r"[ \t]*\[\d+(?:\s*[-,]\s*\d+)*\](?!\()")
"""본문에 박힌 인용 번호.

``[1]`` ``[2, 3]`` ``[1-3]`` 세 형태를 모두 받는다. 숫자·쉼표·하이픈만
받으므로 답변이 쓰는 ``[추론]`` 같은 표기는 건드리지 않고, 뒤에 ``(``
가 오면 마크다운 링크이므로 비켜 간다. 앞 공백까지 먹어야 ``기준
[1-3]`` 이 ``기준`` 으로 깔끔하게 남는다.
"""


def strip_trailing_block(text: str) -> str:
    """``---`` 로 시작하는 마지막 블록을 버린다.

    Args:
        text: 답변 본문.

    Returns:
        마지막 수평선부터 끝까지 걷어낸 본문. 수평선이 없거나 걷어낸
        결과가 비면 원본 그대로.
    """
    lines = text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if _TRAILING_RULE.match(lines[index]):
            kept = "\n".join(lines[:index]).rstrip()
            return kept or text
    return text


def strip_citation_markers(text: str) -> str:
    """본문에 박힌 인용 번호를 지운다.

    Args:
        text: 답변 본문.

    Returns:
        인용 번호를 지운 본문.
    """
    return _CITATION_MARKER.sub("", text)


def for_display(item: models.AnswerItem) -> models.AnswerItem:
    """인용 흔적을 걷어낸 표시용 사본을 만든다.

    ``citations`` 를 비우는 것만으로 인용 상자까지 사라진다. 답변 카드가
    빈 인용을 그리지 않기 때문이다(→ ``components.answer_view``).

    Args:
        item: 저장된 그대로의 답변 항목.

    Returns:
        본문을 거르고 인용을 비운 사본. 본문이 없는 실패 항목은 인용만
        비운다.
    """
    answer = item.answer
    if answer is not None:
        answer = strip_citation_markers(strip_trailing_block(answer))
    return dataclasses.replace(item, answer=answer, citations=())
