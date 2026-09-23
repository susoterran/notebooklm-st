"""정리 파이프라인 테스트 — 실제 네트워크를 타지 않는다."""

import asyncio

import pytest
from notebooklm import exceptions

from notebooklm_st.core import digest_title, models
from notebooklm_st.services import nlm


class FakeAskResult:
    """가짜 ``chat.ask`` 응답."""

    def __init__(self, answer, conversation_id="conv-1"):
        """필드를 그대로 저장한다."""
        self.answer = answer
        self.conversation_id = conversation_id
        self.references = []


class FakeNotebook:
    """가짜 노트북 한 권."""

    def __init__(self, notebook_id, title):
        """필드를 그대로 저장한다."""
        self.id = notebook_id
        self.title = title


class FakeNotebooks:
    """가짜 노트북 API."""

    def __init__(self, calls):
        """호출 기록 리스트를 받아 둔다."""
        self._calls = calls

    async def create(self, title):
        """노트북 생성 호출을 기록한다."""
        self._calls.append(("create", title))
        return FakeNotebook("nb-1", title)

    async def delete(self, notebook_id):
        """노트북 삭제 호출을 기록한다."""
        self._calls.append(("delete", notebook_id))

    async def list(self):
        """빈 목록을 돌려준다."""
        self._calls.append(("list",))
        return []


class FakeSource:
    """가짜 소스 한 건."""

    def __init__(self, title=None):
        """제목을 저장한다."""
        self.title = title


class FakeSources:
    """가짜 소스 API. 지정하면 텍스트 추가 시 오류를 던진다."""

    def __init__(self, calls, error=None):
        """호출 기록 리스트와 던질 오류를 받아 둔다."""
        self._calls = calls
        self._error = error

    async def add_url(self, notebook_id, url, *, wait, wait_timeout):
        """정리 파이프라인은 부르지 않는다.

        부르면 기록으로 드러난다.
        """
        self._calls.append(("add_url", notebook_id, url))
        return FakeSource()

    async def add_text(
        self, notebook_id, title, content, *, wait, wait_timeout
    ):
        """텍스트 추가 호출을 기록하고 가짜 소스를 돌려준다."""
        self._calls.append(
            ("add_text", notebook_id, title, content, wait, wait_timeout)
        )
        if self._error is not None:
            raise self._error
        return FakeSource(title)


class FakeChat:
    """가짜 대화 API."""

    def __init__(self, calls, answer="정리된 글"):
        """호출 기록 리스트와 돌려줄 답변을 받아 둔다."""
        self._calls = calls
        self._answer = answer

    async def ask(self, notebook_id, question):
        """질문 호출을 기록하고 설정된 답변을 돌려준다."""
        self._calls.append(("ask", notebook_id, question))
        return FakeAskResult(self._answer)

    async def delete_conversation(self, notebook_id, conversation_id):
        """정리 파이프라인은 부르지 않는다."""
        self._calls.append(("delete_conversation", notebook_id))


