"""인증 상태 확인.

라이브러리는 만료된 인증을 스스로 되살리려 토큰 재추출과 쿠키 회전을
시도한다. 클라이언트를 여는 것만으로 그 복구가 돌기 때문에, 이 모듈은
열어 보는 것으로 확인을 대신한다.

그 복구가 실패하면 사람이 데스크톱에서 다시 로그인해 자격증명을
가져와야 한다. 앱은 브라우저를 띄우지 않는다.
"""

import asyncio
import dataclasses
import logging
import subprocess
import sys
import threading
from collections.abc import Callable

from notebooklm_st.core import errors
from notebooklm_st.services import nlm

logger = logging.getLogger(__name__)

ProbeLike = Callable[[], bool]

IMPORT_TIMEOUT = 30.0
"""반입 자식 프로세스를 기다리는 최대 초.

JSON 을 읽고 파일 하나를 쓰는 일이라 보통 1초 안에 끝난다. 이 값은
그게 동작하지 않았을 때를 위한 뒷받침이다.
"""

MAX_PAYLOAD_BYTES = 1 << 20
"""받아들일 자격증명 파일의 최대 크기.

``storage_state.json`` 은 수 KB 다. 넉넉히 잡아 두고, 잘못 고른 파일을
CLI 에 넘기기 전에 걸러 낸다.
"""

RunnerLike = Callable[..., subprocess.CompletedProcess[bytes]]
"""자식을 돌리는 함수의 모양.

``subprocess.run`` 의 키워드 인자가 많아 Protocol 로 적으면 길기만
하다. 테스트가 가짜를 끼우는 것이 목적이므로 느슨하게 둔다.
"""


@dataclasses.dataclass(frozen=True, slots=True)
class ImportResult:
    """자격증명 반입 결과.

    ``detail`` 에 쿠키 값을 담지 않는다. 화면이 이 문자열을 그대로
    보여 주기 때문이다.
    """

    ok: bool
    detail: str


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


def import_credentials(
    payload: bytes,
    runner: RunnerLike = subprocess.run,
) -> ImportResult:
    """업로드된 쿠키 JSON 을 활성 프로필에 기록한다.

    같은 일을 하는 라이브러리 함수는 private 이고 협력자까지 private
    이므로, 공개 CLI 를 자식 프로세스로 부른다. CLI 가 도메인 필터와
    검증, 원자적 쓰기, 파일 권한까지 맡는다.

    ``uv`` 로 부르지 않는다. ``uv`` 는 PATH 에 없을 수 있고, 앱은 이미
    notebooklm 이 설치된 인터프리터 안에서 돌고 있다.

    반입에 성공해도 인증 판정은 바꾸지 않는다. 호출자가 이어서
    ``AuthGate.recheck`` 를 부른다. 판정은 한 곳에서만 일어난다.

    Args:
        payload: 업로드된 파일의 내용.
        runner: 자식을 돌리는 함수. 테스트가 가짜를 넣을 수 있게
            뚫어 둔다.

    Returns:
        성공 여부와 사람에게 보여 줄 사유.
    """
    if not payload:
        return ImportResult(ok=False, detail="빈 파일입니다.")
    if len(payload) > MAX_PAYLOAD_BYTES:
        return ImportResult(
            ok=False,
            detail=f"파일이 너무 큽니다({len(payload)} 바이트).",
        )
    try:
        completed = runner(
            [
                sys.executable,
                "-m",
                "notebooklm",
                "auth",
                "import-cookies",
                "-",
            ],
            input=payload,
            capture_output=True,
            timeout=IMPORT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return ImportResult(
            ok=False,
            detail=f"{int(IMPORT_TIMEOUT)}초 안에 끝나지 않았습니다.",
        )
    if completed.returncode == 0:
        return ImportResult(ok=True, detail="자격증명을 반입했습니다.")
    return ImportResult(
        ok=False, detail=_failure_detail(completed.stderr, completed.stdout)
    )


def _failure_detail(stderr: bytes, stdout: bytes, limit: int = 300) -> str:
    """자식의 실패 출력을 화면에 쓸 짧은 문자열로 만든다.

    Args:
        stderr: 자식의 표준 오류.
        stdout: 자식의 표준 출력. stderr 가 비었을 때 대신 쓴다.
        limit: 남길 최대 글자 수.

    Returns:
        끝에서 ``limit`` 글자. 아무 말도 없으면 대체 문구.
    """
    raw = stderr or stdout or b""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "자세한 사유를 알 수 없습니다."
    return text[-limit:]


async def _open_once(client_factory: nlm.ClientFactory) -> None:
    """클라이언트를 열었다 바로 닫는다.

    여는 순간 인증이 확인되므로 따로 요청을 보내지 않는다.

    Args:
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.
    """
    async with client_factory():
        return
