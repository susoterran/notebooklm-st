"""Outline(개인 위키)에 문서를 만들고, 다시 읽어 온다.

문서를 만들어 그 링크를 돌려주는 것과, 만든 문서를 다시 읽어 다른
기능의 재료로 내주는 것, 이 두 가지가 이 모듈의 전부다. 호출과 상태
코드 판정만 하고, 응답 본문 해석은 ``outline_parse``, 실패 안내
문구는 ``outline_messages`` 가 맡는다. ``OutlineConfig`` 등 값
객체는 ``outline_parse`` 의 정의를 이 이름으로 다시 내보낸다.
"""

import os
from collections.abc import Callable

import httpx

from notebooklm_st.core import sync_models
from notebooklm_st.services import outline_messages, outline_parse

OutlineConfig = outline_parse.OutlineConfig
SavedDocument = outline_parse.SavedDocument
OutlineDocument = outline_parse.OutlineDocument
OutlineError = outline_parse.OutlineError

URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_URL"
TOKEN_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_TOKEN"
COLLECTION_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_COLLECTION"
PUBLIC_URL_ENV_VAR = "NOTEBOOKLM_ST_OUTLINE_PUBLIC_URL"

CREATE_TIMEOUT = 20.0
"""문서 생성 요청에 주는 최대 초.

홈 LAN 안의 호출이라 넉넉하다. ``video_metadata`` 와 같은 값을 쓴다.
"""

FETCH_TIMEOUT = 20.0
"""문서 조회 요청에 주는 최대 초.

생성과 같은 값이다. 같은 서버에 같은 망으로 붙는다.
"""

_CREATE_PATH = "/api/documents.create"
_INFO_PATH = "/api/documents.info"
_LIST_PATH = "/api/documents.list"

LIST_PAGE_SIZE = 100
"""목록 한 페이지에 청할 문서 수."""

LIST_PAGE_LIMIT = 50
"""목록을 이어 부를 최대 페이지 수.

응답이 이상해 끝이 오지 않아도 무한히 돌지 않게 한다. 5,000 건이면
개인 위키의 요약본으로는 충분하다.
"""

PostLike = Callable[..., httpx.Response]
"""``httpx.post`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다.
"""


def config_from_env() -> OutlineConfig | None:
    """환경변수에서 설정을 읽는다.

    주소·토큰·컬렉션 셋 다 있을 때만 설정으로 친다. 토큰만 빠진 채로
    호출해 401 을 맞는 것보다, 처음부터 못 한다고 말하는 편이 진단하기
    쉽다. 공개 주소는 **선택**이다. 비어 있으면 연결 주소를 그대로
    쓴다 — 주소가 하나뿐인 흔한 구성에서는 설정이 늘지 않는다.

    Returns:
        설정. 필수 셋 중 하나라도 비어 있으면 ``None``.
    """
    base_url = os.environ.get(URL_ENV_VAR, "").strip()
    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    collection_id = os.environ.get(COLLECTION_ENV_VAR, "").strip()
    public_url = os.environ.get(PUBLIC_URL_ENV_VAR, "").strip()
    if not (base_url and token and collection_id):
        return None
    # 끝 슬래시는 여기서 한 번 뗀다. 붙이고 떼는 일이 호출 지점마다
    # 흩어지면 //api/... 같은 URL 이 언젠가 나온다.
    return OutlineConfig(
        base_url=base_url.rstrip("/"),
        public_url=(public_url or base_url).rstrip("/"),
        token=token,
        collection_id=collection_id,
    )


