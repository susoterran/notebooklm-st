"""이력 한 건을 Outline 문서 본문으로 옮기는 순수 함수들.

화면이 저장 버튼에 넘길 마크다운을 만든다. 저장된 답변은 손대지
않으며, 인용을 뺀 채로 올리는 경우에도 걸러진 사본이 여기로 들어올
뿐이다(→ ``core.answer_text``).
"""

import re
from collections.abc import Sequence

from notebooklm_st.core import models

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
"""메타데이터 값에서 지울 제어문자.

C0(``\\x00-\\x1f``)뿐 아니라 DEL(``\\x7f``)과 C1(``\\x80-\\x9f``)
범위도 포함한다. 영상 제목은 제3자 문자열이라 이 범위가 섞여 들어올
수 있는데, ``\\x85``(NEL) 같은 것은 읽는 쪽에 따라 줄바꿈으로
해석되어 리스트 항목을 두 동강 낸다. 탭·개행·캐리지리턴은 공백으로
접어 살리므로 여기서 뺀다(→ ``one_line``).
"""

_WHITESPACE = re.compile(r"\s+")


def to_markdown(
    summary: models.RunSummary,
    items: Sequence[models.AnswerItem],
    title: str,
    metadata: models.VideoMetadata | None,
) -> str:
    """실행 하나를 Outline 문서 본문으로 만든다.

    메타데이터 리스트, 구분선, 답변들 순으로 쌓는다.

    ``# 제목`` 머리글을 넣지 않는다. Outline 이 문서 제목을 따로
    가지므로 넣으면 제목이 두 번 보인다.

    Args:
        summary: 영상 URL 을 고를 때 쓸 실행 요약.
        items: 문서에 담을 답변 목록. 화면이 그리는 것과 같은 목록을
            받으므로 인용을 뺀 상태면 인용이 비어 들어온다.
        title: 사람이 저장 직전에 확인한 문서 제목. 같은 값이 Outline
            문서 제목이 되므로 여기서 다시 계산하지 않는다.
        metadata: 영상에서 뽑아 온 메타데이터. 없으면 제목과 영상 URL
            두 줄만 남는다.

    Returns:
        메타데이터 리스트로 시작하고 줄바꿈 하나로 끝나는 마크다운
        문서.
    """
    blocks = [_metadata_block(summary, title, metadata), "---"]
    blocks.extend(_item_block(item) for item in items)
    return "\n\n".join(blocks) + "\n"


def _metadata_block(
    summary: models.RunSummary,
    title: str,
    metadata: models.VideoMetadata | None,
) -> str:
    """문서 맨 앞에 둘 메타데이터 리스트를 만든다.

    YAML frontmatter 를 쓰지 않는다. CommonMark 에서 **문단 바로 뒤의**
    ``---`` 는 구분선이 아니라 setext H2 밑줄이라, frontmatter 를 그대로
    실으면 Outline 이 네 줄을 통째로 머리글 하나로 뭉쳐 버린다. 실물로
    확인했다.

    값이 없는 항목은 줄째 뺀다. "채널: 모름" 을 적으면 모르는 것과
    비어 있는 것이 같은 모양이 된다.

    Args:
        summary: 영상 URL 을 고를 때 쓸 실행 요약.
        title: 호출자가 미리 정한 문서 제목. ``summary.title`` 이
            비었을 때의 대체값 계산을 여기서 다시 하지 않는다 — 두
            곳에서 따로 계산하면 어긋날 수 있다.
        metadata: 영상에서 뽑아 온 메타데이터.

    Returns:
        ``- 라벨: 값`` 꼴의 마크다운 리스트.
    """
    lines = [f"- 제목: {one_line(title)}"]
    if metadata is not None and metadata.channel:
        lines.append(f"- 채널: {one_line(metadata.channel)}")
    if metadata is not None and metadata.upload_date:
        lines.append(f"- 업로드 일자: {metadata.upload_date}")
    lines.append(f"- 영상 URL: {_source_url(summary)}")
    return "\n".join(lines)


def _source_url(summary: models.RunSummary) -> str:
    """메타데이터에 적을 영상 URL 을 고른다.

    저장된 원문에는 재생목록·추적 파라미터가 붙어 있을 수 있다.
    검증된 영상 ID 가 있으면 정규 URL 을 다시 짓고, ID 가 없는 옛
    이력만 원문을 쓴다.
    """
    if summary.video_id:
        return f"https://www.youtube.com/watch?v={summary.video_id}"
    return one_line(summary.url)


def one_line(value: str) -> str:
    """리스트 항목 하나에 안전하게 들어갈 한 줄로 만든다.

    제어문자를 지우고 남은 공백류를 공백 하나로 접는다. 개행이 그대로
    남으면 리스트 항목이 두 동강 나고, 뒤쪽 줄은 리스트 밖의 문단이
    되어 버린다.

    정리본도 같은 규칙을 써야 하므로 공개한다. 두 벌로 갈라지면
    한쪽만 고쳐진다.

    Args:
        value: 다듬을 값.

    Returns:
        한 줄로 접은 값.
    """
    return _WHITESPACE.sub(" ", _CONTROL.sub("", value)).strip()


def _item_block(item: models.AnswerItem) -> str:
    """답변 하나를 제목, 본문, 인용 순으로 적는다.

    질문 원문은 싣지 않는다. 위키에 남길 것은 답변이지 무엇을
    물었는지의 기록이 아니다. 원문은 이력 화면의 접은 영역에 그대로
    남는다.
    """
    parts = [f"## {item.question_title}"]
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
