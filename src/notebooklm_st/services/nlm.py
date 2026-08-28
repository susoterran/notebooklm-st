"""NotebookLM 질의 파이프라인."""

import contextlib
import uuid
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

import notebooklm
from notebooklm import exceptions

from notebooklm_st.core import errors, models, youtube

SOURCE_WAIT_TIMEOUT = 120.0
TEMP_TITLE_PREFIX = "tmp-"


class ReferenceLike(Protocol):
    """답변에 딸려 오는 인용 한 건.

    라이브러리의 ``ChatReference`` 는 세 필드가 모두 ``None`` 일 수 있다.
    """

    citation_number: int | None
    cited_text: str | None
    score: float | None


class AskResultLike(Protocol):
    """``chat.ask`` 의 응답."""

    answer: str
    conversation_id: str
    references: Sequence[ReferenceLike]


class NotebookLike(Protocol):
    """노트북 한 권."""

    id: str
    title: str


class ChatLike(Protocol):
    """대화 API."""

    async def ask(self, notebook_id: str, question: str) -> AskResultLike:
        """질문을 던지고 응답을 받는다."""
        ...

    async def delete_conversation(
        self, notebook_id: str, conversation_id: str
    ) -> None:
        """대화 하나를 지운다."""
        ...


class NotebooksLike(Protocol):
    """노트북 API."""

    async def create(self, title: str) -> NotebookLike:
        """노트북을 만든다."""
        ...

    async def delete(self, notebook_id: str) -> None:
        """노트북을 지운다."""
        ...

    async def list(self) -> Sequence[NotebookLike]:
        """노트북 목록을 돌려준다."""
        ...


class SourcesLike(Protocol):
    """소스 API."""

    # 반환된 Source 를 파이프라인이 쓰지 않으므로 모양을 고정하지 않는다.
    async def add_url(
        self,
        notebook_id: str,
        url: str,
        *,
        wait: bool,
        wait_timeout: float,
    ) -> Any:
        """URL 소스를 노트북에 추가한다."""
        ...


class ClientLike(Protocol):
    """파이프라인이 쓰는 클라이언트의 최소 모양."""

    chat: ChatLike
    notebooks: NotebooksLike
    sources: SourcesLike


ClientFactory = Callable[[], contextlib.AbstractAsyncContextManager[ClientLike]]


def default_client_factory() -> contextlib.AbstractAsyncContextManager[
    ClientLike
]:
    """저장된 쿠키로 NotebookLM 클라이언트를 연다.

    Returns:
        ``async with`` 로 열 수 있는 클라이언트 컨텍스트.
    """
    # 라이브러리 클래스는 위 Protocol 을 선언하지 않으므로 경계에서
    # 한 번만 캐스팅한다. 파이프라인 내부는 Protocol 로 검사된다.
    return cast(
        contextlib.AbstractAsyncContextManager[ClientLike],
        notebooklm.NotebookLMClient.from_storage(),
    )


async def run_pipeline(
    url: str,
    questions: Sequence[models.Question],
    on_progress: Callable[[str], None],
    client_factory: ClientFactory = default_client_factory,
) -> models.RunResult:
    """영상 하나에 질문들을 던지고 결과를 모은다.

    임시 노트북을 만들어 쓰고 반드시 지운다. 질문마다 앞 대화를 끊어
    답변이 서로 물들지 않게 한다.

    Args:
        url: 검증을 통과한 단일 YouTube 영상 URL.
        questions: 물어볼 질문 목록.
        on_progress: 진행 문구를 받는 콜백.
        client_factory: 클라이언트 컨텍스트를 여는 팩토리. 테스트가
            가짜 클라이언트를 넣을 수 있게 뚫어 둔다.

    Returns:
        질문별 결과를 담은 ``RunResult``.

    Raises:
        exceptions.NotebookLMError: 노트북 생성이나 자막 인덱싱처럼
            질문 이전 단계가 실패한 경우. 질문 단위 실패는 예외가
            아니라 결과 안에 담긴다.
    """
    items: list[models.AnswerItem] = []
    async with client_factory() as client:
        on_progress("임시 노트북 생성 중")
        notebook = await client.notebooks.create(
            f"{TEMP_TITLE_PREFIX}{uuid.uuid4().hex[:8]}"
        )
        try:
            on_progress(f"자막 인덱싱 중 (최대 {int(SOURCE_WAIT_TIMEOUT)}초)")
            await client.sources.add_url(
                notebook.id,
                url,
                wait=True,
                wait_timeout=SOURCE_WAIT_TIMEOUT,
            )
            previous_conversation: str | None = None
            total = len(questions)
            for index, question in enumerate(questions, start=1):
                on_progress(f"질문 {index}/{total}")
                if previous_conversation is not None:
                    await client.chat.delete_conversation(
                        notebook.id, previous_conversation
                    )
                item, previous_conversation = await _ask_one(
                    client, notebook.id, question
                )
                items.append(item)
        finally:
            # 여기서 on_progress 를 부르지 않는다. 진행 콜백은 Streamlit
            # API 를 호출하는데, 사용자가 페이지를 이동한 순간 스크립트가
            # 중단되어 아래 삭제에 도달하지 못하고 노트북이 남는다.
            await client.notebooks.delete(notebook.id)

    return models.RunResult(
        url=url,
        video_id=youtube.extract_video_id(url) or "",
        items=tuple(items),
    )


