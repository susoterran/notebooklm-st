"""Outline(개인 위키)에 문서를 만들고, 다시 읽어 온다.

Outline 을 아는 유일한 모듈이다. SQLite 도 Streamlit 도 모른다.
문서를 만들어 그 링크를 돌려주는 것과, 만든 문서를 다시 읽어
다른 기능의 재료로 내주는 것, 이 두 가지가 이 모듈의 전부다.
"""

import dataclasses
import os
from collections.abc import Callable

import httpx

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

DETAIL_LIMIT = 200
"""Outline 이 보낸 설명에서 화면에 옮길 최대 글자 수.

`st.error` 한 칸에 들어가야 한다. 더 길면 정작 우리가 쓴 안내 문장이
밀려 안 읽힌다.
"""

PostLike = Callable[..., httpx.Response]
"""``httpx.post`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다.
"""

StatusMessage = Callable[[int], str]
"""상태 코드를 안내 문장으로 옮기는 함수.

읽기와 쓰기가 서로 다른 것을 쓴다.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineConfig:
    """Outline 에 붙는 데 필요한 값들."""

    base_url: str
    """앱이 API 를 부를 주소."""

    public_url: str
    """사람이 브라우저로 열 주소. 링크를 만들 때만 쓴다.

    둘이 다를 수 있다. 컨테이너가 공인 도메인으로 되돌아 나가지 못하는
    망(NAT 헤어핀)에서는 앱이 호스트 주소로 붙어야 하는데, 그 주소에는
    사용자의 Outline 세션 쿠키가 없어 링크로는 쓸 수 없다. 실제 배포에서
    겪은 구성이다.
    """

    token: str
    collection_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class SavedDocument:
    """Outline 에 만들어진 문서."""

    id: str
    title: str
    url: str
    """사람이 브라우저에 붙여 넣을 수 있는 절대 URL."""


@dataclasses.dataclass(frozen=True, slots=True)
class OutlineDocument:
    """위키에서 읽어 온 문서 하나."""

    id: str
    title: str
    markdown: str
    """저장된 본문. Outline 은 CommonMark 로 보관한다."""


class OutlineError(RuntimeError):
    """Outline 호출이 실패했다.

    메시지는 사람이 화면에서 읽는 문장이다. 토큰은 절대 담지 않는다.
    """


def config_from_env() -> OutlineConfig | None:
    """환경변수에서 설정을 읽는다.

    주소·토큰·컬렉션 셋 다 있을 때만 설정으로 친다. 토큰만 빠진 채로
    호출해 401 을 맞는 것보다, 처음부터 못 한다고 말하는 편이 진단하기
    쉽다.

    공개 주소는 **선택**이다. 비어 있으면 연결 주소를 그대로 쓴다 —
    주소가 하나뿐인 흔한 구성에서는 설정이 늘지 않는다.

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
    try:
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
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        # httpx 의 원문 예외를 그대로 흘리지 않는다. 요청 정보가 따라
        # 나올 수 있고, 무엇보다 사람이 읽고 고칠 수 있는 문장이 아니다.
        # InvalidURL 은 HTTPError 를 상속하지 않아 따로 적어야 한다.
        # 자리표시자가 그대로 남은 첫 설정에서 실제로 나온다.
        raise OutlineError(
            f"Outline 에 연결하지 못했습니다({type(error).__name__})."
        ) from error
    if response.status_code >= 400:
        raise OutlineError(
            _failure_message(
                response,
                config.token,
                response.status_code,
                _status_message,
            )
        )
    return _parse(config, response)


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
    try:
        response = poster(
            f"{config.base_url}{_INFO_PATH}",
            headers={"Authorization": f"Bearer {config.token}"},
            json={"id": document_id},
            timeout=timeout,
        )
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        raise OutlineError(
            f"Outline 에 연결하지 못했습니다({type(error).__name__})."
        ) from error
    if response.status_code >= 400:
        raise OutlineError(
            _failure_message(
                response,
                config.token,
                response.status_code,
                _read_status_message,
            )
        )
    return _parse_document(response)


def _parse_document(response: httpx.Response) -> OutlineDocument:
    """응답 본문에서 문서를 꺼낸다.

    Args:
        response: ``documents.info`` 의 응답.

    Returns:
        읽어 온 문서.

    Raises:
        OutlineError: JSON 이 아니거나 기대한 키가 없는 경우.
    """
    try:
        data = response.json()["data"]
        document_id = str(data["id"])
        title = str(data["title"])
        markdown = str(data["text"])
    except (ValueError, KeyError, TypeError) as error:
        raise OutlineError("Outline 의 응답을 이해하지 못했습니다.") from error
    return OutlineDocument(id=document_id, title=title, markdown=markdown)


