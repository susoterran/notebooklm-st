"""정리본 초안을 Outline 문서 본문으로 옮기는 순수 함수들.

화면이 저장 버튼에 넘길 마크다운을 만든다. ``markdown_export`` 가
요약본 하나를 옮긴다면 이쪽은 정리본 하나를 옮긴다.
"""

from notebooklm_st.core import markdown_export, models

_NESTED_INDENT = "    "
"""하위 리스트 항목 앞에 붙일 들여쓰기.

CommonMark 는 부모 항목의 내용 시작(``- `` 뒤, 2칸)만큼만 들여 써도
하위 리스트로 읽지만, 4칸을 요구하는 파서도 있어 4칸을 쓴다.
"""


def to_markdown(draft: models.DigestDraft) -> str:
    """정리본 초안을 Outline 문서 본문으로 만든다.

    메타데이터 리스트, 구분선, 정리 본문 순으로 쌓는다.

    ``# 제목`` 머리글을 넣지 않는다. Outline 이 문서 제목을 따로
    가지므로 넣으면 제목이 두 번 보인다.

    Args:
        draft: 저장할 초안.

    Returns:
        메타데이터 리스트로 시작하고 줄바꿈 하나로 끝나는 마크다운
        문서.
    """
    blocks = [
        _metadata_block(draft),
        "---",
        draft.body.strip(),
    ]
    return "\n\n".join(blocks) + "\n"


def _metadata_block(draft: models.DigestDraft) -> str:
    """문서 맨 앞에 둘 메타데이터 리스트를 만든다.

    YAML frontmatter 를 쓰지 않는다. CommonMark 에서 **문단 바로 뒤의**
    ``---`` 는 구분선이 아니라 setext H2 밑줄이라, frontmatter 를
    그대로 실으면 Outline 이 여러 줄을 머리글 하나로 뭉쳐 버린다.
    요약본에서 실물로 확인한 함정이다(→ ``markdown_export``).

    정리 지시는 적지 않는다. 지시는 질문 관리가 가진 작업용 글이지
    문서를 읽는 사람에게 필요한 정보가 아니다.

    출처도 메타데이터 항목 하나다. 재료가 된 요약본들을 ``- 출처:``
    아래 하위 리스트로 적는다.

    Args:
        draft: 저장할 초안.

    Returns:
        ``- 라벨: 값`` 꼴의 마크다운 리스트.
    """
    lines = [
        "- 종류: 정리본",
        f"- 작성일자: {draft.created_on}",
        "- 출처:",
    ]
    lines.extend(_NESTED_INDENT + _source_line(run) for run in draft.sources)
    return "\n".join(lines)


def _source_line(run: models.RunSummary) -> str:
    """요약본 하나를 출처 한 줄로 적는다.

    위키에 붙은 문서 제목을 쓴다. 정리본을 읽는 사람이 원본을 찾을 때
    보는 이름이 그것이기 때문이다.

    Args:
        run: 재료가 된 실행.

    Returns:
        링크가 있으면 마크다운 링크, 없으면 제목만.
    """
    label = markdown_export.one_line(
        run.outline_title or run.title or run.video_id
    )
    if run.outline_url:
        return f"- [{label}]({run.outline_url})"
    return f"- {label}"
