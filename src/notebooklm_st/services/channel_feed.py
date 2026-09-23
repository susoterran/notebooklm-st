"""채널 RSS 피드를 읽어 최근 영상을 돌려준다.

피드를 아는 유일한 모듈이다. SQLite 도 Streamlit 도 모른다.

**실패를 예외가 아니라 값으로 돌려준다.** 화면이 채널 여러 개를
차례로 읽으면서 하나의 실패로 멈추지 않아야 한다.

채널 목록(`yt-dlp --flat-playlist`)을 쓰지 않는 이유가 있다. 거기엔
업로드 시각이 오지 않아(``timestamp`` 가 ``None``) "기준일 이후" 를
판정할 수 없다. 피드는 그 값을 주고 비용이 HTTP 한 번이다.
"""

import dataclasses
import datetime
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable

import httpx

from notebooklm_st.core import models

FEED_URL = "https://www.youtube.com/feeds/videos.xml"
"""채널 피드 주소. 채널 ID 를 질의 파라미터로 붙인다."""

FETCH_TIMEOUT = 20.0
"""요청에 주는 최대 초. ``outline`` 과 같은 값이다."""

MAX_FEED_BYTES = 1 << 20
"""받아들일 피드 본문의 최대 크기.

``ElementTree`` 는 엔티티 확장 공격("billion laughs")에 취약하고, 이
모듈은 제3자가 주는 XML 을 읽는다. 실측한 피드가 24 KB 이므로 1 MiB
는 넉넉하다.
"""

_NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

GetLike = Callable[..., httpx.Response]
"""``httpx.get`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다(``outline`` 의
``PostLike`` 와 같은 이유).
"""


@dataclasses.dataclass(frozen=True, slots=True)
class FeedResult:
    """피드 조회 결과.

    ``error`` 가 있으면 ``entries`` 는 비어 있다. 항목이 없는 성공과
    실패를 구분해야 하므로 둘을 함께 담는다.
    """

    entries: tuple[models.FeedEntry, ...]
    error: str | None


def fetch(
    channel_id: str,
    getter: GetLike = httpx.get,
    timeout: float = FETCH_TIMEOUT,
) -> FeedResult:
    """채널의 최근 영상을 피드에서 읽는다.

    Args:
        channel_id: ``UC`` 로 시작하는 채널 ID.
        getter: 요청을 보내는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        timeout: 요청에 주는 최대 초.

    Returns:
        읽은 항목들 또는 사람에게 보여 줄 실패 사유. 피드는 최신
        15건까지만 준다.
    """
    try:
        response = getter(
            FEED_URL,
            params={"channel_id": channel_id},
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.HTTPError as error:
        return FeedResult((), f"피드를 가져오지 못했습니다: {error}")
    if response.status_code != 200:
        return FeedResult((), _status_message(response.status_code))
    if len(response.content) > MAX_FEED_BYTES:
        return FeedResult(
            (), f"피드가 너무 큽니다({len(response.content)} 바이트)."
        )
    return _read(response.text)


def _status_message(status: int) -> str:
    """상태 코드를 사람이 읽을 안내로 옮긴다.

    **404 와 5xx 를 가른다.** 404 는 이 채널에 피드가 없다는 뜻이라
    등록할 수 없고, 5xx 는 일시적일 수 있어 다시 시도하면 된다.
    실측에서 같은 URL 이 두 답을 다 냈다.

    Args:
        status: 응답 상태 코드.

    Returns:
        화면에 그대로 보여 줄 문장.
    """
    if status == 404:
        return (
            "이 채널에는 RSS 피드가 없습니다. 채널 URL 을 확인하세요."
            " 피드가 없는 채널은 등록할 수 없습니다."
        )
    if 500 <= status < 600:
        return (
            f"YouTube 가 일시적인 오류를 냈습니다(HTTP {status})."
            " 잠시 뒤 다시 시도하세요."
        )
    return f"YouTube 가 오류를 냈습니다(HTTP {status})."


def _read(text: str) -> FeedResult:
    """피드 본문을 항목들로 옮긴다.

    Args:
        text: 응답 본문.

    Returns:
        읽을 수 있던 항목들. 본문 자체가 깨졌으면 사유.
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return FeedResult((), "피드를 해석하지 못했습니다.")
    entries = []
    for element in root.findall("atom:entry", _NAMESPACES):
        entry = _to_entry(element)
        if entry is not None:
            entries.append(entry)
    return FeedResult(tuple(entries), None)


def _to_entry(element: ElementTree.Element) -> models.FeedEntry | None:
    """항목 하나를 값 객체로 옮긴다.

    **쓸 수 없는 항목은 건너뛴다.** 피드 하나의 흠집이 채널 전체를
    실패로 만들 이유가 없다.

    Args:
        element: ``atom:entry`` 요소.

    Returns:
        값 객체. 필드가 빠졌거나 시각에 타임존이 없으면 ``None``.
    """
    video_id = element.findtext("yt:videoId", namespaces=_NAMESPACES)
    title = element.findtext("atom:title", namespaces=_NAMESPACES)
    published = element.findtext("atom:published", namespaces=_NAMESPACES)
    if not video_id or not title or not published:
        return None
    try:
        moment = datetime.datetime.fromisoformat(published)
    except ValueError:
        return None
    if moment.tzinfo is None:
        # naive 와 aware 를 섞어 비교하면 TypeError 가 난다.
        return None
    return models.FeedEntry(video_id=video_id, title=title, published=moment)
