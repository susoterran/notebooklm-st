"""정리본 제목을 NotebookLM 에게 받아 오는 순수 함수들.

프롬프트에 붙일 지시와 그 지시를 되읽는 파싱이 **한 파일에 있다.**
둘이 갈라지면 한쪽만 고쳐도 조용히 어긋나고, 어긋난 자리는 제목이
날짜로 떨어지는 것으로만 드러나 알아차리기 어렵다.
"""

import re

from notebooklm_st.core import labels, markdown_export

DOCUMENT_PREFIX = "[정리]"
"""정리본 문서 제목 앞에 붙는 표시.

주제를 받지 못한 문서에도 붙인다. Outline 에서 정리본만 한 번에
찾는 손잡이가 이것이다.
"""

TOPIC_MAX_CHARS = 60
"""제목에 쓸 주제의 최대 글자 수.

지시가 30자를 요구하지만 모델이 그 말을 반드시 지키지는 않는다.
문서 목록이 읽히는 길이에서 자른다.
"""

DIRECTIVE = (
    "답변의 첫 줄에 `제목: ` 으로 시작하는 줄을 두고, 그 줄에 이 정리의"
    " 주제를 30자 이내의 한국어 명사구로 적어라. 마침표와 따옴표는 넣지"
    " 마라. 둘째 줄은 비우고, 셋째 줄부터 정리 본문을 써라."
)
"""사람이 고른 정리 지시 뒤에 붙일 제목 요구.

정리 지시 자체는 사람의 것이므로 건드리지 않고, 형식 요구만 뒤에
덧붙인다.
"""

# 전각 콜론은 모델이 실제로 쓰는 문자라 일부러 받는다.
_TITLE_LINE = re.compile(
    r"^[#>*_\s]*제목[*_\s]*[:：][*_\s]*(.*?)[*_\s]*$"  # noqa: RUF001
)
"""첫 줄에서 주제를 뽑는 패턴.

모델이 `**제목:**` 이나 `## 제목:` 처럼 꾸며 쓰는 것을 실패로 보지
않는다. 표시를 못 읽으면 제목이 날짜로 떨어지므로, 관용이 곧
성공률이다. 전각 콜론도 받는다.
"""

# 벗겨야 할 대상 문자 자체라 다른 글자로 바꿀 수 없다.
_QUOTES = "\"'“”‘’「」『』"  # noqa: RUF001
"""주제를 감싸 오면 벗길 따옴표들."""


def wrap(instruction: str) -> str:
    """정리 지시에 제목 요구를 덧붙인다.

    Args:
        instruction: 사람이 고른 정리 지시.

    Returns:
        지시 뒤에 빈 줄과 ``DIRECTIVE`` 가 붙은 프롬프트.
    """
    return f"{instruction}\n\n{DIRECTIVE}"


def split(text: str) -> tuple[str | None, str]:
    """답변을 주제와 본문으로 가른다.

    **본문을 잃지 않는 것이 제목을 얻는 것보다 앞선다.** 표시를 못
    읽거나 잘라낸 뒤 본문이 남지 않으면 받은 글을 그대로 돌려주고
    주제를 포기한다.

    Args:
        text: NotebookLM 이 돌려준 답변 전체.

    Returns:
        ``(주제, 본문)``. 주제를 읽지 못하면 첫 값이 ``None`` 이다.
    """
    lines = text.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index == len(lines):
        return None, text
    match = _TITLE_LINE.match(lines[index])
    if match is None:
        return None, text
    body = "\n".join(lines[index + 1 :]).strip()
    if not body:
        return None, text
    return match.group(1).strip(_QUOTES).strip() or None, body


def compose(topic: str | None, created_on: str) -> str:
    """Outline 문서 제목을 만든다.

    Args:
        topic: NotebookLM 이 지은 주제. 못 받았으면 ``None``.
        created_on: ``2026-09-23`` 형식의 날짜. 주제가 없을 때 쓴다.

    Returns:
        ``[정리] <주제>``. 주제가 없거나 공백뿐이면
        ``[정리] <날짜>``.
    """
    folded = markdown_export.one_line(topic) if topic else ""
    subject = labels.shorten(folded, TOPIC_MAX_CHARS) if folded else created_on
    return f"{DOCUMENT_PREFIX} {subject}"
