"""질의를 대기열에 넣고 백그라운드 워커가 하나씩 돌린다."""

import asyncio
import logging
import pathlib
import threading
import time
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

from notebooklm_st.core import errors, models, youtube
from notebooklm_st.services import (
    nlm,
    run_export,
    run_registry,
    run_steps,
    runs,
)

logger = logging.getLogger(__name__)

# Coroutine 의 Send/Throw 타입은 쓰지 않으므로 Any 로 둔다.
PipelineCallable = Callable[..., Coroutine[Any, Any, models.RunResult]]

_BLOCKED_POLL_SECONDS = 2.0
"""다른 일이 NotebookLM 을 쓰는 동안 워커가 다시 확인하는 간격."""

_threads: list[threading.Thread] = []


def enqueue(
    registry: run_registry.RunRegistry,
    url: str,
    questions: Sequence[models.Question],
    db_path: pathlib.Path,
    auto_save: bool,
    is_blocked: Callable[[], bool],
    pipeline: PipelineCallable = nlm.run_pipeline,
    category_ids: Sequence[int] = (),
) -> runs.RunHandle:
    """질의를 대기열 끝에 넣고, 도는 워커가 없으면 띄운다.

    즉시 반환하므로 호출한 화면이 파이프라인에 묶이지 않는다. 워커는
    하나뿐이라 NotebookLM 에는 넣은 순서대로 하나씩 붙는다. 진행
    상황과 결과는 레지스트리에서 조회한다. ``db_path``·``is_blocked``·
    ``pipeline`` 은 워커의 몫이라 도는 워커가 있으면 쓰이지 않는다.

    Args:
        registry: 실행과 대기열을 보관할 레지스트리.
        url: 질의할 영상 URL.
        questions: 물어볼 질문 목록.
        db_path: 완료 시 이력을 저장할 DB 경로.
        auto_save: 참이면 이력을 남긴 직후 Outline 에 올린다. 핸들에
            고정되므로 나중에 설정을 바꿔도 이 실행은 그대로다.
        is_blocked: 다른 일이 지금 NotebookLM 을 쓰고 있는가. 참인
            동안 워커가 시작을 미룬다. 화면은 정리본 레지스트리의
            ``is_running`` 을 넘긴다.
        pipeline: 실행할 파이프라인. 테스트가 가짜를 넣게 뚫어 둔다.
        category_ids: 고른 카테고리 ID. 핸들에 고정되고, 끝나면
            이력에 붙는다. 화면은 늘 넘긴다. 기본값은 테스트의 기존
            호출을 지킨다.

    Returns:
        넣은 실행의 핸들.
    """
    handle = registry.enqueue(
        url,
        youtube.extract_video_id(url) or "",
        tuple(questions),
        auto_save,
        tuple(category_ids),
    )
    if registry.acquire_worker():
        _start_worker(registry, db_path, is_blocked, pipeline)
    return handle


def resume(
    registry: run_registry.RunRegistry,
    db_path: pathlib.Path,
    is_blocked: Callable[[], bool],
    pipeline: PipelineCallable = nlm.run_pipeline,
) -> None:
    """멈춘 대기열을 풀고, 남은 항목이 있으면 워커를 띄운다.

    원인이 남아 있으면 다음 실행이 같은 이유로 실패하고 다시 멈춘다.

    Args:
        registry: 실행과 대기열을 보관할 레지스트리.
        db_path: 완료 시 이력을 저장할 DB 경로.
        is_blocked: ``enqueue`` 와 같다.
        pipeline: ``enqueue`` 와 같다.
    """
    if registry.resume():
        _start_worker(registry, db_path, is_blocked, pipeline)


def join_all(timeout: float = 5.0) -> None:
    """시작된 스레드가 모두 끝날 때까지 기다린다.

    테스트가 결과를 확인하기 전에 쓴다. 운영 코드는 부르지 않는다.

    Args:
        timeout: 스레드 하나당 최대 대기 초.
    """
    for thread in list(_threads):
        thread.join(timeout=timeout)
    _threads.clear()


