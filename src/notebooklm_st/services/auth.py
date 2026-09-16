"""인증 상태 확인과 브라우저 재로그인.

라이브러리는 만료된 인증을 스스로 되살리려 여러 단계를 밟는다. 토큰
재추출과 쿠키 회전은 항상 시도하고, 저장된 브라우저 프로필로 무인
재인증을 하는 단계는 ``allow_headless`` 를 켜야 돈다(→ ``nlm``).

그 무인 단계마저 실패하면 남는 방법은 브라우저를 띄우는 로그인뿐이다.
그건 라이브러리 API 가 아니라 CLI 가 하므로 자식 프로세스로 부른다.
"""

import asyncio
import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from typing import Protocol

from notebooklm_st.core import errors
from notebooklm_st.services import nlm

logger = logging.getLogger(__name__)

LOGIN_TIMEOUT = 420.0
"""로그인 자식 프로세스를 기다리는 최대 초.

CLI 자신도 브라우저를 300초까지만 기다리므로 보통은 그쪽이 먼저 끝난다.
이 값은 그게 동작하지 않았을 때를 위한 뒷받침이다.
"""

CHECK_NOTICE = "인증 상태 확인 중"
"""확인 단계가 화면에 남기는 문구.

확인은 콜백을 부르지 않으므로 이 줄이 없으면 상자가 빈 채로 몇 초 동안
멈춰 있고, 실패로 끝나면 단서가 한 줄도 남지 않는다.
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

    실패는 반드시 한 줄을 남긴다. 자식이 아무 말도 못 하고 죽으면
    화면에 빈 상자와 "실패" 만 남아, 무엇이 잘못됐는지 알아낼 단서가
    아무것도 없다.

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
        code = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        process.kill()
        on_progress(f"로그인이 {int(timeout)}초 안에 끝나지 않아 멈췄습니다.")
        return False
    if code != 0:
        on_progress(f"로그인 CLI 가 종료 코드 {code} 로 끝났습니다.")
    return code == 0


class AuthGate:
    """앱이 떠 있는 동안 인증 확인을 한 번만 돌리기 위한 표식.

    Streamlit 은 세션마다 다른 스레드에서 스크립트를 돌리고, 스크립트는
    상호작용마다 처음부터 다시 실행된다. 표식이 없으면 재실행마다
    느린 네트워크 확인이 돌고, 잠금이 없으면 탭 두 개가 동시에 확인을
    시작한다.
    """

    def __init__(self, probe: ProbeLike = is_authenticated) -> None:
        """확인 함수를 받아 둔다.

        Args:
            probe: 인증이 살아 있는지 확인하는 함수.
        """
        self._probe = probe
        self._lock = threading.Lock()
        self._tried = False
        self._ok = False
        self._probe_error: Exception | None = None

    @property
    def ok(self) -> bool:
        """마지막 확인 결과. 한 번도 확인하지 않았으면 ``False``."""
        return self._ok

    @property
    def tried(self) -> bool:
        """자동 확인을 이미 돌렸는지 여부.

        화면이 이 값을 보고 진행 표시를 그릴지 정한다. 재실행마다 다시
        그리면 아무 일도 없는데 화면이 깜빡인다.
        """
        return self._tried

    @property
    def probe_error(self) -> Exception | None:
        """확인 **자체**가 실패했을 때 그 예외.

        만료(``ok`` 가 ``False``)와 구분된다. 만료는 사람이 재시드로
        풀 수 있지만, 확인 불가는 라이브러리 구조 변경 같은 다른
        원인이라 안내가 달라야 한다. 보관해 두지 않으면 재실행 뒤
        ``_tried`` 때문에 예외가 다시 올라오지 않아 만료로 오인된다.
        """
        return self._probe_error

    def ensure(self) -> bool:
        """처음 한 번만 인증을 확인한다.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        with self._lock:
            if self._tried:
                return self._ok
            return self._verify()

    def recheck(self) -> bool:
        """캐시를 버리고 다시 확인한다.

        사용자가 데스크톱에서 재로그인해 자격증명을 갈아 끼운 뒤
        부른다. 실패 판정은 이 객체가 프로세스가 끝날 때까지 들고
        있으므로, 이 경로가 없으면 회복하는 유일한 방법이 프로세스
        재시작이 된다.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        with self._lock:
            return self._verify()

    def _verify(self) -> bool:
        """확인하고 결과를 기록한다.

        호출자가 ``self._lock`` 을 쥔 채로 불러야 한다.

        Returns:
            인증이 쓸 수 있는 상태면 ``True``.
        """
        self._tried = True
        self._probe_error = None
        try:
            self._ok = self._probe()
        except Exception as error:
            # 게이트에서만 넓게 잡는다. 여기서 새면 화면에 트레이스백이
            # 뜨고 사용자는 무엇이 잘못됐는지 알 수 없다.
            # runner._work 와 같은 근거다.
            logger.exception("인증 확인 실패")
            self._ok = False
            self._probe_error = error
        return self._ok


async def _open_once(client_factory: nlm.ClientFactory) -> None:
    """클라이언트를 열었다 바로 닫는다.

    여는 순간 인증이 확인되므로 따로 요청을 보내지 않는다.

    Args:
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.
    """
    async with client_factory():
        return
