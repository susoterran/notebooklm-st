"""질의 실행을 백그라운드 스레드에서 돌린다."""

import asyncio
import logging
import pathlib
import threading
from collections.abc import Callable, Coroutine, Sequence
from typing import Any

from notebooklm import exceptions

from notebooklm_st.core import errors, models, youtube
from notebooklm_st.services import nlm, runs, store

logger = logging.getLogger(__name__)

# Coroutine 의 Send/Throw 타입은 쓰지 않으므로 Any 로 둔다.
PipelineCallable = Callable[..., Coroutine[Any, Any, models.RunResult]]

_threads: list[threading.Thread] = []


def start_run(
    registry: runs.RunRegistry,
    url: str,
    questions: Sequence[models.Question],
    db_path: pathlib.Path,
    pipeline: PipelineCallable = nlm.run_pipeline,
) -> runs.RunHandle:
    """질의 실행을 백그라운드 스레드에서 시작한다.

    즉시 반환하므로 호출한 화면이 파이프라인에 묶이지 않는다. 진행
    상황과 결과는 레지스트리에서 조회한다.

    Args:
        registry: 실행 상태를 보관할 레지스트리.
        url: 질의할 영상 URL.
        questions: 물어볼 질문 목록.
        db_path: 완료 시 이력을 저장할 DB 경로.
        pipeline: 실행할 파이프라인. 테스트가 가짜를 넣을 수 있게 뚫어 둔다.

    Returns:
        시작된 실행의 핸들.
    """
    # 실행마다 스레드가 하나씩 쌓이는 것을 막는다. 끝난 스레드는
    # join_all 이 아니라 여기서 걸러 내야 앱이 오래 떠 있어도 새지
    # 않는다. join_all 이 같은 리스트 객체를 참조하므로 재대입 대신
    # 슬라이스 대입으로 정리한다.
    _threads[:] = [thread for thread in _threads if thread.is_alive()]
    handle = registry.create(
        url,
        youtube.extract_video_id(url) or "",
        tuple(question.text for question in questions),
    )
    thread = threading.Thread(
        target=_work,
        args=(registry, handle.run_id, url, list(questions), db_path, pipeline),
        daemon=True,
    )
    _threads.append(thread)
    thread.start()
    return handle


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
    registry: runs.RunRegistry,
    run_id: str,
    url: str,
    questions: list[models.Question],
    db_path: pathlib.Path,
    pipeline: PipelineCallable,
) -> None:
    """스레드 본체 — 파이프라인을 돌리고 결과를 남긴다.

    Streamlit API 를 부르지 않는다. 콜백이 화면을 건드리면 사용자가
    페이지를 이동한 순간 이 스레드가 중단되기 때문이다.
    """

    def on_progress(message: str) -> None:
        """진행 문구를 레지스트리에 기록한다."""
        registry.append_progress(run_id, message)

    try:
        result = asyncio.run(pipeline(url, questions, on_progress))
    except exceptions.NotebookLMError as error:
        message = errors.to_message(error)
        logger.info("실행 %s 실패: %s", run_id, message.text)
        registry.fail(run_id, message.text, message.level)
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

    try:
        connection = store.connect(db_path)
        try:
            store.save_run(connection, result)
        finally:
            connection.close()
    except Exception as error:
        # 스레드 최상위에서만 넓게 잡는다. 이력 저장이 실패했는데
        # 상태를 남기지 않으면 화면이 영원히 "실행 중" 에 머문다.
        logger.exception("실행 %s 이력 저장 실패", run_id)
        registry.fail(
            run_id,
            "답변은 받았으나 이력 저장에 실패했습니다"
            f"({type(error).__name__}): {error}",
            "error",
        )
        return
    registry.finish(run_id, result)
