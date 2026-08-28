"""notebooklm-py 예외를 화면에 보여 줄 문구로 바꾼다."""

import dataclasses
from typing import Literal

from notebooklm import exceptions

_LOGIN_HINT = (
    "인증이 만료되었습니다. 터미널에서 "
    "`uv run notebooklm login` 을 다시 실행하세요."
)


@dataclasses.dataclass(frozen=True, slots=True)
class UserMessage:
    """화면에 표시할 문구와 표시 수준."""

    text: str
    level: Literal["info", "error"]


def to_message(error: exceptions.NotebookLMError) -> UserMessage:
    """라이브러리 예외를 화면 문구로 바꾼다.

    자막이 없는 영상은 도구의 오류가 아니라 그 영상의 성질이므로
    ``info`` 수준으로 돌려준다. 나머지는 ``error`` 다.

    검사 순서는 좁은 예외부터 둔다. 지금은 분기 2가
    ``SourceAddError | SourceProcessingError`` 를 구체적으로 검사하므로
    ``SourceTimeoutError`` 가 잘못 걸리지 않지만, 나중에 넓은
    ``SourceError`` 검사를 넣는다면 반드시 그 뒤에 와야 한다.

    Args:
        error: notebooklm-py 가 올린 예외.

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
    if isinstance(
        error,
        exceptions.AuthError | exceptions.HeadlessLoginRequiredError,
    ):
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
