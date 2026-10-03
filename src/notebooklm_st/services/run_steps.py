"""워커가 실행 하나를 돌릴 때 거치는 단계들.

영상 정보를 받는 단계와 결과를 이력에 남기는 단계를 담는다.
대기열과 스레드는 ``runner`` 가 맡는다. Streamlit API 를 부르지
않는다 — 워커 스레드에서 돈다.
"""

import logging
import pathlib

from notebooklm_st.core import models
from notebooklm_st.services import (
    run_history,
    run_registry,
    store,
    video_metadata,
)

logger = logging.getLogger(__name__)


def save_history(
    registry: run_registry.RunRegistry,
    run_id: str,
    result: models.RunResult,
    metadata: models.VideoMetadata | None,
    db_path: pathlib.Path,
) -> int | None:
    """결과를 이력에 남기고 이력 ID 를 돌려준다.

    실패하면 실행을 실패로 마감하고 ``None`` 을 돌려준다. 이력이 없으면
    올릴 것도 없으므로 자동 저장도 하지 않는다.
    """
    try:
        connection = store.connect(db_path)
        try:
            return run_history.save_run(connection, result, metadata)
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
        return None


def fetch_metadata(
    registry: run_registry.RunRegistry, run_id: str, url: str
) -> models.VideoMetadata | None:
    """영상 메타데이터를 조회하고 진행 문구를 남긴다.

    ``video_metadata.fetch`` 는 실패를 예외가 아니라 값으로 돌려주는
    계약이지만, 그 계약이 어디선가 깨지더라도 이 함수 밖으로 예외가
    새면 안 된다. 메타데이터는 부가물이라 요약 자체를 막을 이유가
    없는데, 예외가 새는 순간 화면이 영원히 "실행 중" 에 머무는 이
    앱 최악의 실패 모드로 이어진다. ``fetch`` 자신의 계약 뒤에 놓는
    마지막 방어선이라 이 넓은 catch 를 둔다.

    Args:
        registry: 진행 문구를 남길 레지스트리.
        run_id: 진행 문구를 붙일 실행 ID.
        url: 조회할 영상 URL.

    Returns:
        조회된 메타데이터. 못 가져왔으면 ``None``.
    """
    registry.append_progress(run_id, "영상 정보 확인 중")
    try:
        meta = video_metadata.fetch(url)
    except Exception:
        # 위 docstring 참고 — 여기서 예외가 새면 요약 자체가
        # 시작되지 못한 채 실행이 running 에 머문다.
        logger.exception("실행 %s 메타데이터 조회 중 예외", run_id)
        registry.append_progress(run_id, "영상 정보를 가져오지 못했습니다")
        return None
    if meta.error is not None:
        # 메타데이터는 부가물이다. 못 가져와도 요약은 끝까지 간다.
        logger.info("실행 %s 메타데이터 실패: %s", run_id, meta.error)
        registry.append_progress(
            run_id, f"영상 정보를 가져오지 못했습니다: {meta.error}"
        )
        return None
    return meta.metadata