def _start_worker(
    registry: run_registry.RunRegistry,
    db_path: pathlib.Path,
    is_blocked: Callable[[], bool],
    pipeline: PipelineCallable,
) -> None:
    """워커 스레드를 띄운다. 워커 자리를 잡은 호출자만 부른다."""
    # 워커마다 스레드가 하나씩 쌓이는 것을 막는다. 끝난 스레드는
    # join_all 이 아니라 여기서 걸러 내야 앱이 오래 떠 있어도 새지
    # 않는다. join_all 이 같은 리스트 객체를 참조하므로 재대입 대신
    # 슬라이스 대입으로 정리한다.
    _threads[:] = [thread for thread in _threads if thread.is_alive()]
    thread = threading.Thread(
        target=_drain,
        args=(registry, db_path, is_blocked, pipeline),
        daemon=True,
    )
    try:
        thread.start()
    except BaseException:
        # 못 뜬 스레드가 자리를 쥐고 있으면 다시는 워커가 뜨지 않는다.
        registry.release_worker()
        raise
    _threads.append(thread)


def _drain(
    registry: run_registry.RunRegistry,
    db_path: pathlib.Path,
    is_blocked: Callable[[], bool],
    pipeline: PipelineCallable,
) -> None:
    """워커 본체 — 대기열이 빌 때까지 하나씩 돌리고 끝난다.

    정상 종료에서 워커 자리를 비우는 곳은 ``claim_next`` 한 곳뿐이다.
    ``finally`` 에서 비우면, 이 워커가 ``None`` 을 받은 직후 들어온
    항목이 새 워커를 띄웠는데 옛 워커가 그 자리를 비워 워커가 하나 더
    뜰 수 있다. 그래서 예외로 끝날 때만 여기서 비운다. ``_work`` 는
    ``Exception`` 을 잡으므로, 여기로 오는 것은 ``BaseException`` 과
    ``is_blocked``·``claim_next`` 가 던진 예외다.
    """
    try:
        while True:
            while is_blocked():
                time.sleep(_BLOCKED_POLL_SECONDS)
            handle = registry.claim_next()
            if handle is None:
                return
            _work(registry, handle, db_path, pipeline)
    except BaseException:
        registry.release_worker()
        raise


def _work(
    registry: run_registry.RunRegistry,
    handle: runs.RunHandle,
    db_path: pathlib.Path,
    pipeline: PipelineCallable,
) -> None:
    """실행 하나 — 파이프라인을 돌리고 결과를 남긴다.

    이력을 먼저 남기고 자동 저장은 그 뒤에 한다. Outline 이 실패해도
    결과가 사라지지 않는다. 자동 저장이 어떻게 끝나든 실행은 done
    이다. 저장 결과는 표의 저장 칸이 따로 보여 준다.

    다음 실행도 같은 이유로 실패할 오류면 대기열을 멈춘다. 남은
    항목이 몇 초 간격으로 줄줄이 실패하지 않게 하고, 사람이 원인을
    푼 뒤 재개한다.

    Streamlit API 를 부르지 않는다. 콜백이 화면을 건드리면 사용자가
    페이지를 이동한 순간 이 스레드가 중단되기 때문이다.
    """
    run_id = handle.run_id

    def on_progress(message: str) -> None:
        """진행 문구를 레지스트리에 기록한다."""
        registry.append_progress(run_id, message)

    metadata = run_steps.fetch_metadata(registry, run_id, handle.url)

    try:
        result = asyncio.run(
            pipeline(handle.url, list(handle.questions), on_progress)
        )
    except errors.MAPPED_ERRORS as error:
        message = errors.to_message(error)
        logger.info("실행 %s 실패: %s", run_id, message.text)
        registry.fail(run_id, message.text, message.level)
        if errors.stops_queue(error):
            registry.pause(message.text)
        return
    except Exception as error:
        # 스레드 최상위에서만 넓게 잡는다. 여기서 예외가 새면 화면이
        # 영원히 "실행 중" 에 머물러 사용자가 원인을 알 수 없다.
        logger.exception("실행 %s 파이프라인 실패", run_id)
        registry.fail(
            run_id,
            f"예상 못 한 오류({type(error).__name__}): {error}",
            "error",
        )
        return
    except BaseException as error:
        # CancelledError 같은 BaseException 이 새면 핸들이 영원히
        # running 에 남는다. 상태만 남기고 그대로 재전파한다.
        logger.exception("실행 %s 비정상 종료", run_id)
        registry.fail(
            run_id,
            f"실행이 비정상 종료되었습니다({type(error).__name__})",
            "error",
        )
        raise

    history_id = run_steps.save_history(
        registry, run_id, result, metadata, handle.category_ids, db_path
    )
    if history_id is None:
        return
    save: runs.SaveOutcome | None = None
    if handle.auto_save:
        registry.append_progress(run_id, "Outline 에 저장 중")
        save = run_export.save_automatically(
            db_path, history_id, result, metadata
        )
    registry.finish(run_id, result, save)
