"""YouTube URL 파싱 테스트."""

import pytest

from notebooklm_st.core import youtube

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "https://www.youtube.com/v/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?list=PL1&v=dQw4w9WgXcQ&t=42",
        "  https://youtu.be/dQw4w9WgXcQ  ",
        "https://youtu.be/dQw4w9WgXcQ?t=30",
    ],
)
def test_extract_video_id_accepts_single_video_urls(url: str) -> None:
    """다양한 형식의 유효한 YouTube URL 에서 영상 ID 를 추출한다."""
    assert youtube.extract_video_id(url) == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "not a url",
        "https://evil.com/youtube.com/watch?v=dQw4w9WgXcQ",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=PL1",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/@channel",
        "https://youtu.be/",
        "ftp://www.youtube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_extract_video_id_rejects_other_urls(url: str) -> None:
    """유효하지 않은 URL 들은 None 을 반환한다."""
    assert youtube.extract_video_id(url) is None


def test_is_valid_mirrors_extract() -> None:
    """is_valid 는 extract_video_id 의 성공 여부를 반영한다."""
    assert youtube.is_valid("https://youtu.be/dQw4w9WgXcQ") is True
    assert youtube.is_valid("https://example.com") is False
