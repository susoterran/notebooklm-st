"""자동 저장을 건너뛸지 가르는 순수 함수.

러너가 답변을 받자마자 Outline 에 올리기 전에 부른다. 사람이 고쳐야
할 결과는 올리지 않고 이력에 미저장으로 남긴다. 영상 ID 를 제목으로
올리거나 빈 답변을 위키에 남기지 않으려는 것이다.

Outline 설정이 없는 경우는 여기서 알 수 없으므로 러너가 따로 본다.
"""

from notebooklm_st.core import models


def skip_reason(result: models.RunResult) -> str | None:
    """자동 저장을 건너뛸 이유를 고른다.

    답변 일부 실패를 제목 없음보다 먼저 본다. 둘 다 걸리면 앞의 것을
    돌려준다.

    Args:
        result: 파이프라인이 돌려준 결과.

    Returns:
        저장 칸에 ``미저장 · `` 뒤로 붙일 이유. 올려도 되면 ``None``.
    """
    if any(item.error is not None for item in result.items):
        return "답변 일부 실패"
    if result.title is None or not result.title.strip():
        return "제목 없음"
    return None
