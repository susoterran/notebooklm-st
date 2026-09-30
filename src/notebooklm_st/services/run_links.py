"""실행에 Outline 문서 링크를 적는다.

요약본을 Outline 에 올린 뒤 로컬 이력에 문서 링크를 적고 답변을
지우는 일 하나를 맡는다. 이력의 저장·조회·삭제는 ``run_history``
가 맡는다. 부르는 곳은 ``run_export.save`` 다.
"""

import sqlite3

from notebooklm_st.services import store


def mark_exported(
    connection: sqlite3.Connection,
    run_id: int,
    *,
    document_id: str,
    document_title: str,
    document_url: str,
) -> None:
    """문서 링크를 적고 로컬 답변을 지운다.

    두 문장을 커밋 하나로 묶는다. 중간에 죽어도 "본문은 사라졌는데
    링크는 없는" 상태가 생기지 않는다.

    영상 메타데이터(``run_metadata``)는 지우지 않는다. 문서 머리에
    적은 채널·업로드 일자와 같은 값의 캐시로 남아 정리본 재료 표가
    쓴다. 정본은 Outline 이고, 이력 동기화가 문서에서 다시 읽어
    맞춘다.

    Outline 의 자료형을 받지 않고 문자열 셋을 받는다. 저장소가 외부
    서비스를 알 이유가 없다.

    Args:
        connection: 열린 커넥션.
        run_id: 링크를 걸 실행 ID.
        document_id: Outline 문서 ID. 나중에 문서를 다시 읽을 때 쓴다.
        document_title: Outline 에 붙은 문서 제목.
        document_url: 사람이 열 수 있는 절대 URL.

    Raises:
        ValueError: 그 ID 의 실행이 없거나 이미 저장된 경우. 이때는
            아무것도 지우지 않는다.
    """
    # 커넥션은 앱 전체가 함께 쓴다. UPDATE 만 걸린 채로 예외가 빠져
    # 나가면 다음 조회가 그 실행을 저장된 것으로 그리고, 다른 곳의
    # commit 이 반쪽짜리 내보내기를 확정해 버린다. 그래서 어떤 실패든
    # 여기서 되돌리고 다시 던진다.
    try:
        cursor = connection.execute(
            "UPDATE runs SET outline_id = ?, outline_url = ?,"
            " outline_title = ?, exported_at = ?"
            " WHERE id = ? AND exported_at IS NULL",
            (
                document_id,
                document_url,
                document_title,
                store.now(),
                run_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(
                f"실행 {run_id} 을 찾을 수 없거나 이미 저장되었습니다."
            )
        connection.execute("DELETE FROM answers WHERE run_id = ?", (run_id,))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
