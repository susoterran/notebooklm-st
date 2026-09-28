"""Outline 의 실패 응답을 사람이 읽고 고칠 수 있는 문장으로 옮긴다.

호출 경로(생성·조회·목록)마다 "무엇부터 확인하라" 가 다르다. 그
차이를 여기 모아 ``services.outline`` 은 호출만 남긴다.
"""

from collections.abc import Callable

import httpx

DETAIL_LIMIT = 200
"""Outline 이 보낸 설명에서 화면에 옮길 최대 글자 수.

`st.error` 한 칸에 들어가야 한다. 더 길면 정작 우리가 쓴 안내 문장이
밀려 안 읽힌다.
"""

StatusMessage = Callable[[int], str]
"""상태 코드를 안내 문장으로 옮기는 함수.

읽기와 쓰기가 서로 다른 것을 쓴다.
"""


def failure_message(
    response: httpx.Response,
    token: str,
    status: int,
    status_message: StatusMessage,
) -> str:
    """실패 응답을 사람이 읽고 고칠 수 있는 한 문장으로 만든다.

    우리가 지은 안내 뒤에 **Outline 이 보낸 설명**을 붙인다. 설명을
    버리고 상태 코드만 남기면, 서버가 무엇이 틀렸는지 정확히 말해
    줬는데도 사람이 추측으로 파게 된다. 실제로 그렇게 됐다.

    Args:
        response: 오류 응답.
        token: 화면에 오르면 안 되는 값. 본문에 섞여 있으면 설명째
            버린다.
        status: HTTP 상태 코드.
        status_message: 이 호출 경로의 안내를 만드는 함수.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    text = detail(response, token)
    if not text:
        return status_message(status)
    return f"{status_message(status)} Outline 이 말한 것: {text}"


def create_status_message(status: int) -> str:
    """오류 상태 코드를 "무엇부터 확인하라" 는 안내로 옮긴다.

    순서가 중요하다. 실측해 보니 **없는 컬렉션 ID** 가 404 가 아니라
    403 으로 온다 — Outline 이 "없다" 와 "권한 없다" 를 한 응답으로
    뭉치기 때문이다. 그래서 403 에서 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 400:
        return (
            "Outline 이 값을 받아들이지 않았습니다."
            " 컬렉션 ID 가 UUID 인지 확인하세요 — 컬렉션 이름은"
            " 받지 않습니다."
        )
    if status == 401:
        return (
            "Outline 이 API 토큰을 받아들이지 않았습니다."
            " 토큰이 맞는지, 만료되지 않았는지 확인하세요."
        )
    if status == 403:
        return (
            "Outline 이 요청을 거부했습니다."
            " 컬렉션 ID 가 이 토큰의 계정이 쓸 수 있는 컬렉션인지"
            " 먼저 확인하세요 — 없는 컬렉션도 이 오류로 옵니다."
            " 그다음 토큰 scope(documents.create)를 봅니다."
        )
    if status == 404:
        return "Outline 이 대상을 찾지 못했습니다. 주소를 확인하세요."
    return f"Outline 이 오류를 냈습니다(HTTP {status})."


def read_status_message(status: int) -> str:
    """읽기 실패를 "무엇부터 확인하라" 는 안내로 옮긴다.

    쓰기와 문구를 나눈다. ``create_status_message`` 는 403 에서 컬렉션
    ID 를 먼저 의심하게 하는데, 그것은 ``documents.create`` 의 실측에서
    나온 순서다. 읽기에 그 안내를 내면 멀쩡한 컬렉션을 파게 된다.

    **401 에서 scope 를 먼저 짚는 것도 실측에서 나왔다.** scope 밖
    엔드포인트를 부르면 권한 오류(403)가 아니라 인증 오류(401)가
    오고, 본문은 ``Authentication required`` 다. Outline 의 현재
    소스는 이 경우 403 을 내므로 배포판에 따라 다르며, 그래서 401 과
    403 양쪽이 scope 를 짚는다. 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다 — 저장은 되는데 정리본만 안 되는 상황이 정확히
    이것이다.

    Args:
        status: HTTP 상태 코드.

    Returns:
        화면에 그대로 나갈 한국어 문장.
    """
    if status == 401:
        return (
            "Outline 이 읽기 요청을 인증하지 못했습니다."
            " API 키 scope 에 documents.info 가 있는지 먼저"
            " 확인하세요 — 저장만 하던 키에는 없고, 그때 403 이"
            " 아니라 이 오류로 옵니다."
            " 그다음 토큰이 맞는지, 만료되지 않았는지 봅니다."
        )
    if status == 403:
        return (
            "Outline 이 문서 읽기를 거부했습니다."
            " API 키 scope 에 읽기 권한이 있는지 확인하세요 —"
            " 저장만 하던 키에는 없습니다."
        )
    if status == 404:
        return (
            "Outline 에서 문서를 찾지 못했습니다."
            " 위키에서 지워졌을 수 있습니다."
            " 그 이력을 선택에서 빼고 다시 시도하세요."
        )
    return f"Outline 이 오류를 냈습니다(HTTP {status})."


def detail(response: httpx.Response, token: str) -> str:
    """응답 본문에서 사람에게 보여 줄 한 줄을 뽑는다.

    토큰은 헤더에 있지 본문에 없으므로 본문을 보여 줘도 샐 것이 없다.
    그래도 서버가 무엇을 돌려주든 화면에 무엇이 실리는지는 우리가
    통제해야 하므로, 토큰이 섞여 있으면 설명째 버린다.

    Args:
        response: 오류 응답.
        token: 본문에 있으면 안 되는 값.

    Returns:
        한 줄로 접고 길이를 자른 설명. 읽을 것이 없으면 빈 문자열.
    """
    try:
        body = response.json()
        text = str(body.get("message") or body.get("error") or "")
    except (ValueError, AttributeError):
        text = response.text
    text = " ".join(text.split())[:DETAIL_LIMIT]
    if not text or token in text:
        return ""
    return text
