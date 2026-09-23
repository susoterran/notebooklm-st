"""NotebookLM 질의 파이프라인."""

import contextlib
import uuid
from collections.abc import Callable, Sequence
from typing import Protocol, cast

import notebooklm
from notebooklm import exceptions

from notebooklm_st.core import (
    answer_text,
    digest_title,
    errors,
    models,
    youtube,
)

SOURCE_WAIT_TIMEOUT = 120.0
TEMP_TITLE_PREFIX = "tmp-"
DIGEST_SOURCE_LIMIT = 10
"""정리본 하나에 넣을 수 있는 최대 재료 수.

소스 하나에 최대 ``SOURCE_WAIT_TIMEOUT`` 초를 기다리므로 이 수가 곧
최악의 대기 시간이다(10건이면 약 20분). 화면이 이 상한으로 선택을
막는다.
"""


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


class SourceLike(Protocol):
    """노트북에 붙은 소스 한 건.

    라이브러리의 ``Source`` 는 필드가 많지만 파이프라인은 제목만 쓴다.
    유튜브 소스에서는 이 값이 영상 제목이다.
    """

    title: str | None


class SourcesLike(Protocol):
    """소스 API."""

    async def add_url(
        self,
        notebook_id: str,
        url: str,
        *,
        wait: bool,
        wait_timeout: float,
    ) -> SourceLike:
        """URL 소스를 노트북에 추가하고 그 소스를 돌려준다."""
        ...

    async def add_text(
        self,
        notebook_id: str,
        title: str,
        content: str,
        *,
        wait: bool,
        wait_timeout: float,
    ) -> SourceLike:
        """텍스트 소스를 노트북에 추가하고 그 소스를 돌려준다."""
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

    쿠키가 죽어 있으면 라이브러리가 토큰 재추출과 쿠키 회전을 먼저
    시도하고, 그것마저 안 되면 저장된 브라우저 프로필로 무인 재인증을
    한 번 시도한다. 마지막 단계는 기본으로 꺼져 있어 여기서 켠다.

    대가는 실패하는 경로가 몇 초 길어지는 것뿐이다. 성공하면 사용자가
    아무것도 하지 않아도 인증이 되살아나고, 실패해도 화면이 재로그인을
    안내할 수 있다.

    Returns:
        ``async with`` 로 열 수 있는 클라이언트 컨텍스트.
    """
    # 라이브러리 클래스는 위 Protocol 을 선언하지 않으므로 경계에서
    # 한 번만 캐스팅한다. 파이프라인 내부는 Protocol 로 검사된다.
    return cast(
        contextlib.AbstractAsyncContextManager[ClientLike],
        notebooklm.NotebookLMClient.from_storage(allow_headless=True),
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
        질문별 결과와 영상 제목을 담은 ``RunResult``.

    Raises:
        exceptions.NotebookLMError: 노트북 생성이나 자막 인덱싱처럼
            질문 이전 단계가 실패한 경우. 질문 단위 실패는 예외가
            아니라 결과 안에 담긴다.
    """
    items: list[models.AnswerItem] = []
    title: str | None = None
    async with client_factory() as client:
        on_progress("임시 노트북 생성 중")
        notebook = await client.notebooks.create(
            f"{TEMP_TITLE_PREFIX}{uuid.uuid4().hex[:8]}"
        )
        try:
            on_progress(f"자막 인덱싱 중 (최대 {int(SOURCE_WAIT_TIMEOUT)}초)")
            source = await client.sources.add_url(
                notebook.id,
                url,
                wait=True,
                wait_timeout=SOURCE_WAIT_TIMEOUT,
            )
            # 빈 제목은 없는 것으로 본다. 화면이 video_id 로 대신한다.
            title = source.title or None
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
        title=title,
    )


async def run_digest_pipeline(
    sources: Sequence[models.DigestSource],
    instruction: str,
    on_progress: Callable[[str], None],
    client_factory: ClientFactory = default_client_factory,
) -> tuple[str | None, str]:
    """재료 여러 편을 넣고 정리 지시를 한 번 던진다.

    ``run_pipeline`` 과 대칭이다 — 임시 노트북을 만들어 쓰고 반드시
    지운다. 다른 점은 소스가 여럿이고 질문이 하나라는 것뿐이다.

    지시에는 제목 요구가 함께 실려 나가고(→ ``core.digest_title``)
    돌아온 답변에서 그 줄을 떼어 주제로 돌려준다. 질의를 두 번
    던지지 않는다.

    Args:
        sources: 노트북에 넣을 글들. 상한은 호출자가 지킨다
            (``DIGEST_SOURCE_LIMIT``).
        instruction: 던질 정리 지시.
        on_progress: 진행 문구를 받는 콜백.
        client_factory: 클라이언트 컨텍스트를 여는 팩토리. 테스트가
            가짜 클라이언트를 넣을 수 있게 뚫어 둔다.

    Returns:
        ``(주제, 본문)``. 둘 다 인용 흔적을 걷어낸 값이며, 답변이
        제목 줄을 주지 않았으면 주제가 ``None`` 이다.

    Raises:
        exceptions.NotebookLMError: 노트북 생성·소스 등록·질의 중
            어느 단계든 실패한 경우. 정리는 질문이 하나뿐이라 부분
            성공이 없다.
    """
    async with client_factory() as client:
        on_progress("임시 노트북 생성 중")
        notebook = await client.notebooks.create(
            f"{TEMP_TITLE_PREFIX}{uuid.uuid4().hex[:8]}"
        )
        try:
            total = len(sources)
            for index, source in enumerate(sources, start=1):
                on_progress(
                    f"소스 {index}/{total} 등록 중"
                    f" (최대 {int(SOURCE_WAIT_TIMEOUT)}초)"
                )
                await client.sources.add_text(
                    notebook.id,
                    source.title,
                    source.text,
                    wait=True,
                    wait_timeout=SOURCE_WAIT_TIMEOUT,
                )
            on_progress("정리 중")
            result = await client.chat.ask(
                notebook.id, digest_title.wrap(instruction)
            )
        finally:
            # run_pipeline 과 같은 이유로 여기서 on_progress 를 부르지
            # 않는다. 콜백이 Streamlit 을 건드리는데, 사용자가 페이지를
            # 옮긴 순간 스크립트가 중단되어 삭제에 닿지 못한다.
            await client.notebooks.delete(notebook.id)

    # 제목 줄을 **먼저** 떼어낸다. 후속 제안 블록을 자르는 규칙은
    # 마지막 수평선을 기준으로 하므로, 답변이 제목 줄 뒤에 수평선을
    # 두면 그 규칙이 본문 전체를 잘라낸다.
    topic, body = digest_title.split(result.answer)
    # 인용 번호는 임시 노트북 안에서만 뜻이 있다. 노트북이 지워진
    # 뒤에도 위키에 남으면 아무 데도 가리키지 않는 숫자가 된다.
    cleaned = answer_text.strip_citation_markers(
        answer_text.strip_trailing_block(body)
    )
    if topic is not None:
        topic = answer_text.strip_citation_markers(topic).strip() or None
    return topic, cleaned


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
