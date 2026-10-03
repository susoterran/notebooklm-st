"""정리본 소스에 S 번호를 매기는 순수 함수.

NotebookLM 은 노트북의 소스에 번호를 매겨 주지 않는다. 정리 지시가
출처를 밝히라고 하면 모델이 번호를 스스로 지어 ``S3``·``소스3`` 같은
표기가 섞이고, 그 번호가 저장된 문서의 출처 목록과 맞는다는 보장도
없다. 그래서 소스 이름 앞에 넣은 순서대로 S 번호를 붙이고, 정리
지시 앞에는 그 번호만 쓰라는 짧은 규칙을 붙인다. 이 순서는 정리본
문서의 출처 목록 순번과 같다(→ ``digest_markdown``).

규칙을 붙인 지시는 질의가 아니라 노트북의 맞춤 대화 설정이 된다
(→ ``services.nlm.run_digest_pipeline``). 제목 목록은 어디에도 싣지
않는다 — 번호는 소스 이름 자체에 있다.
"""

from notebooklm_st.core import markdown_export

HEADER = "[소스 목록]"
"""맞춤 대화 설정 맨 앞에 붙는 머리 줄."""

RULE = (
    "소스 패널의 각 소스 이름은 S1, S2… 번호로 시작합니다. 소스를"
    " 가리킬 때는 이 S 번호만 쓰고, 번호를 새로 매기거나 바꾸지"
    " 마세요."
)
"""머리 줄 바로 뒤의 규칙."""


def source_title(number: int, title: str) -> str:
    """노트북에 넣을 소스 이름을 만든다.

    번호를 이름 맨 앞에 둔다. 긴 이름이 잘려도 번호는 남는다.

    Args:
        number: 1 부터 매긴 S 번호. 넣는 순서다.
        title: 재료의 문서 제목.

    Returns:
        ``S<번호>: <한 줄로 접은 제목>``.
    """
    return f"S{number}: {markdown_export.one_line(title)}"


def prepend(instruction: str) -> str:
    """정리 지시 앞에 S 번호 규칙을 붙인다.

    Args:
        instruction: 사람이 고른 정리 지시. 손대지 않는다.

    Returns:
        머리 줄, 규칙, 빈 줄, 정리 지시 순의 글. 맞춤 대화 설정에 쓴다.
    """
    return f"{HEADER}\n{RULE}\n\n{instruction}"
