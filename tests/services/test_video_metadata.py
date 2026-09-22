"""영상 메타데이터 조회 테스트."""

import datetime
import json
import subprocess
import sys

from notebooklm_st.services import video_metadata

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxxxx"
KST = datetime.timezone(datetime.timedelta(hours=9))


class FakeCompleted:
    """``subprocess.run`` 의 반환값을 흉내낸다."""

    def __init__(self, returncode, stdout=b"", stderr=b""):
        """종료 코드와 출력을 저장한다."""
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def fake_runner(result, calls):
    """호출 인자를 기록하고 준비된 결과를 돌려주는 러너를 만든다."""

    def run(args, **kwargs):
        """subprocess.run 을 대신한다."""
        calls.append((args, kwargs))
        if isinstance(result, Exception):
            raise result
        return result

    return run


def payload(**fields) -> bytes:
    """yt-dlp 가 찍을 JSON 한 덩어리를 만든다."""
    return json.dumps(fields).encode("utf-8")


def test_fetch_calls_yt_dlp_with_a_normalized_url() -> None:
    """자기 인터프리터로 부르고 재생목록 파라미터를 떼어 낸다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0, payload(channel="안될공학")), calls)

    result = video_metadata.fetch(URL, runner=runner)

    assert result.error is None
    args, kwargs = calls[0]
    assert args[0] == sys.executable
    assert args[1:] == [
        "-m",
        "yt_dlp",
        "--no-playlist",
        "-J",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    assert kwargs["capture_output"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL


def test_fetch_reads_the_channel() -> None:
    """Channel 필드를 그대로 가져온다."""
    runner = fake_runner(FakeCompleted(0, payload(channel="안될공학")), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is not None
    assert result.metadata.channel == "안될공학"


def test_fetch_converts_the_timestamp_to_the_given_timezone() -> None:
    """UTC 로는 전날인 시각이 KST 날짜로 나온다."""
    # 1789428600 = 2026-09-14 23:30 UTC = 2026-09-15 08:30 KST
    runner = fake_runner(
        FakeCompleted(0, payload(timestamp=1789428600, upload_date="20260914")),
        [],
    )

    result = video_metadata.fetch(URL, runner=runner, tz=KST)

    assert result.metadata is not None
    assert result.metadata.upload_date == "2026-09-15"


def test_fetch_falls_back_to_upload_date_without_a_timestamp() -> None:
    """Timestamp 가 없으면 upload_date 의 모양만 바꾼다."""
    runner = fake_runner(FakeCompleted(0, payload(upload_date="20260914")), [])

    result = video_metadata.fetch(URL, runner=runner, tz=KST)

    assert result.metadata is not None
    assert result.metadata.upload_date == "2026-09-14"


def test_fetch_folds_missing_fields_to_none() -> None:
    """빈 문자열과 없는 키를 모두 None 으로 접는다."""
    runner = fake_runner(FakeCompleted(0, payload(channel="")), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is not None
    assert result.metadata.channel is None
    assert result.metadata.upload_date is None


def test_fetch_reports_a_nonzero_exit() -> None:
    """종료 코드가 0 이 아니면 stderr 끝부분을 사유로 남긴다."""
    runner = fake_runner(FakeCompleted(1, b"", b"ERROR: Video unavailable"), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert result.error is not None
    assert "Video unavailable" in result.error


def test_fetch_reports_unparsable_output() -> None:
    """JSON 이 아니면 해석 실패로 남긴다."""
    runner = fake_runner(FakeCompleted(0, b"not json at all"), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert result.error is not None
    assert "해석하지 못했습니다" in result.error


def test_fetch_reports_a_timeout() -> None:
    """제한 시간을 넘기면 사유에 초가 들어간다."""
    runner = fake_runner(
        subprocess.TimeoutExpired(cmd="yt-dlp", timeout=20.0), []
    )

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert result.error is not None
    assert "20초" in result.error


def test_fetch_reports_a_launch_failure() -> None:
    """자식 프로세스를 띄우지 못해도 예외가 새지 않는다."""
    runner = fake_runner(FileNotFoundError("no such file"), [])

    result = video_metadata.fetch(URL, runner=runner)

    assert result.metadata is None
    assert result.error is not None
    assert "실행하지 못했습니다" in result.error


def test_fetch_rejects_a_non_video_url() -> None:
    """영상 URL 이 아니면 프로세스를 띄우지 않는다."""
    calls: list[tuple[list[str], dict[str, object]]] = []
    runner = fake_runner(FakeCompleted(0, payload()), calls)

    result = video_metadata.fetch("https://example.com/", runner=runner)

    assert result.metadata is None
    assert result.error == "영상 URL 이 아닙니다."
    assert calls == []
