"""이력 한 건을 Outline 문서 본문으로 옮기는 순수 함수들.

화면이 저장 버튼에 넘길 마크다운을 만든다. 저장된 답변은 손대지
않으며, 인용을 뺀 채로 올리는 경우에도 걸러진 사본이 여기로 들어올
뿐이다(→ ``core.answer_text``).
"""

import re
from collections.abc import Sequence

from notebooklm_st.core import models

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
    title: str,
    metadata: models.VideoMetadata | None,
) -> str:
    """실행 하나를 Outline 문서 본문으로 만든다.

    ``# 제목`` 머리글을 넣지 않는다. Outline 이 문서 제목을 따로
    가지므로 넣으면 제목이 두 번 보인다. 대신 출처 블록은 남긴다 —
    frontmatter 의 URL 은 구분선 사이 맨 텍스트로 렌더되어 클릭되지
    않는다.

    Args:
        summary: 출처와 실행 시각에 쓸 실행 요약.
        items: 문서에 담을 답변 목록. 화면이 그리는 것과 같은 목록을
            받으므로 인용을 뺀 상태면 인용이 비어 들어온다.
        title: 사람이 저장 직전에 확인한 문서 제목. 같은 값이 Outline
            문서 제목이 되므로 여기서 다시 계산하지 않는다.
        metadata: 영상에서 뽑아 온 메타데이터. 없으면 frontmatter 에
            ``title`` 과 ``url`` 만 남는다.

    Returns:
        YAML frontmatter 로 시작하고 줄바꿈 하나로 끝나는 마크다운
        문서.
    """
    blocks = [
        _frontmatter(summary, title, metadata),
        f"- 출처: {summary.url}\n- 실행: {summary.created_at}",
    ]
    blocks.extend(_item_block(item) for item in items)
    return "\n\n".join(blocks) + "\n"


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
