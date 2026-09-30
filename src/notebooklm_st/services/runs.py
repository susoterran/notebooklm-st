"""실행 상태를 담는 값 객체.

값을 락 안에서 보관하고 고치는 일은 ``run_store`` 와 ``run_registry`` 가
한다.
"""

import dataclasses
from typing import Literal

from notebooklm_st.core import models

RunStatus = Literal["running", "done", "failed"]
MessageLevel = Literal["info", "error"]
SaveState = Literal["saved", "skipped", "failed"]

FINISHED: frozenset[RunStatus] = frozenset({"done", "failed"})
"""끝난 실행의 상태.

표의 지우기와 "끝난 항목 모두 지우기" 가 이것을 본다. 진행 중이 아닌
것을 ``!= "running"`` 으로 가리면 나중에 상태가 늘 때 함께 지워진다.
"""


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
    """진행 중이거나 끝난 실행 하나.

    다른 값 객체와 달리 frozen 이 아니다. 백그라운드 스레드가 상태를
    갱신하며, 동시 접근은 ``run_store.RunStore`` 의 락이 막는다.
    """

    run_id: str
    url: str
    video_id: str
    question_texts: tuple[str, ...]
    auto_save: bool
    """넣는 순간 고정한 자동 저장 여부. 설정을 바꿔도 그대로다."""

    started_at: str
    status: RunStatus
    progress: list[str]
    result: models.RunResult | None
    save: SaveOutcome | None
    """자동 저장 결과. 자동 저장을 시도했을 때만 채운다."""

    error_message: str | None
    error_level: MessageLevel | None
    finished_at: str | None
