"""목록 한 줄에 쓸 라벨을 만드는 순수 함수들.

이력·정리본 두 화면이 같은 규칙으로 제목을 자른다. 로직이 두 파일에
각각 있으면 상한이나 말줄임 문자를 바꿀 때 한쪽만 고치고 조용히
어긋날 수 있어 여기로 모은다.
"""

LIST_LABEL_MAX_CHARS = 60
"""목록 한 줄에 들어갈 최대 글자 수.

목록은 한 줄로 읽혀야 값을 한다 — 길어서 줄바꿈되면 여러 항목이 섞여
보인다.
"""


def shorten(title: str, limit: int = LIST_LABEL_MAX_CHARS) -> str:
    """목록 한 줄에 들어가도록 제목을 자른다.

    Args:
        title: 자를 원본 제목.
        limit: 결과 문자열의 최대 길이.

    Returns:
        상한 이하면 그대로. 넘으면 뒤를 잘라내고 ``…`` 를 붙인
        문자열이며, 그 길이는 ``limit`` 과 같다.
    """
    if len(title) <= limit:
        return title
    return f"{title[: limit - 1]}…"
