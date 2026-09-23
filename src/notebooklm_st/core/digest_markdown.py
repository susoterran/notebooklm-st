"""정리본 초안을 Outline 문서 본문으로 옮기는 순수 함수들.

화면이 저장 버튼에 넘길 마크다운을 만든다. ``markdown_export`` 가
요약본 하나를 옮긴다면 이쪽은 정리본 하나를 옮긴다.
"""

from notebooklm_st.core import markdown_export, models


def to_markdown(draft: models.DigestDraft) -> str:
    """정리본 초안을 Outline 문서 본문으로 만든다.

    메타데이터 리스트, 출처, 구분선, 정리 본문 순으로 쌓는다.

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
        _sources_block(draft),
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

    Args:
        draft: 저장할 초안.

    Returns:
        ``- 라벨: 값`` 꼴의 마크다운 리스트.
    """
    return "\n".join(
        [
            "- 종류: 정리본",
            f"- 만든 날: {draft.created_on}",
            f"- 정리 지시: {markdown_export.one_line(draft.instruction)}",
        ]
    )


def _sources_block(draft: models.DigestDraft) -> str:
    """재료가 된 요약본들을 링크 목록으로 적는다.

    Args:
        draft: 저장할 초안.

    Returns:
        ``## 출처`` 머리글과 링크 리스트.
    """
    items = "\n".join(_source_line(run) for run in draft.sources)
    return f"## 출처\n\n{items}"


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