def _read_status_message(status: int) -> str:
    """읽기 실패를 "무엇부터 확인하라" 는 안내로 옮긴다.

    쓰기와 문구를 나눈다. ``_status_message`` 는 403 에서 컬렉션 ID 를
    먼저 의심하게 하는데, 그것은 ``documents.create`` 의 실측에서 나온
    순서다. 읽기에 그 안내를 내면 멀쩡한 컬렉션을 파게 된다.

    **401 에서 scope 를 먼저 짚는 것도 실측에서 나왔다.** scope 밖
    엔드포인트를 부르면 권한 오류(403)가 아니라 인증 오류(401)가
    오고, 본문은 ``Authentication required`` 다. Outline 의 현재
    소스는 이 경우 403 을 내므로 배포판에 따라 다르며, 그래서 401 과
    403 양쪽이 scope 를 짚는다. 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다 — 저장은 되는데 정리본만 안 되는 상황이 정확히
    이것이다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 401:
        return (
            "Outline 이 읽기 요청을 인증하지 못했습니다."
            " API 키 scope 에 documents.info 가 있는지 먼저"
            " 확인하세요 — 저장만 하던 키에는 없고, 그때 403 이"
            " 아니라 이 오류로 옵니다."
            " 그다음 토큰이 맞는지, 만료되지 않았는지 봅니다."
        )
    if status == 403:
        return (
            "Outline 이 문서 읽기를 거부했습니다."
            " API 키 scope 에 읽기 권한이 있는지 확인하세요 —"
            " 저장만 하던 키에는 없습니다."
        )
    if status == 404:
        return (
            "Outline 에서 문서를 찾지 못했습니다."
            " 위키에서 지워졌을 수 있습니다."
            " 그 이력을 선택에서 빼고 다시 시도하세요."
        )
    return f"Outline 이 오류를 냈습니다(HTTP {status})."


def _parse(config: OutlineConfig, response: httpx.Response) -> SavedDocument:
    """응답 본문에서 문서를 꺼낸다.

    Args:
        config: 상대 URL 앞에 붙일 공개 주소를 가진 설정.
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
        id=document_id, title=title, url=_absolute(config.public_url, url)
    )


def _absolute(public_url: str, url: str) -> str:
    """응답의 문서 URL 을 사람이 열 수 있는 절대 URL 로 만든다.

    Outline 은 ``/doc/제목-슬러그`` 같은 **상대 경로**를 준다(실측).
    그래서 앞에 붙이는 주소가 곧 사람이 나중에 누를 주소가 된다 —
    연결 주소가 아니라 **공개 주소**를 써야 하는 이유다.

    절대 URL 로 오는 배포판도 있을 수 있어 그때는 그대로 받는다.
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{public_url}/{url.lstrip('/')}"


def _failure_message(
    response: httpx.Response,
    token: str,
    status: int,
    status_message: StatusMessage,
) -> str:
    """실패 응답을 사람이 읽고 고칠 수 있는 한 문장으로 만든다.

    우리가 지은 안내 뒤에 **Outline 이 보낸 설명**을 붙인다. 설명을
    버리고 상태 코드만 남기면, 서버가 무엇이 틀렸는지 정확히 말해
    줬는데도 사람이 추측으로 파게 된다. 실제로 그렇게 됐다.

    Args:
        response: 오류 응답.
        token: 화면에 오르면 안 되는 값. 본문에 섞여 있으면 설명째
            버린다.
        status: HTTP 상태 코드.
        status_message: 이 호출 경로의 안내를 만드는 함수.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    detail = _detail(response, token)
    if not detail:
        return status_message(status)
    return f"{status_message(status)} Outline 이 말한 것: {detail}"


def _status_message(status: int) -> str:
    """오류 상태 코드를 "무엇부터 확인하라" 는 안내로 옮긴다.

    순서가 중요하다. 실측해 보니 **없는 컬렉션 ID** 가 404 가 아니라
    403 으로 온다 — Outline 이 "없다" 와 "권한 없다" 를 한 응답으로
    뭉치기 때문이다. 그래서 403 에서 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 400:
        return (
            "Outline 이 값을 받아들이지 않았습니다."
            " 컬렉션 ID 가 UUID 인지 확인하세요 — 컬렉션 이름은"
            " 받지 않습니다."
        )
    if status == 401:
        return (
            "Outline 이 API 토큰을 받아들이지 않았습니다."
            " 토큰이 맞는지, 만료되지 않았는지 확인하세요."
        )
    if status == 403:
        return (
            "Outline 이 요청을 거부했습니다."
            " 컬렉션 ID 가 이 토큰의 계정이 쓸 수 있는 컬렉션인지"
            " 먼저 확인하세요 — 없는 컬렉션도 이 오류로 옵니다."
            " 그다음 토큰 scope(documents.create)를 봅니다."
        )
    if status == 404:
        return "Outline 이 대상을 찾지 못했습니다. 주소를 확인하세요."
    return f"Outline 이 오류를 냈습니다(HTTP {status})."


def _detail(response: httpx.Response, token: str) -> str:
    """응답 본문에서 사람에게 보여 줄 한 줄을 뽑는다.

    토큰은 헤더에 있지 본문에 없으므로 본문을 보여 줘도 샐 것이 없다.
    그래도 서버가 무엇을 돌려주든 화면에 무엇이 실리는지는 우리가
    통제해야 하므로, 토큰이 섞여 있으면 설명째 버린다.

    Args:
        response: 오류 응답.
        token: 본문에 있으면 안 되는 값.

    Returns:
        한 줄로 접고 길이를 자른 설명. 읽을 것이 없으면 빈 문자열.
    """
    try:
        body = response.json()
        text = str(body.get("message") or body.get("error") or "")
    except (ValueError, AttributeError):
        text = response.text
    text = " ".join(text.split())[:DETAIL_LIMIT]
    if not text or token in text:
        return ""
    return text
