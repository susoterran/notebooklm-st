"""인증 상태 확인.

라이브러리는 만료된 인증을 스스로 되살리려 토큰 재추출과 쿠키 회전을
시도한다. 클라이언트를 여는 것만으로 그 복구가 돌기 때문에, 이 모듈은
열어 보는 것으로 확인을 대신한다.

그 복구가 실패하면 사람이 데스크톱에서 다시 로그인해 자격증명을
가져와야 한다. 앱은 브라우저를 띄우지 않는다.
"""

import asyncio
import logging
import threading
from collections.abc import Callable

from notebooklm_st.core import errors
from notebooklm_st.services import nlm

logger = logging.getLogger(__name__)

ProbeLike = Callable[[], bool]


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
