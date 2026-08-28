"""인증 상태 확인과 브라우저 재로그인.

라이브러리는 만료된 인증을 스스로 되살리려 여러 단계를 밟는다. 토큰
재추출과 쿠키 회전은 항상 시도하고, 저장된 브라우저 프로필로 무인
재인증을 하는 단계는 ``allow_headless`` 를 켜야 돈다(→ ``nlm``).

그 무인 단계마저 실패하면 남는 방법은 브라우저를 띄우는 로그인뿐이다.
그건 라이브러리 API 가 아니라 CLI 가 하므로 자식 프로세스로 부른다.
"""

import asyncio
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from typing import Protocol

from notebooklm_st.core import errors
from notebooklm_st.services import nlm

LOGIN_TIMEOUT = 420.0
"""로그인 자식 프로세스를 기다리는 최대 초.

CLI 자신도 브라우저를 300초까지만 기다리므로 보통은 그쪽이 먼저 끝난다.
이 값은 그게 동작하지 않았을 때를 위한 뒷받침이다.
"""


class ProcessLike(Protocol):
    """로그인 자식 프로세스의 최소 모양."""

    @property
    def stdout(self) -> Iterable[str] | None:
        """자식이 흘려 보내는 출력. 줄 단위로 읽는다."""
        ...

    def wait(self, timeout: float | None = None) -> int:
        """자식이 끝나기를 기다리고 종료 코드를 돌려준다."""
        ...

    def kill(self) -> None:
        """자식을 죽인다."""
        ...


PopenLike = Callable[..., ProcessLike]
ProbeLike = Callable[[], bool]
LoginLike = Callable[[Callable[[str], None]], bool]


def is_authenticated(
    client_factory: nlm.ClientFactory = nlm.default_client_factory,
) -> bool:
    """저장된 인증으로 클라이언트를 열 수 있는지 확인한다.

    여는 데 성공하면 라이브러리가 필요한 복구를 이미 마친 것이다.
    화면 문구로 바꿀 수 있는 예외만 "만료" 로 본다. 그 밖의 예외는
    인증 문제가 아니므로 삼키지 않고 그대로 올린다.

    Args:
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.

    Returns:
        인증이 살아 있으면 ``True``.
    """
    try:
        asyncio.run(_open_once(client_factory))
    except errors.MAPPED_ERRORS:
        return False
    return True


def run_login(
    on_progress: Callable[[str], None],
    timeout: float = LOGIN_TIMEOUT,
    popen: PopenLike = subprocess.Popen,
) -> bool:
    """브라우저 로그인을 자식 프로세스로 띄우고 끝날 때까지 지켜본다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은 이미
    notebooklm 이 설치된 venv 안에서 돌고 있다. 그래서 자기 인터프리터로
    CLI 모듈을 직접 부른다.

    터미널 입력은 필요 없다. CLI 가 로그인을 감지하면 스스로 저장하고
    끝나므로 표준 입력을 막아 둔다. 이미 로그인된 브라우저 프로필이
    남아 있으면 사용자가 아무것도 하지 않아도 통과한다.

    Args:
        on_progress: 자식의 출력 한 줄을 받는 콜백.
        timeout: 자식을 기다리는 최대 초.
        popen: 자식을 띄우는 함수. 테스트가 가짜를 넣을 수 있게 뚫어 둔다.

    Returns:
        로그인이 성공하면 ``True``.
    """
    process = popen(
        [sys.executable, "-m", "notebooklm", "login"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    deadline = time.monotonic() + timeout
    if process.stdout is not None:
        for line in process.stdout:
            on_progress(line.rstrip())
            if time.monotonic() > deadline:
                break
    remaining = max(deadline - time.monotonic(), 0.0)
    try:
        return process.wait(timeout=remaining) == 0
    except subprocess.TimeoutExpired:
        process.kill()
        return False


class AuthGate:
    """앱이 떠 있는 동안 자동 재인증을 한 번만 돌리기 위한 표식.

    Streamlit 은 세션마다 다른 스레드에서 스크립트를 돌리고, 스크립트는
    상호작용마다 처음부터 다시 실행된다. 표식이 없으면 재실행마다 인증을
    확인하게 되고, 잠금이 없으면 탭 두 개가 브라우저 로그인을 동시에
    띄운다.
    """

    def __init__(
        self,
        probe: ProbeLike = is_authenticated,
        login: LoginLike = run_login,
    ) -> None:
        """확인·로그인 함수를 받아 둔다.

        Args:
            probe: 인증이 살아 있는지 확인하는 함수.
            login: 브라우저 로그인을 돌리는 함수.
        """
        self._probe = probe
        self._login = login
        self._lock = threading.Lock()
        self._tried = False
        self._ok = False

    @property
    def ok(self) -> bool:
        """마지막 확인 결과. 한 번도 확인하지 않았으면 ``False``."""
        return self._ok

    @property
    def tried(self) -> bool:
        """자동 확인을 이미 돌렸는지 여부.

        화면이 이 값을 보고 진행 상자를 그릴지 정한다. 재실행마다 상자를
        다시 그리면 아무 일도 없는데 화면이 깜빡인다.
        """
        return self._tried

    def ensure(self, on_progress: Callable[[str], None]) -> bool:
        """처음 한 번만 인증을 확인하고, 만료됐으면 되살린다.

        확인 자체가 라이브러리의 무인 복구를 태우므로, 로그인까지 가는
        것은 그 무인 복구가 실패했을 때뿐이다.

        Args:
            on_progress: 로그인 진행 문구를 받는 콜백.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        with self._lock:
            if self._tried:
                return self._ok
            self._tried = True
            self._ok = self._probe() or self._login(on_progress)
            return self._ok

    def relogin(self, on_progress: Callable[[str], None]) -> bool:
        """사용자가 직접 요청한 재로그인을 돌린다.

        확인을 건너뛴다. 사용자가 눌렀다는 것은 이미 인증이 안 된다는
        뜻이므로 다시 확인해 봐야 시간만 든다.

        Args:
            on_progress: 로그인 진행 문구를 받는 콜백.

        Returns:
            로그인이 성공하면 ``True``.
        """
        with self._lock:
            self._tried = True
            self._ok = self._login(on_progress)
            return self._ok


async def _open_once(client_factory: nlm.ClientFactory) -> None:
    """클라이언트를 열었다 바로 닫는다.

    여는 순간 인증이 확인되므로 따로 요청을 보내지 않는다.

    Args:
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.
    """
    async with client_factory():
        return