async def list_temp_notebooks(
    client_factory: ClientFactory = default_client_factory,
) -> list[models.TempNotebook]:
    """정리 대상으로 남아 있는 임시 노트북을 찾는다.

    제목이 ``tmp-`` 로 시작하는 것만 고른다. 사용자가 손으로 만든
    노트북은 건드리지 않는다.

    Args:
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.

    Returns:
        임시 노트북 목록.
    """
    async with client_factory() as client:
        notebooks = await client.notebooks.list()
    return [
        models.TempNotebook(id=item.id, title=item.title)
        for item in notebooks
        if item.title.startswith(TEMP_TITLE_PREFIX)
    ]


async def delete_notebooks(
    notebook_ids: Sequence[str],
    client_factory: ClientFactory = default_client_factory,
) -> int:
    """주어진 노트북들을 지운다.

    ``notebooks.delete`` 는 멱등적이라 이미 없는 노트북을 지워도
    예외가 나지 않는다.

    Args:
        notebook_ids: 지울 노트북 ID 목록.
        client_factory: 클라이언트 컨텍스트를 여는 팩토리.

    Returns:
        삭제를 시도한 개수.
    """
    if not notebook_ids:
        return 0
    async with client_factory() as client:
        for notebook_id in notebook_ids:
            await client.notebooks.delete(notebook_id)
    return len(notebook_ids)


async def _ask_one(
    client: ClientLike, notebook_id: str, question: models.Question
) -> tuple[models.AnswerItem, str | None]:
    """질문 하나를 던지고 결과와 이어 갈 대화 ID 를 돌려준다.

    실패하면 대화 ID 로 ``None`` 을 돌려준다. 끊을 대화가 없으므로
    다음 질문이 헛되이 삭제를 시도하지 않는다.

    Args:
        client: 열려 있는 NotebookLM 클라이언트.
        notebook_id: 임시 노트북 ID.
        question: 던질 질문.

    Returns:
        답변 항목과, 이어 갈 대화 ID(실패 시 ``None``) 의 튜플.
    """
    try:
        result = await client.chat.ask(notebook_id, question.text)
    except exceptions.ChatError as error:
        return (
            models.AnswerItem(
                question_title=question.title,
                question_text=question.text,
                answer=None,
                citations=(),
                error=errors.to_message(error).text,
            ),
            None,
        )
    citations = _to_citations(result.references)
    return (
        models.AnswerItem(
            question_title=question.title,
            question_text=question.text,
            answer=result.answer,
            citations=citations,
            error=None,
        ),
        result.conversation_id,
    )


def _to_citations(
    references: Sequence[ReferenceLike],
) -> tuple[models.Citation, ...]:
    """인용을 화면과 저장이 그대로 쓸 수 있는 형태로 정규화한다.

    번호나 본문이 없는 인용은 근거로 보여 줄 값어치가 없으므로 버리고,
    점수만 없는 경우 0.0 으로 채운다. 경계에서 한 번 정리해 두면 화면과
    저장 코드가 ``None`` 을 다루지 않아도 된다.

    Args:
        references: 라이브러리가 돌려준 인용 목록.

    Returns:
        번호와 본문이 모두 있는 인용만 담은 튜플.
    """
    citations: list[models.Citation] = []
    for reference in references:
        number = reference.citation_number
        text = reference.cited_text
        if number is None or not text:
            continue
        score = reference.score
        citations.append(
            models.Citation(
                number=number,
                text=text,
                score=score if score is not None else 0.0,
            )
        )
    return tuple(citations)
