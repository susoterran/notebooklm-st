"""notebooklm-py 예외를 화면에 보여 줄 문구로 바꾼다."""

import dataclasses
from typing import Literal

from notebooklm import exceptions

# 토큰 조회가 구글 로그인 화면으로 튕기면 라이브러리는 이를 공개 예외가
# 아니라 private ``_LoginRedirectError`` (``ValueError`` 하위) 로 올린다.
# 라이브러리 자신의 CLI 도 이걸 "Unexpected error" 로 흘리므로, 우리가
# 직접 잡지 않으면 화면에 내부 클래스명과 구글 URL 이 그대로 노출된다.
# private 이라 위치가 바뀔 수 있으니 못 찾으면 매핑만 포기하고 앱은
# 그대로 뜨게 둔다.
try:
    from notebooklm._auth import extraction as _auth_extraction

    _LOGIN_REDIRECT_ERRORS: tuple[type[Exception], ...] = (
        _auth_extraction._LoginRedirectError,
    )
except (ImportError, AttributeError):  # pragma: no cover - 구조 변경 대비
    _LOGIN_REDIRECT_ERRORS = ()

MAPPED_ERRORS: tuple[type[Exception], ...] = (
    exceptions.NotebookLMError,
    *_LOGIN_REDIRECT_ERRORS,
)
"""``to_message`` 가 화면 문구로 바꿀 수 있는 예외들.

호출자는 이 튜플로 ``except`` 를 잡는다. 잡는 범위와 바꾸는 범위를 한
곳에서 같이 정의해 두면 둘이 어긋나지 않는다.
"""

_LOGIN_ERRORS: tuple[type[Exception], ...] = (
    exceptions.AuthError,
    exceptions.HeadlessLoginRequiredError,
    *_LOGIN_REDIRECT_ERRORS,
)
"""재로그인으로만 풀리는 예외들."""

_LOGIN_HINT = (
    "인증이 만료되었습니다. 터미널에서 "
    "`uv run notebooklm login` 을 다시 실행하세요."
)


@dataclasses.dataclass(frozen=True, slots=True)
class UserMessage:
    """화면에 표시할 문구와 표시 수준."""

    text: str
    level: Literal["info", "error"]


def to_message(error: Exception) -> UserMessage:
    """라이브러리 예외를 화면 문구로 바꾼다.

    자막이 없는 영상은 도구의 오류가 아니라 그 영상의 성질이므로
    ``info`` 수준으로 돌려준다. 나머지는 ``error`` 다.

    검사 순서는 좁은 예외부터 둔다. 지금은 분기 2가
    ``SourceAddError | SourceProcessingError`` 를 구체적으로 검사하므로
    ``SourceTimeoutError`` 가 잘못 걸리지 않지만, 나중에 넓은
    ``SourceError`` 검사를 넣는다면 반드시 그 뒤에 와야 한다.

    Args:
        error: notebooklm-py 가 올린 예외. 라이브러리가 공개 예외로
            감싸지 않고 흘리는 로그인 리다이렉트도 받는다.

    Returns:
        표시할 문구와 수준.
    """
    if isinstance(error, exceptions.SourceTimeoutError):
        return UserMessage(
            "자막 인덱싱이 제한 시간 안에 끝나지 않았습니다."
            " 잠시 후 다시 시도하세요.",
            "error",
        )
    if isinstance(
        error,
        exceptions.SourceAddError | exceptions.SourceProcessingError,
    ):
        return UserMessage(
            "자막이 없거나 소스로 쓸 수 없는 영상입니다.", "info"
        )
    if isinstance(error, _LOGIN_ERRORS):
        return UserMessage(_LOGIN_HINT, "error")
    if isinstance(error, exceptions.RateLimitError):
        return UserMessage(
            "요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.", "error"
        )
    if isinstance(error, exceptions.NotebookLimitError):
        return UserMessage(
            "노트북 개수 상한에 도달했습니다."
            " 정리 페이지에서 임시 노트북을 삭제하세요.",
            "error",
        )
    if isinstance(error, exceptions.NetworkError):
        return UserMessage("네트워크 오류가 발생했습니다.", "error")
    if isinstance(error, exceptions.ChatError):
        return UserMessage("답변을 받지 못했습니다.", "error")
    return UserMessage("NotebookLM 요청이 실패했습니다.", "error")
