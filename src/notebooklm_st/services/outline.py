"""Outline(개인 위키)에 요약본 문서를 만든다.

Outline 을 아는 유일한 모듈이다. SQLite 도 Streamlit 도 모른다.
앱은 Outline 을 읽지 않는다 — 문서를 만들고 그 링크를 돌려주는 것이
이 모듈의 전부다.
"""

import dataclasses
import os
from collections.abc import Callable

import httpx

URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_URL"
TOKEN_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_TOKEN"
COLLECTION_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_COLLECTION"

CREATE_TIMEOUT = 20.0
"""문서 생성 요청에 주는 최대 초.

홈 LAN 안의 호출이라 넉넉하다. ``video_metadata`` 와 같은 값을 쓴다.
"""

_CREATE_PATH = "/api/documents.create"

PostLike = Callable[..., httpx.Response]
"""``httpx.post`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineConfig:
    """Outline 에 붙는 데 필요한 값 셋."""

    base_url: str
    token: str
    collection_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class SavedDocument:
    """Outline 에 만들어진 문서."""

    id: str
    title: str
    url: str
    """사람이 브라우저에 붙여 넣을 수 있는 절대 URL."""


class OutlineError(RuntimeError):
    """Outline 에 문서를 만들지 못했다.

    메시지는 사람이 화면에서 읽는 문장이다. 토큰은 절대 담지 않는다.
    """


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


def create_document(
    config: OutlineConfig,
    title: str,
    markdown: str,
    timeout: float = CREATE_TIMEOUT,
    poster: PostLike = httpx.post,
) -> SavedDocument:
    """컬렉션에 문서를 하나 만든다.

    ``publish`` 를 켠다. 끄면 초안으로 남아 컬렉션에서 보이지 않는다.

    Args:
        config: 주소·토큰·컬렉션 ID.
        title: 문서 제목. 사람이 저장 직전에 확인한 값이다.
        markdown: 문서 본문.
        timeout: 요청에 주는 최대 초.
        poster: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        만들어진 문서의 ID·제목·절대 URL.

    Raises:
        OutlineError: 연결이 안 되거나, 거부당했거나, 응답이 기대한
            모양이 아닌 경우.
    """
    response = poster(
        f"{config.base_url}{_CREATE_PATH}",
        headers={"Authorization": f"Bearer {config.token}"},
        json={
            "title": title,
            "text": markdown,
            "collectionId": config.collection_id,
            "publish": True,
        },
        timeout=timeout,
    )
    return _parse(config, response)


def _parse(config: OutlineConfig, response: httpx.Response) -> SavedDocument:
    """응답 본문에서 문서를 꺼낸다.

    Args:
        config: 상대 URL 앞에 붙일 주소를 가진 설정.
        response: ``documents.create`` 의 응답.

    Returns:
        만들어진 문서.

    Raises:
        OutlineError: JSON 이 아니거나 기대한 키가 없는 경우.
    """
    try:
        data = response.json()["data"]
        document_id = str(data["id"])
        title = str(data["title"])
        url = str(data["url"])
    except (ValueError, KeyError, TypeError) as error:
        raise OutlineError("Outline 의 응답을 이해하지 못했습니다.") from error
    return SavedDocument(
        id=document_id, title=title, url=_absolute(config.base_url, url)
    )


def _absolute(base_url: str, url: str) -> str:
    """응답의 문서 URL 을 절대 URL 로 만든다.

    ``/doc/제목-슬러그`` 같은 상대 경로로 오는 것을 전제하되, 절대
    URL 로 오는 배포판도 그대로 받는다(스펙 13.1).
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{base_url}/{url.lstrip('/')}"
