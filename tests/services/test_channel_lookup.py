"""채널 URL 해석 테스트 — 실제 yt-dlp 를 부르지 않는다."""

import json
import subprocess

from notebooklm_st.services import channel_lookup

CHANNEL_ID = "UCsBjURrPoezykLs9EqgamOA"
HANDLE_URL = "https://www.youtube.com/@Fireship"

PAYLOAD = {
    "_type": "playlist",
    "channel": "Fireship",
    "channel_id": CHANNEL_ID,
    "channel_url": f"https://www.youtube.com/channel/{CHANNEL_ID}",
    "entries": [{"id": "TbkUKCm3CHQ"}],
}


def completed(returncode=0, stdout=None, stderr=b""):
    """가짜 자식 프로세스 결과를 만든다."""
    if stdout is None:
        stdout = json.dumps(PAYLOAD).encode("utf-8")
    return subprocess.CompletedProcess(
        args=["yt-dlp"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def runner_for(result):
    """준비된 결과를 돌려주는 가짜 runner 를 만든다."""

    def runner(argv, **kwargs):
        """호출을 무시하고 준비된 결과만 돌려준다."""
        return result

    return runner


def test_lookup_reads_the_channel_id_and_title():
    """채널 ID 와 이름을 읽는다."""
    found = channel_lookup.lookup(HANDLE_URL, runner=runner_for(completed()))

    assert found.error is None
    assert found.channel_id == CHANNEL_ID
    assert found.title == "Fireship"
    assert found.url == f"https://www.youtube.com/channel/{CHANNEL_ID}"


def test_lookup_asks_for_only_one_entry():
    """목록은 한 건만 받는다. 쓰는 것은 최상위 필드뿐이다."""
    seen = {}

    def runner(argv, **kwargs):
        """넘어온 명령줄을 기록한다."""
        seen["argv"] = argv
        return completed()

    channel_lookup.lookup(HANDLE_URL, runner=runner)

    assert "--flat-playlist" in seen["argv"]
    assert "--playlist-end" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--playlist-end") + 1] == "1"
    assert seen["argv"][-1] == HANDLE_URL


def test_a_dash_leading_url_is_not_read_as_an_option():
    """`-` 로 시작하는 입력이 yt-dlp 옵션으로 해석되지 않는다.

    `--` 구분자가 없으면 `--batch-file=...` 같은 입력이 옵션으로 먹혀
    로컬 파일 내용이 실패 사유에 섞여 화면으로 새어 나온다.
    """
    seen = {}

    def runner(argv, **kwargs):
        """넘어온 명령줄을 기록한다."""
        seen["argv"] = argv
        return completed()

    channel_lookup.lookup("--batch-file=/etc/hostname", runner=runner)

    argv = seen["argv"]
    assert argv[-1] == "--batch-file=/etc/hostname"
    assert argv[-2] == "--"


def test_a_url_without_a_channel_is_refused():
    """채널 ID 가 없으면 채널 URL 이 아니라고 말한다."""
    payload = json.dumps({"_type": "video", "id": "abc"}).encode("utf-8")

    found = channel_lookup.lookup(
        "https://youtu.be/dQw4w9WgXcQ",
        runner=runner_for(completed(stdout=payload)),
    )

    assert found.channel_id is None
    assert "채널 URL 이 아닙니다" in (found.error or "")


def test_a_blank_url_is_refused_without_running_yt_dlp():
    """빈 URL 이면 자식 프로세스를 부르지 않는다."""
    called = []

    def runner(argv, **kwargs):
        """불리면 기록을 남긴다."""
        called.append(True)
        return completed()

    found = channel_lookup.lookup("   ", runner=runner)

    assert called == []
    assert found.error is not None


def test_a_failing_exit_code_is_reported():
    """0 이 아닌 종료 코드는 자식의 출력을 사유로 옮긴다."""
    found = channel_lookup.lookup(
        HANDLE_URL,
        runner=runner_for(
            completed(returncode=1, stdout=b"", stderr=b"ERROR: not found")
        ),
    )

    assert found.channel_id is None
    assert "not found" in (found.error or "")


def test_a_timeout_is_reported():
    """타임아웃은 사유로 돌아온다."""

    def runner(argv, **kwargs):
        """타임아웃을 만든다."""
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=30.0)

    found = channel_lookup.lookup(HANDLE_URL, runner=runner)

    assert "넘겨 중단했습니다" in (found.error or "")


def test_a_missing_executable_is_reported():
    """yt-dlp 를 실행할 수 없으면 사유로 돌아온다."""

    def runner(argv, **kwargs):
        """실행 실패를 만든다."""
        raise OSError("실행 파일 없음")

    found = channel_lookup.lookup(HANDLE_URL, runner=runner)

    assert "실행하지 못했습니다" in (found.error or "")


def test_broken_json_is_reported():
    """출력이 JSON 이 아니면 사유로 돌아온다."""
    found = channel_lookup.lookup(
        HANDLE_URL, runner=runner_for(completed(stdout=b"not json"))
    )

    assert "해석하지 못했습니다" in (found.error or "")
