"""영상 메타데이터를 yt-dlp 로 가져온다.

yt-dlp 를 아는 유일한 모듈이다. 파이썬 API 대신 자식 프로세스로
CLI 를 부른다 — ``YoutubeDL`` 에는 전체 시간을 막는 수단이 없어
느린 응답 하나가 요약 실행을 붙잡을 수 있다.

실패를 예외가 아니라 값으로 돌려준다. 호출자가 백그라운드
스레드라 예외가 새면 요약 실행 전체가 죽는다.
"""

import dataclasses
import datetime
import json
import subprocess
import sys
from collections.abc import Callable

from notebooklm_st.core import models, youtube

FETCH_TIMEOUT = 20.0
"""자식 프로세스에 주는 최대 초."""

DETAIL_LIMIT = 500
"""실패 사유로 남길 최대 글자 수."""

RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]
"""``subprocess.run`` 자리에 넣을 수 있는 것.

키워드 인자가 많아 Protocol 로 적으면 길기만 하다.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class MetadataResult:
    """메타데이터 조회 결과.

    ``metadata`` 와 ``error`` 중 하나만 채워진다.
    """

    metadata: models.VideoMetadata | None
    error: str | None


def fetch(
    url: str,
    runner: RunnerLike = subprocess.run,
    timeout: float = FETCH_TIMEOUT,
    tz: datetime.tzinfo | None = None,
) -> MetadataResult:
    """영상 URL 에서 채널명과 업로드일자를 가져온다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은
    이미 yt-dlp 가 설치된 인터프리터 안에서 돌고 있다.

    Args:
        url: 조회할 영상 URL. 재생목록·추적 파라미터가 붙어 있어도
            영상 ID 만 뽑아 정규 URL 을 다시 짓는다.
        runner: 자식을 돌리는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.
        timeout: 자식에게 주는 최대 초.
        tz: 업로드 시각을 옮길 타임존. ``None`` 이면 시스템 로컬을
            쓴다. 컨테이너는 ``TZ=Asia/Seoul`` 로 돈다.

    Returns:
        메타데이터 또는 사람에게 보여 줄 실패 사유.
    """
    video_id = youtube.extract_video_id(url)
    if video_id is None:
        return MetadataResult(None, "영상 URL 이 아닙니다.")
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-playlist",
                "-J",
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return MetadataResult(
            None,
            f"영상 정보 조회가 {int(timeout)}초를 넘겨 중단했습니다.",
        )
    except OSError as error:
        return MetadataResult(None, f"yt-dlp 를 실행하지 못했습니다: {error}")
    if completed.returncode != 0:
        return MetadataResult(None, _failure_detail(completed.stderr))
    return _read(completed.stdout, tz)


def _read(stdout: bytes, tz: datetime.tzinfo | None) -> MetadataResult:
    """자식의 표준 출력에서 필요한 두 값을 꺼낸다."""
    try:
        info = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return MetadataResult(None, "yt-dlp 출력을 해석하지 못했습니다.")
    if not isinstance(info, dict):
        return MetadataResult(None, "yt-dlp 출력을 해석하지 못했습니다.")
    return MetadataResult(
        models.VideoMetadata(
            channel=_clean(info.get("channel")),
            upload_date=_to_date(
                info.get("timestamp"), info.get("upload_date"), tz
            ),
        ),
        None,
    )


def _clean(value: object) -> str | None:
    """문자열이면 앞뒤 공백을 떼고, 비면 ``None`` 으로 접는다.

    yt-dlp 는 값을 모를 때 키를 빼기도 하고 빈 문자열을 주기도
    한다. 한쪽으로 모아 둔다.
    """
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _to_date(
    timestamp: object, upload_date: object, tz: datetime.tzinfo | None
) -> str | None:
    """업로드 시각을 ``YYYY-MM-DD`` 로 만든다.

    ``timestamp`` 를 먼저 쓴다. yt-dlp 의 ``upload_date`` 는 UTC 라
    한국 시각 이른 아침에 올라온 영상이 전날로 찍히기 때문이다.
    """
    if isinstance(timestamp, int | float) and not isinstance(timestamp, bool):
        try:
            moment = datetime.datetime.fromtimestamp(timestamp, tz)
        except (OSError, OverflowError, ValueError):
            return None
        return moment.strftime("%Y-%m-%d")
    raw = _clean(upload_date)
    if raw is None or len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def _failure_detail(stderr: bytes, limit: int = DETAIL_LIMIT) -> str:
    """자식의 실패 출력을 화면에 쓸 짧은 문자열로 만든다.

    끝에서 자른다. 실제 원인은 마지막 줄에 있고 앞쪽은 경고로
    채워지는 일이 많다.
    """
    text = stderr.decode("utf-8", errors="replace").strip()
    if not text:
        return "자세한 사유를 알 수 없습니다."
    return text[-limit:]
