"""Outline 이 돌려주는 값과, 응답 본문을 도메인 값으로 바꾸는 일.

HTTP 호출도 상태 코드 판정도 모른다. ``services.outline`` 이 200 대
응답을 넘기면 이 모듈은 그 본문만 본다. 실패 안내 문구는
``outline_messages`` 에 있다.
"""

import dataclasses
import datetime

import httpx

from notebooklm_st.core import models


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


def parse_saved_document(
    config: OutlineConfig, response: httpx.Response
) -> SavedDocument:
    """``documents.create`` 응답 본문에서 문서를 꺼낸다.

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
        id=document_id, title=title, url=absolute(config.public_url, url)
    )


def parse_outline_document(response: httpx.Response) -> OutlineDocument:
    """``documents.info`` 응답 본문에서 문서를 꺼낸다.

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


def parse_listed_page(
    config: OutlineConfig, response: httpx.Response
) -> list[models.ListedDocument]:
    """``documents.list`` 응답 본문에서 문서들을 꺼낸다.

    한 항목이라도 기대한 키가 없거나 시각이 읽히지 않으면 페이지
    전체가 실패다. 그 항목만 조용히 빼면 다음 동기화가 그 행을 지운다.

    Args:
        config: 상대 URL 앞에 붙일 공개 주소를 가진 설정.
        response: ``documents.list`` 의 응답.

    Returns:
        이 페이지의 문서들.

    Raises:
        OutlineError: JSON 이 아니거나 기대한 키가 없는 경우.
    """
    try:
        data = response.json()["data"]
        return [
            models.ListedDocument(
                id=str(item["id"]),
                title=str(item["title"]),
                url=absolute(config.public_url, str(item["url"])),
                created_at=to_local_time(str(item["createdAt"])),
                markdown=str(item["text"]),
            )
            for item in data
        ]
    except (ValueError, KeyError, TypeError) as error:
        raise OutlineError("Outline 의 응답을 이해하지 못했습니다.") from error


def to_local_time(stamp: str) -> str:
    """Outline 의 UTC 시각을 ``store.now()`` 와 같은 모양으로 바꾼다.

    ``2026-09-25T01:00:00.000Z`` → 로컬 시각의 ``2026-09-25T10:00:00``.
    접미가 없으면 UTC 로 본다.

    Args:
        stamp: ISO 8601 문자열.

    Returns:
        타임존 접미가 없는 초 단위 ISO 문자열.

    Raises:
        ValueError: 날짜로 읽히지 않는 경우.
    """
    moment = datetime.datetime.fromisoformat(stamp)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.UTC)
    return (
        moment.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    )


def absolute(public_url: str, url: str) -> str:
    """응답의 문서 URL 을 사람이 열 수 있는 절대 URL 로 만든다.

    Outline 은 ``/doc/제목-슬러그`` 같은 **상대 경로**를 준다(실측).
    그래서 앞에 붙이는 주소가 곧 사람이 나중에 누를 주소가 된다 —
    연결 주소가 아니라 **공개 주소**를 써야 하는 이유다.

    절대 URL 로 오는 배포판도 있을 수 있어 그때는 그대로 받는다.

    Args:
        public_url: 앞에 붙일 공개 주소.
        url: 응답이 준 URL. 상대 경로이거나 절대 URL 이다.

    Returns:
        사람이 브라우저에 붙여 넣을 수 있는 절대 URL.
    """
    if url.startswith(("http://", "https://")):
        return url
    return f"{public_url}/{url.lstrip('/')}"
