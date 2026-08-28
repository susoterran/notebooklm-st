"""라이브러리 예외 → 화면 문구 변환 테스트."""

from notebooklm import exceptions
from notebooklm._auth import extraction as _auth_extraction

from notebooklm_st.core import errors


def test_source_timeout_is_error() -> None:
    """인덱싱 시간 초과는 오류 수준으로 안내한다."""
    message = errors.to_message(
        exceptions.SourceTimeoutError("source-1", 120.0)
    )
    assert message.level == "error"
    assert "제한 시간" in message.text


def test_source_add_failure_is_info_not_error() -> None:
    """자막 없음은 정보 수준이다."""
    message = errors.to_message(
        exceptions.SourceAddError("https://youtu.be/dQw4w9WgXcQ")
    )
    assert message.level == "info"
    assert "자막" in message.text


def test_source_processing_failure_is_info() -> None:
    """처리 실패는 정보 수준이다."""
    message = errors.to_message(exceptions.SourceProcessingError("source-1"))
    assert message.level == "info"
    assert "자막" in message.text


def test_auth_error_tells_user_to_log_in_again() -> None:
    """인증 오류는 재로그인을 안내한다."""
    message = errors.to_message(exceptions.AuthError("expired"))
    assert message.level == "error"
    assert "notebooklm login" in message.text


def test_headless_login_required_tells_user_to_log_in_again() -> None:
    """헤드리스 로그인 필요 오류는 재로그인을 안내한다."""
    message = errors.to_message(
        exceptions.HeadlessLoginRequiredError("dead session")
    )
    assert message.level == "error"
    assert "notebooklm login" in message.text


def test_rate_limit_error() -> None:
    """요청 한도 오류를 안내한다."""
    message = errors.to_message(exceptions.RateLimitError("too many"))
    assert message.level == "error"
    assert "한도" in message.text


def test_notebook_limit_error_points_at_cleanup_page() -> None:
    """노트북 개수 상한 오류는 정리 페이지를 안내한다."""
    message = errors.to_message(exceptions.NotebookLimitError(100))
    assert message.level == "error"
    assert "정리" in message.text


def test_network_error() -> None:
    """네트워크 오류를 안내한다."""
    message = errors.to_message(exceptions.NetworkError("boom"))
    assert message.level == "error"
    assert "네트워크" in message.text


def test_rpc_timeout_is_treated_as_network_error() -> None:
    """RPC 시간 초과는 네트워크 오류로 취급한다."""
    message = errors.to_message(exceptions.RPCTimeoutError("slow"))
    assert message.level == "error"
    assert "네트워크" in message.text


def test_chat_error() -> None:
    """채팅 오류를 안내한다."""
    message = errors.to_message(exceptions.ChatError("bad response"))
    assert message.level == "error"
    assert "답변" in message.text


def test_unmapped_library_error_falls_back() -> None:
    """매핑되지 않은 오류는 기본 메시지로 돌아간다."""
    message = errors.to_message(exceptions.NotebookLMError("무슨 일이지"))
    assert message.level == "error"
    assert message.text


def test_login_redirect_tells_user_to_log_in_again() -> None:
    """라이브러리가 공개 예외로 감싸지 않는 로그인 리다이렉트도 안내한다.

    ``_LoginRedirectError`` 는 ``NotebookLMError`` 가 아니라 ``ValueError``
    라 기본 분기로 새기 쉽다. 실제로 새면 화면에 내부 클래스명과 구글
    URL 이 그대로 찍히므로 여기서 막는다.
    """
    error = _auth_extraction._LoginRedirectError(
        "Authentication expired or invalid. Final URL: https://accounts.google.com/x"
    )

    message = errors.to_message(error)

    assert message.level == "error"
    assert "notebooklm login" in message.text
