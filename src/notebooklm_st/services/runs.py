"""실행 상태를 담는 값 객체.

값을 락 안에서 보관하고 고치는 일은 ``run_store`` 와 ``run_registry`` 가
한다.
"""

import dataclasses
from typing import Literal

from notebooklm_st.core import models

RunStatus = Literal["queued", "running", "done", "failed"]
MessageLevel = Literal["info", "error"]
SaveState = Literal["saved", "skipped", "failed"]

FINISHED: frozenset[RunStatus] = frozenset({"done", "failed"})
"""끝난 실행의 상태.

표의 지우기와 "끝난 항목 모두 지우기" 가 이것을 본다. 진행 중이 아닌
것을 ``!= "running"`` 으로 가리면 나중에 상태가 늘 때 함께 지워진다.
"""

PENDING: frozenset[RunStatus] = frozenset({"queued", "running"})
"""아직 끝나지 않은 실행의 상태. 같은 영상을 두 번 넣지 않는 데 쓴다."""


@dataclasses.dataclass(frozen=True, slots=True)
class SaveOutcome:
    """자동 저장 한 번의 결과."""

    state: SaveState
    message: str
    """표의 저장 칸에 그대로 쓰는 문구."""

    url: str | None
    """만들어진 문서 URL. 못 만들었으면 ``None``."""


@dataclasses.dataclass(slots=True)
class RunHandle:
    """대기 중이거나, 진행 중이거나, 끝난 실행 하나.

    다른 값 객체와 달리 frozen 이 아니다. 백그라운드 스레드가 상태를
    갱신하며, 동시 접근은 ``run_store.RunStore`` 의 락이 막는다.
    """

    run_id: str
    url: str
    video_id: str
    questions: tuple[models.Question, ...]
    """물어볼 질문들. 파이프라인에 넘길 수 있게 제목까지 쥔다."""

    auto_save: bool
    """넣는 순간 고정한 자동 저장 여부. 설정을 바꿔도 그대로다."""

    queued_at: str
    started_at: str | None
    """시작한 시각. 대기 중이면 ``None``."""

    status: RunStatus
    progress: list[str]
    result: models.RunResult | None
    save: SaveOutcome | None
    """자동 저장 결과. 자동 저장을 시도했을 때만 채운다."""

    error_message: str | None
    error_level: MessageLevel | None
    finished_at: str | None
    category_ids: tuple[int, ...] = ()
    """넣는 순간 고른 카테고리 ID. 이름은 이력과 문서에 쓸 때 읽는다.

    ID 로 쥐어, 대기 중에 이름이 바뀌어도 새 이름이 적힌다. 기본값이
    있어 맨 끝에 둔다.
    """
