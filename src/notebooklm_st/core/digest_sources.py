"""정리 지시 앞에 붙일 소스 목록을 만드는 순수 함수.

NotebookLM 은 노트북의 소스에 번호를 매겨 주지 않는다. 정리 지시가
출처를 밝히라고 하면 모델이 번호를 스스로 지어 ``S3``·``소스3`` 같은
표기가 섞이고, 그 번호가 저장된 문서의 출처 목록과 맞는다는 보장도
없다. 그래서 고른 재료 순서대로 S 번호를 매긴 목록을 질의 맨 앞에
실어 번호를 못 박는다. 이 순서는 정리본 문서의 출처 목록 순번과
같다(→ ``digest_markdown``).
"""

from collections.abc import Sequence

from notebooklm_st.core import markdown_export

HEADER = "[소스 목록]"
"""소스 목록 덩어리의 머리 줄."""

INTRO = (
    "이 노트북의 소스 목록입니다. 소스를 가리킬 때는 아래 S 번호만 쓰고,"
    " 번호를 새로 매기거나 바꾸지 마세요. 소스 패널의 이름과 아래"
    " 이름이 조금 달라도 가장 비슷한 소스로 대응시키세요."
)
"""머리 줄 바로 뒤의 안내 문장.

노트북의 소스 이름에는 번호를 붙이지 않는다. 목록의 이름과 소스
패널의 이름이 어긋나는 경우는 이 문장의 마지막 요구가 받는다.
"""


def prepend(instruction: str, titles: Sequence[str]) -> str:
    """정리 지시 앞에 S 번호를 매긴 소스 목록을 붙인다.

    Args:
        instruction: 사람이 고른 정리 지시. 손대지 않는다.
        titles: 노트북에 넣은 순서대로의 소스 제목.

    Returns:
        소스 목록, 빈 줄, 정리 지시 순의 프롬프트.
    """
    lines = [HEADER, INTRO]
    lines.extend(
        f"- S{number}: {markdown_export.one_line(title)}"
        for number, title in enumerate(titles, start=1)
    )
    return "\n".join(lines) + "\n\n" + instruction