class FakeClient:
    """``async with`` 로 열리는 가짜 NotebookLM 클라이언트."""

    def __init__(self, calls, *, chat=None, sources=None):
        """하위 가짜 API들을 같은 호출 기록 리스트로 구성한다."""
        self.notebooks = FakeNotebooks(calls)
        self.sources = sources or FakeSources(calls)
        self.chat = chat or FakeChat(calls)

    async def __aenter__(self):
        """자기 자신을 컨텍스트 값으로 돌려준다."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """예외를 삼키지 않는다."""
        return False


INSTRUCTION = "공통 주장과 엇갈리는 지점을 정리해 줘"


def make_sources(*titles):
    """테스트용 재료 목록을 만든다."""
    return [
        models.DigestSource(title=title, text=f"{title} 의 본문")
        for title in titles
    ]


def digest(sources, client, instruction=INSTRUCTION, progress=None):
    """가짜 클라이언트로 정리 파이프라인을 동기적으로 실행한다.

    ``(주제, 본문)`` 을 돌려준다.
    """
    messages = progress if progress is not None else []
    return asyncio.run(
        nlm.run_digest_pipeline(
            sources,
            instruction,
            messages.append,
            client_factory=lambda: client,
        )
    )


def test_pipeline_creates_adds_asks_and_deletes():
    """생성·텍스트 추가·질의·삭제를 순서대로 부른다."""
    calls = []

    digest(make_sources("요약 A", "요약 B"), FakeClient(calls))

    names = [call[0] for call in calls]
    assert names == ["create", "add_text", "add_text", "ask", "delete"]


def test_notebook_title_is_temporary():
    """정리도 tmp- 노트북을 쓴다.

    정리 화면이 회수할 수 있어야 한다.
    """
    calls = []

    digest(make_sources("요약 A"), FakeClient(calls))

    assert calls[0][1].startswith(nlm.TEMP_TITLE_PREFIX)


def test_each_source_is_added_with_its_title_and_text():
    """재료의 제목과 본문이 그대로 소스가 된다."""
    calls = []

    digest(make_sources("요약 A"), FakeClient(calls))

    _, notebook_id, title, content, wait, timeout = calls[1]
    assert notebook_id == "nb-1"
    assert title == "요약 A"
    assert content == "요약 A 의 본문"
    assert wait is True
    assert timeout == nlm.SOURCE_WAIT_TIMEOUT


def test_the_instruction_is_asked_once():
    """질문은 정리 지시 하나뿐이다."""
    calls = []

    digest(make_sources("요약 A", "요약 B"), FakeClient(calls))

    asks = [call for call in calls if call[0] == "ask"]
    assert len(asks) == 1
    assert INSTRUCTION in asks[0][2]


def test_the_prompt_asks_for_a_title():
    """제목 요구가 지시와 함께 한 번에 나간다."""
    calls = []

    digest(make_sources("요약 A"), FakeClient(calls))

    asks = [call for call in calls if call[0] == "ask"]
    assert digest_title.DIRECTIVE in asks[0][2]


def test_the_topic_comes_from_the_title_line():
    """첫 줄의 제목 표시가 주제가 되고 본문에서 빠진다."""
    calls = []
    answer = "제목: 밸류에이션 세 강의\n\n핵심은 셋이다."
    client = FakeClient(calls, chat=FakeChat(calls, answer=answer))

    topic, body = digest(make_sources("요약 A"), client)

    assert topic == "밸류에이션 세 강의"
    assert body == "핵심은 셋이다."


def test_the_topic_is_missing_when_the_answer_has_no_title_line():
    """제목 표시가 없으면 주제 없이 본문만 돌려준다."""
    calls = []

    topic, body = digest(make_sources("요약 A"), FakeClient(calls))

    assert topic is None
    assert body == "정리된 글"


def test_the_topic_drops_citation_markers():
    """주제에 박힌 인용 번호도 걷어낸다."""
    calls = []
    answer = "제목: 밸류에이션 [1]\n\n핵심은 셋이다."
    client = FakeClient(calls, chat=FakeChat(calls, answer=answer))

    topic, _ = digest(make_sources("요약 A"), client)

    assert topic == "밸류에이션"


def test_a_rule_after_the_title_line_does_not_eat_the_body():
    """제목 줄 바로 뒤의 수평선이 본문을 삼키지 않는다.

    후속 제안 블록을 자르는 규칙은 **마지막** 수평선을 기준으로 하므로,
    제목 줄을 먼저 떼어내지 않으면 남은 수평선이 본문 전체를 잘라낸다.
    """
    calls = []
    answer = "제목: 주제다\n\n---\n\n핵심은 셋이다."
    client = FakeClient(calls, chat=FakeChat(calls, answer=answer))

    topic, body = digest(make_sources("요약 A"), client)

    assert topic == "주제다"
    assert "핵심은 셋이다." in body


def test_notebook_is_deleted_when_a_source_fails():
    """소스 등록이 실패해도 노트북을 남기지 않는다."""
    calls = []
    client = FakeClient(
        calls,
        sources=FakeSources(calls, error=exceptions.NotebookLMError("없음")),
    )

    with pytest.raises(exceptions.NotebookLMError):
        digest(make_sources("요약 A"), client)

    assert ("delete", "nb-1") in calls


def test_body_drops_citation_markers():
    """임시 노트북 안에서만 뜻이 있는 인용 번호를 지운다."""
    calls = []
    client = FakeClient(
        calls, chat=FakeChat(calls, answer="핵심은 셋이다 [1].")
    )

    _, body = digest(make_sources("요약 A"), client)

    assert body == "핵심은 셋이다."


def test_body_drops_the_trailing_suggestion_block():
    """답변 끝의 후속 제안 블록을 버린다."""
    calls = []
    answer = "핵심은 셋이다.\n\n---\n\n💡 **다음으로 무엇을 할까요?**"
    client = FakeClient(calls, chat=FakeChat(calls, answer=answer))

    _, body = digest(make_sources("요약 A"), client)

    assert "다음으로" not in body
    assert body.startswith("핵심은 셋이다.")


def test_progress_counts_the_sources():
    """진행 문구가 재료 순서를 센다."""
    progress = []

    digest(make_sources("요약 A", "요약 B"), FakeClient([]), progress=progress)

    assert progress[0] == "임시 노트북 생성 중"
    assert "소스 1/2" in progress[1]
    assert "소스 2/2" in progress[2]
    assert progress[-1] == "정리 중"
