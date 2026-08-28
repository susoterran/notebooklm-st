"""YouTube URL 검증과 영상 ID 추출."""

import re
import urllib.parse

_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)
_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/")


def extract_video_id(url: str) -> str | None:
    """단일 YouTube 영상 URL 에서 영상 ID 를 뽑는다.

    호스트 이름을 파싱해서 비교하므로 ``evil.com/youtube.com/...``
    같은 부분 문자열 위장은 통과하지 못한다. 재생목록 파라미터가
    붙어 있으면 무시하고 영상 ID 만 돌려준다.

    Args:
        url: 검사할 URL. 앞뒤 공백은 무시한다.

    Returns:
        11자리 영상 ID. 단일 영상 URL 이 아니면 ``None``.
    """
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    hostname = (parsed.hostname or "").lower()
    if hostname not in _ALLOWED_HOSTS:
        return None

    if hostname == "youtu.be":
        return _validated(parsed.path.lstrip("/").split("/")[0])

    if parsed.path == "/watch":
        values = urllib.parse.parse_qs(parsed.query).get("v", [])
        return _validated(values[0]) if values else None

    for prefix in _PATH_PREFIXES:
        if parsed.path.startswith(prefix):
            rest = parsed.path[len(prefix) :]
            return _validated(rest.split("/")[0])

    return None


def is_valid(url: str) -> bool:
    """URL 이 단일 YouTube 영상을 가리키는지 알려준다.

    Args:
        url: 검사할 URL.

    Returns:
        영상 ID 를 뽑아낼 수 있으면 참.
    """
    return extract_video_id(url) is not None


def _validated(candidate: str) -> str | None:
    """11자리 영상 ID 형식이면 그대로, 아니면 ``None`` 을 돌려준다."""
    return candidate if _VIDEO_ID_PATTERN.match(candidate) else None
