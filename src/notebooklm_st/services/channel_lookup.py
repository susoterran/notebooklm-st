"""채널 URL 을 채널 ID 로 해석한다.

**등록할 때 한 번만 부른다.** 그 뒤의 확인은 피드만 읽는다
(→ ``services.channel_feed``).

``video_metadata`` 와 같은 방식이다 — yt-dlp 를 자식 프로세스로
부르고, 실패를 예외가 아니라 값으로 돌려준다.
"""

import dataclasses
import json
import subprocess
import sys
from collections.abc import Callable

LOOKUP_TIMEOUT = 30.0
"""자식 프로세스에 주는 최대 초.

``video_metadata.FETCH_TIMEOUT``(20초)보다 길다. 채널 페이지 해석이
영상 하나보다 무겁고, 등록은 사람이 기다리는 한 번뿐이다.
"""

DETAIL_LIMIT = 500
"""실패 사유로 남길 최대 글자 수."""

RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]
"""``subprocess.run`` 자리에 넣을 수 있는 것."""


@dataclasses.dataclass(frozen=True, slots=True)
class LookupResult:
    """채널 해석 결과.

    ``error`` 가 있으면 나머지는 모두 ``None`` 이다.
    """

    channel_id: str | None
    title: str | None
    url: str | None
    error: str | None


def lookup(
    url: str,
    runner: RunnerLike = subprocess.run,
    timeout: float = LOOKUP_TIMEOUT,
) -> LookupResult:
    """채널 URL 에서 채널 ID 와 이름을 얻는다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은
    이미 yt-dlp 가 설치된 인터프리터 안에서 돌고 있다.

    Args:
        url: 채널 URL. ``@handle`` 과 ``/channel/UC…`` 를 받는다.
            ``/videos`` 를 붙이지 않아도 된다.
        runner: 자식을 돌리는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        timeout: 자식에게 주는 최대 초.

    Returns:
        채널 ID·이름·주소, 또는 사람에게 보여 줄 실패 사유.
    """
    cleaned = url.strip()
    if not cleaned:
        return _failed("채널 URL 을 입력하세요.")
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--flat-playlist",
                "-J",
                "--playlist-end",
                "1",
                cleaned,
            ],
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return _failed(f"채널 조회가 {int(timeout)}초를 넘겨 중단했습니다.")
    except OSError as error:
        return _failed(f"yt-dlp 를 실행하지 못했습니다: {error}")
    if completed.returncode != 0:
        return _failed(_detail(completed.stderr, completed.stdout))
    return _read(completed.stdout)


def _read(stdout: bytes) -> LookupResult:
    """자식의 출력에서 채널 세 값을 꺼낸다.

    ``channel_url`` 이 없으면 채널 ID 로 짓는다. 저장할 주소가 항상
    한 모양이어야 화면의 링크도 한 모양이 된다.

    Args:
        stdout: 자식의 표준 출력.

    Returns:
        해석 결과.
    """
    try:
        info = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _failed("yt-dlp 출력을 해석하지 못했습니다.")
    if not isinstance(info, dict):
        return _failed("yt-dlp 출력을 해석하지 못했습니다.")
    channel_id = info.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        return _failed(
            "채널 URL 이 아닙니다. 채널 주소를 넣으세요"
            "(예: https://www.youtube.com/@handle)."
        )
    title = info.get("channel")
    url = info.get("channel_url")
    return LookupResult(
        channel_id=channel_id,
        title=title if isinstance(title, str) and title else channel_id,
        url=url
        if isinstance(url, str) and url
        else f"https://www.youtube.com/channel/{channel_id}",
        error=None,
    )


def _failed(detail: str) -> LookupResult:
    """실패 결과를 만든다.

    Args:
        detail: 사람에게 보여 줄 사유.

    Returns:
        ``error`` 만 채운 결과.
    """
    return LookupResult(channel_id=None, title=None, url=None, error=detail)


def _detail(stderr: bytes, stdout: bytes) -> str:
    """자식의 실패 출력을 짧은 문자열로 만든다.

    Args:
        stderr: 자식의 표준 오류.
        stdout: 자식의 표준 출력. stderr 가 비었을 때 대신 쓴다.

    Returns:
        끝에서 ``DETAIL_LIMIT`` 글자. 아무 말도 없으면 대체 문구.
    """
    raw = stderr or stdout or b""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "채널을 확인하지 못했습니다."
    return text[-DETAIL_LIMIT:]
