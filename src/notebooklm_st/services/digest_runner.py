"""정리본 작성을 백그라운드 스레드에서 돌린다.

핸들·레지스트리·스레드를 한 파일에 둔다. 정리는 한 번에 한 건이라
``runs`` 와 ``runner`` 처럼 둘로 나눌 만큼 크지 않다.
"""

import dataclasses
import datetime
import logging
import threading
from collections.abc import Callable, Sequence
from typing import Literal

from notebooklm_st.core import errors, models
from notebooklm_st.services import digest, outline, runs

logger = logging.getLogger(__name__)

DigestStatus = Literal["running", "done", "failed"]

BuildCallable = Callable[..., models.DigestDraft]
"""``digest.build`` 자리에 넣을 수 있는 것.

테스트가 가짜를 넣는다.
"""

_threads: list[threading.Thread] = []


@dataclasses.dataclass(slots=True)
class DigestHandle:
    """진행 중이거나 끝난 정리 한 건.

    ``RunHandle`` 과 마찬가지로 frozen 이 아니다. 백그라운드 스레드가
    상태를 갱신하며, 동시 접근은 ``DigestRegistry`` 의 락이 막는다.
    """

    status: DigestStatus
    progress: list[str]
    draft: models.DigestDraft | None
    error_message: str | None
    error_level: runs.MessageLevel | None
    started_at: str
    finished_at: str | None


class DigestRegistry:
    """정리 한 건을 담는 보관소.

    **슬롯이 하나다.** 질의와 달리 정리는 동시에 여럿을 돌릴 이유가
    없고, 돌리면 NotebookLM 에 같은 쿠키로 동시 접근하게 된다.

    모든 공개 메서드가 락 안에서 동작한다.
    """

    def __init__(self) -> None:
        """빈 보관소를 만든다."""
        self._lock = threading.Lock()
        self._handle: DigestHandle | None = None

    def start(self) -> bool:
        """슬롯을 running 으로 잡는다.

        Returns:
            잡았으면 ``True``. 이미 돌고 있으면 ``False`` 이며 기존
            핸들은 그대로 둔다.
        """
        with self._lock:
            if self._handle is not None and self._handle.status == "running":
                return False
            self._handle = DigestHandle(
                status="running",
                progress=[],
                draft=None,
                error_message=None,
                error_level=None,
                started_at=_now(),
                finished_at=None,
            )
            return True

    def get(self) -> DigestHandle | None:
        """현재 핸들의 복사본을 돌려준다.

        Returns:
            복사본. 비어 있으면 ``None``.
        """
        with self._lock:
            if self._handle is None:
                return None
            return dataclasses.replace(
                self._handle, progress=list(self._handle.progress)
            )

    def is_running(self) -> bool:
        """정리가 진행 중인지 알려준다.

        Returns:
            진행 중이면 참. 다른 화면의 가드가 이것을 본다.
        """
        with self._lock:
            return self._handle is not None and self._handle.status == "running"

    def append_progress(self, message: str) -> None:
        """진행 문구를 덧붙인다. 슬롯이 비었으면 조용히 넘어간다.

        Args:
            message: 기록할 진행 문구.
        """
        with self._lock:
            if self._handle is not None:
                self._handle.progress.append(message)

    def finish(self, draft: models.DigestDraft) -> None:
        """정리를 완료로 표시한다.

        Args:
            draft: 만들어진 초안.
        """
        with self._lock:
            if self._handle is None:
                return
            self._handle.status = "done"
            self._handle.draft = draft
            self._handle.finished_at = _now()

    def fail(self, message: str, level: runs.MessageLevel) -> None:
        """정리를 실패로 표시한다.

        Args:
            message: 화면에 보여 줄 사용자 문구.
            level: 표시 수준.
        """
        with self._lock:
            if self._handle is None:
                return
            self._handle.status = "failed"
            self._handle.error_message = message
            self._handle.error_level = level
            self._handle.finished_at = _now()

    def clear(self) -> None:
        """슬롯을 비운다.

        사람이 초안을 저장했거나 버렸을 때 부른다.
        """
        with self._lock:
            self._handle = None


def start_digest(
    registry: DigestRegistry,
    config: outline.OutlineConfig,
    summaries: Sequence[models.RunSummary],
    instruction: str,
    build: BuildCallable = digest.build,
) -> bool:
    """정리본 작성을 백그라운드 스레드에서 시작한다.

    즉시 반환하므로 호출한 화면이 파이프라인에 묶이지 않는다.

    Args:
        registry: 상태를 보관할 레지스트리.
        config: Outline 주소·토큰.
        summaries: 재료가 될 실행들.
        instruction: 던질 정리 지시.
        build: 실행할 조립 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        시작했으면 ``True``. 이미 돌고 있으면 ``False``.
    """
    # 끝난 스레드를 여기서 걸러 낸다. 앱이 오래 떠 있어도 새지 않는다.
    _threads[:] = [thread for thread in _threads if thread.is_alive()]
    if not registry.start():
        return False
    thread = threading.Thread(
        target=_work,
        args=(registry, config, list(summaries), instruction, build),
        daemon=True,
    )
    _threads.append(thread)
    thread.start()
    return True


def join_all(timeout: float = 5.0) -> None:
    """시작된 스레드가 모두 끝날 때까지 기다린다.

    테스트가 결과를 확인하기 전에 쓴다. 운영 코드는 부르지 않는다.

    Args:
        timeout: 스레드 하나당 최대 대기 초.
    """
    for thread in list(_threads):
        thread.join(timeout=timeout)
    _threads.clear()


def _work(
    registry: DigestRegistry,
    config: outline.OutlineConfig,
    summaries: list[models.RunSummary],
    instruction: str,
    build: BuildCallable,
) -> None:
    """스레드 본체 — 초안을 만들고 결과를 남긴다.

    Streamlit API 를 부르지 않는다. 콜백이 화면을 건드리면 사용자가
    페이지를 이동한 순간 이 스레드가 중단된다.
    """

    def on_progress(message: str) -> None:
        """진행 문구를 레지스트리에 기록한다."""
        registry.append_progress(message)

    try:
        draft = build(config, summaries, instruction, on_progress)
    except outline.OutlineError as error:
        # 이미 사람이 읽을 문장이다. 한 겹 더 감싸면 말이 겹친다.
        logger.info("정리본 실패: %s", error)
        registry.fail(str(error), "error")
        return
    except errors.MAPPED_ERRORS as error:
        message = errors.to_message(error)
        logger.info("정리본 실패: %s", message.text)
        registry.fail(message.text, message.level)
        return
    except Exception as error:
        # 스레드 최상위에서만 넓게 잡는다. 여기서 예외가 새면 화면이
        # 영원히 "정리 중" 에 머물러 사용자가 원인을 알 수 없다.
        logger.exception("정리본 작성 실패")
        registry.fail(
            f"예상 못 한 오류({type(error).__name__}): {error}", "error"
        )
        return
    except BaseException as error:
        # CancelledError 같은 것이 새면 슬롯이 영원히 running 에 남아
        # 다음 정리를 막는다. 상태만 남기고 그대로 재전파한다.
        logger.exception("정리본 작성 비정상 종료")
        registry.fail(
            f"작성이 비정상 종료되었습니다({type(error).__name__})",
            "error",
        )
        raise

    registry.finish(draft)


def _now() -> str:
    """현재 로컬 시각을 초 단위 ISO 문자열로 돌려준다."""
    return datetime.datetime.now().isoformat(timespec="seconds")