def _post(
    config: OutlineConfig,
    path: str,
    payload: dict[str, object],
    timeout: float,
    poster: PostLike,
    status_message: outline_messages.StatusMessage,
) -> httpx.Response:
    """요청을 보내고 연결·거부 실패를 사람이 읽을 문장으로 옮긴다.

    세 호출 경로(생성·조회·목록)가 겪는 앞부분이 같다. 차이는 주소·
    본문과 실패 안내뿐이다. httpx 의 원문 예외는 그대로 흘리지 않는다
    — ``httpx.InvalidURL`` 은 ``HTTPError`` 를 상속하지 않아 따로
    잡아야 한다.

    Args:
        config: 주소·토큰.
        path: 부를 엔드포인트 경로.
        payload: 요청 본문.
        timeout: 요청에 주는 최대 초.
        poster: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        status_message: 실패 상태 코드를 이 호출 경로의 안내로 옮기는
            함수.

    Returns:
        400 미만 상태의 응답. 본문은 아직 해석하지 않았다.

    Raises:
        OutlineError: 주소가 URL 로 읽히지 않거나, 연결이 안 되거나,
            거부당한 경우.
    """
    try:
        response = poster(
            f"{config.base_url}{path}",
            headers={"Authorization": f"Bearer {config.token}"},
            json=payload,
            timeout=timeout,
        )
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise OutlineError(
            f"Outline 에 연결하지 못했습니다({type(error).__name__})."
        ) from error
    if response.status_code >= 400:
        raise OutlineError(
            outline_messages.failure_message(
                response, config.token, response.status_code, status_message
            )
        )
    return response


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
        OutlineError: 주소가 URL 로 읽히지 않거나, 연결이 안 되거나,
            거부당했거나, 응답이 기대한 모양이 아닌 경우.
    """
    response = _post(
        config,
        _CREATE_PATH,
        {
            "title": title,
            "text": markdown,
            "collectionId": config.collection_id,
            "publish": True,
        },
        timeout,
        poster,
        outline_messages.create_status_message,
    )
    return outline_parse.parse_saved_document(config, response)


def fetch_document(
    config: OutlineConfig,
    document_id: str,
    timeout: float = FETCH_TIMEOUT,
    poster: PostLike = httpx.post,
) -> OutlineDocument:
    """문서 하나를 읽어 온다.

    **연결 주소로 나간다.** 공개 주소는 사람이 누를 링크를 만들 때만
    쓴다 — 여기서 공개 주소를 쓰면 컨테이너가 공인 도메인으로 되돌아
    나가지 못하는 망에서 앱이 자기 위키를 읽지 못한다.

    Args:
        config: 주소·토큰.
        document_id: 읽을 문서의 ID. ``runs.outline_id`` 에 적혀 있다.
        timeout: 요청에 주는 최대 초.
        poster: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        문서의 ID·제목·본문.

    Raises:
        OutlineError: 연결이 안 되거나, 거부당했거나, 응답이 기대한
            모양이 아닌 경우.
    """
    response = _post(
        config,
        _INFO_PATH,
        {"id": document_id},
        timeout,
        poster,
        outline_messages.read_status_message,
    )
    return outline_parse.parse_outline_document(response)


def list_documents(
    config: OutlineConfig,
    timeout: float = FETCH_TIMEOUT,
    poster: PostLike = httpx.post,
) -> list[sync_models.ListedDocument]:
    """컬렉션의 문서를 전부 읽어 온다.

    ``offset`` 을 ``LIST_PAGE_SIZE`` 씩 올리며 이어 부르고, 한 페이지가
    그보다 짧게 오면 끝으로 본다. 어느 페이지든 실패하면 지금까지
    모은 것을 버리고 실패한다 — 반쪽 목록으로 이력을 지우면 멀쩡한
    행이 사라진다. **연결 주소로 나간다.** 공개 주소는 문서 URL 을
    절대화할 때만 쓴다.

    Args:
        config: 주소·토큰·컬렉션 ID.
        timeout: 요청 하나에 주는 최대 초.
        poster: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        생성 시각 내림차순의 문서 목록.

    Raises:
        OutlineError: 연결이 안 되거나, 거부당했거나, 응답이 기대한
            모양이 아니거나, 페이지가 상한을 넘긴 경우.
    """
    documents: list[sync_models.ListedDocument] = []
    for page_index in range(LIST_PAGE_LIMIT):
        page = _list_page(config, page_index * LIST_PAGE_SIZE, timeout, poster)
        documents.extend(page)
        if len(page) < LIST_PAGE_SIZE:
            return documents
    raise OutlineError(
        "Outline 문서 목록이 너무 길거나 목록 응답이 이상합니다"
        f"(페이지 상한 {LIST_PAGE_LIMIT})."
    )


def _list_page(
    config: OutlineConfig,
    offset: int,
    timeout: float,
    poster: PostLike,
) -> list[sync_models.ListedDocument]:
    """목록 한 페이지를 읽는다.

    Args:
        config: 주소·토큰·컬렉션 ID.
        offset: 건너뛸 문서 수.
        timeout: 요청에 주는 최대 초.
        poster: 요청을 보내는 함수.

    Returns:
        이 페이지의 문서들.

    Raises:
        OutlineError: 연결·거부·응답 모양 문제.
    """
    response = _post(
        config,
        _LIST_PATH,
        {
            "filters": [
                {
                    "field": "collectionId",
                    "operator": "eq",
                    "value": config.collection_id,
                }
            ],
            "sort": "createdAt",
            "direction": "DESC",
            "limit": LIST_PAGE_SIZE,
            "offset": offset,
        },
        timeout,
        poster,
        outline_messages.list_status_message,
    )
    return outline_parse.parse_listed_page(config, response)
