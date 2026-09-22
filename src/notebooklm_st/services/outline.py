"""Outline(개인 위키)에 요약본 문서를 만든다.

Outline 을 아는 유일한 모듈이다. SQLite 도 Streamlit 도 모른다.
앱은 Outline 을 읽지 않는다 — 문서를 만들고 그 링크를 돌려주는 것이
이 모듈의 전부다.
"""

import dataclasses
import os

URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_URL"
TOKEN_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_TOKEN"
COLLECTION_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_COLLECTION"


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineConfig:
    """Outline 에 붙는 데 필요한 값 셋."""

    base_url: str
    token: str
    collection_id: str


def config_from_env() -> OutlineConfig | None:
    """환경변수에서 설정을 읽는다.

    셋 다 있을 때만 설정으로 친다. 토큰만 빠진 채로 호출해 401 을
    맞는 것보다, 처음부터 못 한다고 말하는 편이 진단하기 쉽다.

    Returns:
        설정. 하나라도 비어 있으면 ``None``.
    """
    base_url = os.environ.get(URL_ENV_VAR, "").strip()
    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    collection_id = os.environ.get(COLLECTION_ENV_VAR, "").strip()
    if not (base_url and token and collection_id):
        return None
    # 끝 슬래시는 여기서 한 번 뗀다. 붙이고 떼는 일이 호출 지점마다
    # 흩어지면 //api/... 같은 URL 이 언젠가 나온다.
    return OutlineConfig(
        base_url=base_url.rstrip("/"),
        token=token,
        collection_id=collection_id,
    )
