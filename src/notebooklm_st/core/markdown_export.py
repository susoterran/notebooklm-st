"""이력 한 건을 마크다운 문서와 파일명으로 옮기는 순수 함수들.

화면이 다운로드 버튼에 넘길 문자열을 만든다. 저장된 답변은 손대지
않으며, 인용을 걸러 내려받는 경우에도 걸러진 사본이 여기로 들어올
뿐이다(→ ``core.answer_text``).
"""

import re
from collections.abc import Sequence

from notebooklm_st.core import models

MAX_STEM_CHARS = 100
"""파일명에서 확장자를 뺀 부분의 최대 글자 수.

파일 시스템 한계는 보통 255 바이트인데 한글은 한 자가 UTF-8 로 3
바이트다. 100 자면 300 바이트에 확장자까지 얹혀 한계에 닿으므로 실제
한계보다 넉넉히 낮춰 잡는다.
"""

_FORBIDDEN = re.compile(r'[<>:"/\|?*\x00-\x1f]')
"""윈도우가 파일명에 허용하지 않는 문자와 제어 문자.

유튜브 제목에는 ``:`` 와 ``?`` 가 흔해서 거르지 않으면 저장이
실패한다.
"""

_REPEATED_SPACE = re.compile(r"\s+")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
"""YAML 문자열에서 지울 제어문자.

C0(``\\x00-\\x1f``)뿐 아니라 DEL(``\\x7f``)과 C1(``\\x80-\\x9f``)
범위도 포함한다. PyYAML 은 이 범위 대부분을 인쇄 불가로 보아
``ReaderError`` 를 던지고 ``\\x85`` 는 줄바꿈으로 해석한다. 영상
제목은 제3자 문자열이라 이 범위가 하나만 섞여도 문서 전체가
frontmatter 를 쓰는 목적인 파싱 자체에 실패한다. 탭·개행·캐리지리턴은
이스케이프해서 살리므로 여기서 뺀다.
"""


def to_markdown(
    summary: models.RunSummary,
    items: Sequence[models.AnswerItem],
    metadata: models.VideoMetadata | None = None,
) -> str:
    """실행 하나를 마크다운 문서 한 장으로 만든다.

    Args:
        summary: 머리글과 출처에 쓸 실행 요약.
        items: 문서에 담을 답변 목록. 화면이 그리는 것과 같은 목록을
            받으므로 인용을 숨긴 상태면 인용이 비어 들어온다.
        metadata: 영상에서 뽑아 온 메타데이터. 없으면 frontmatter 에
            ``title`` 과 ``url`` 만 남는다.

    Returns:
        YAML frontmatter 로 시작하고 줄바꿈 하나로 끝나는 마크다운
        문서.
    """
    title = summary.title or summary.video_id
    blocks = [
        _frontmatter(summary, title, metadata),
        f"# {title}",
        f"- 출처: {summary.url}\n- 실행: {summary.created_at}",
    ]
    blocks.extend(_item_block(item) for item in items)
    return "\n\n".join(blocks) + "\n"


def to_filename(title: str | None, video_id: str) -> str:
    """영상 제목을 내려받을 파일 이름으로 바꾼다.

    Args:
        title: 저장된 영상 제목. 없을 수 있다.
        video_id: 제목이 없거나 못 쓸 문자뿐일 때 대신 쓸 영상 ID.

    Returns:
        ``.md`` 로 끝나는 파일 이름.
    """
    stem = _sanitize(title or "") or _sanitize(video_id) or "run"
    return f"{stem}.md"


def _frontmatter(
    summary: models.RunSummary,
    title: str,
    metadata: models.VideoMetadata | None,
) -> str:
    """문서 맨 앞에 둘 YAML 블록을 만든다.

    값이 없는 키는 ``null`` 로 적지 않고 아예 뺀다. ``null`` 을
    적으면 읽는 쪽이 "값이 null 인 채널" 과 "모르는 채널" 을
    구분하지 못한다.

    Args:
        summary: URL 과 영상 ID 에 쓸 실행 요약.
        title: H1 머리글과 같은 값으로 호출자가 미리 정한 제목.
            ``summary.title`` 이 비었을 때의 대체값 계산을 여기서
            다시 하지 않는다 — 두 곳에서 따로 계산하면 어긋날 수
            있다.
        metadata: 영상에서 뽑아 온 메타데이터.

    Returns:
        ``---`` 로 감싼 YAML frontmatter 블록.
    """
    lines = [f"title: {_yaml_string(title)}"]
    if metadata is not None and metadata.channel:
        lines.append(f"channel: {_yaml_string(metadata.channel)}")
    if metadata is not None and metadata.upload_date:
        lines.append(f"upload_date: {metadata.upload_date}")
    lines.append(f"url: {_source_url(summary)}")
    return "---\n" + "\n".join(lines) + "\n---"


def _source_url(summary: models.RunSummary) -> str:
    """Frontmatter 에 적을 URL 을 고른다.

    저장된 원문에는 재생목록·추적 파라미터나 ``#`` 이 붙어 있을 수
    있어 따옴표 없는 YAML 값으로 쓰기 위험하다. 검증된 영상 ID 로
    정규 URL 을 다시 짓고, ID 가 없는 옛 이력만 원문을 따옴표로
    감싼다.
    """
    if summary.video_id:
        return f"https://www.youtube.com/watch?v={summary.video_id}"
    return _yaml_string(summary.url)


def _yaml_string(value: str) -> str:
    """큰따옴표로 감싼 YAML 스칼라로 만든다.

    역슬래시를 먼저 바꾼다. 나중에 바꾸면 앞서 넣은 이스케이프까지
    다시 이스케이프된다.
    """
    escaped = (
        _CONTROL.sub("", value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _item_block(item: models.AnswerItem) -> str:
    """답변 하나를 제목, 질문 원문, 본문, 인용 순으로 적는다."""
    parts = [f"## {item.question_title}", _quote(item.question_text)]
    if item.error is not None:
        parts.append(f"**답변을 받지 못했습니다:** {item.error}")
        return "\n\n".join(parts)
    if item.answer:
        parts.append(item.answer)
    if item.citations:
        parts.append(f"### 인용 {len(item.citations)}건")
        parts.append(
            "\n".join(
                f"- **[{citation.number}]** {citation.text}"
                for citation in item.citations
            )
        )
    return "\n\n".join(parts)


def _quote(text: str) -> str:
    """질문 원문을 줄마다 인용 기호를 붙인 블록으로 만든다.

    화면은 원문을 접어 두지만 마크다운에는 접기가 없다. 인용 블록으로
    두면 답변 본문과 눈으로 갈린다.
    """
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _sanitize(text: str) -> str:
    """파일명으로 쓸 수 있게 다듬는다.

    못 쓰는 문자를 지우지 않고 공백으로 바꾼다. 지우면 ``어떻게?
    AI는`` 이 ``어떻게AI는`` 으로 붙어 읽기 어려워진다. 자르기는 겹친
    공백을 접은 뒤에 하고, 윈도우가 싫어하는 끝의 마침표와 공백은
    마지막에 뗀다.
    """
    cleaned = _REPEATED_SPACE.sub(" ", _FORBIDDEN.sub(" ", text)).strip()
    return cleaned[:MAX_STEM_CHARS].strip(" .")
