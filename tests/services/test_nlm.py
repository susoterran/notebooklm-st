"""질의 파이프라인 테스트 — 실제 네트워크를 타지 않는다."""

import asyncio

import pytest
from notebooklm import exceptions

from notebooklm_st.core import models
from notebooklm_st.services import nlm

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class FakeReference:
    """가짜 인용 참조 한 건."""

    def __init__(self, number, text, score):
        """필드를 그대로 저장한다."""
        self.citation_number = number
        self.cited_text = text
        self.score = score


class FakeAskResult:
    """가짜 ``chat.ask`` 응답."""

    def __init__(self, answer, conversation_id, references=()):
        """필드를 그대로 저장한다."""
        self.answer = answer
        self.conversation_id = conversation_id
        self.references = list(references)


class FakeNotebook:
    """가짜 노트북 한 권."""

    def __init__(self, notebook_id, title):
        """필드를 그대로 저장한다."""
        self.id = notebook_id
        self.title = title


class FakeNotebooks:
    """가짜 노트북 API. 호출 기록을 공유 리스트에 남긴다."""

    def __init__(self, calls):
        """호출 기록 리스트를 받아 둔다."""
        self._calls = calls

    async def create(self, title):
        """노트북 생성 호출을 기록하고 가짜 노트북을 돌려준다."""
        self._calls.append(("create", title))
        return FakeNotebook("nb-1", title)

    async def delete(self, notebook_id):
        """노트북 삭제 호출을 기록한다."""
        self._calls.append(("delete", notebook_id))

    async def list(self):
        """목록 조회 호출을 기록하고 빈 목록을 돌려준다."""
        self._calls.append(("list",))
        return []


class FakeSource:
    """가짜 소스 한 건. 파이프라인은 제목만 읽는다."""

    def __init__(self, title=None):
        """제목을 저장한다."""
        self.title = title


class FakeSources:
    """가짜 소스 API. 지정하면 소스 추가 시 오류를 던진다."""

    def __init__(self, calls, error=None, title=None):
        """호출 기록 리스트, 던질 오류, 돌려줄 제목을 받아 둔다."""
        self._calls = calls
        self._error = error
        self._title = title

    async def add_url(self, notebook_id, url, *, wait, wait_timeout):
        """URL 추가 호출을 기록하고 가짜 소스를 돌려준다."""
        self._calls.append(("add_url", notebook_id, url, wait, wait_timeout))
        if self._error is not None:
            raise self._error
        return FakeSource(self._title)


class FakeChat:
    """가짜 대화 API. 질문별 응답·오류를 미리 설정할 수 있다."""

    def __init__(self, calls, results=None, errors=None):
        """호출 기록 리스트와 응답·오류 설정을 받아 둔다."""
        self._calls = calls
        self._results = list(results or [])
        self._errors = dict(errors or {})
        self._index = 0

    async def ask(self, notebook_id, question):
        """질문 호출을 기록하고 설정된 응답이나 오류를 돌려준다."""
        self._calls.append(("ask", notebook_id, question))
        index = self._index
        self._index += 1
        if question in self._errors:
            raise self._errors[question]
        if index < len(self._results):
            return self._results[index]
        return FakeAskResult(f"답변: {question}", f"conv-{index}")

    async def delete_conversation(self, notebook_id, conversation_id):
        """대화 삭제 호출을 기록한다."""
        self._calls.append(
            ("delete_conversation", notebook_id, conversation_id)
        )


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


def make_questions(*texts: str) -> list[models.Question]:
    """테스트용 질문 목록을 만든다."""
    return [
        models.Question(
            id=index,
            title=f"제목{index}",
            text=text,
            created_at="2026-08-28T10:00:00",
            updated_at="2026-08-28T10:00:00",
        )
        for index, text in enumerate(texts, start=1)
    ]


def run(
    url: str,
    questions: list[models.Question],
    client: FakeClient,
    progress: list[str] | None = None,
) -> models.RunResult:
    """가짜 클라이언트로 파이프라인을 동기적으로 실행한다."""
    messages = progress if progress is not None else []
    return asyncio.run(
        nlm.run_pipeline(
            url,
            questions,
            messages.append,
            client_factory=lambda: client,
        )
    )


def test_pipeline_creates_indexes_asks_and_deletes():
    """파이프라인이 생성·인덱싱·질의·삭제를 순서대로 부른다."""
    calls = []
    client = FakeClient(calls)
    run(URL, make_questions("핵심 주장은?"), client)
    names = [call[0] for call in calls]
    assert names == ["create", "add_url", "ask", "delete"]


def test_notebook_title_is_temporary():
    """생성되는 노트북 제목이 임시 접두어로 시작한다."""
    calls = []
    run(URL, make_questions("핵심 주장은?"), FakeClient(calls))
    title = calls[0][1]
    assert title.startswith(nlm.TEMP_TITLE_PREFIX)
    assert len(title) > len(nlm.TEMP_TITLE_PREFIX)


def test_source_is_added_with_wait_and_timeout():
    """소스 추가가 대기와 타임아웃을 지정해 호출된다."""
    calls = []
    run(URL, make_questions("핵심 주장은?"), FakeClient(calls))
    _, notebook_id, url, wait, timeout = calls[1]
    assert notebook_id == "nb-1"
    assert url == URL
    assert wait is True
    assert timeout == nlm.SOURCE_WAIT_TIMEOUT


def test_first_question_does_not_delete_a_conversation():
    """첫 질문 전에는 대화 삭제를 부르지 않는다."""
    calls = []
    run(URL, make_questions("하나"), FakeClient(calls))
    assert "delete_conversation" not in [call[0] for call in calls]


def test_later_questions_start_a_fresh_conversation():
    """두 번째 질문부터 이전 대화를 지우고 새로 묻는다."""
    calls = []
    run(URL, make_questions("하나", "둘", "셋"), FakeClient(calls))
    names = [call[0] for call in calls]
    assert names == [
        "create",
        "add_url",
        "ask",
        "delete_conversation",
        "ask",
        "delete_conversation",
        "ask",
        "delete",
    ]
    assert calls[3][2] == "conv-0"
    assert calls[5][2] == "conv-1"


def test_answers_carry_citations():
    """답변에 인용 정보가 그대로 실린다."""
    calls = []
    chat = FakeChat(
        calls,
        results=[
            FakeAskResult(
                "세 가지다.",
                "conv-0",
                references=[FakeReference(1, "근거 구절", 0.9)],
            )
        ],
    )
    result = run(
        URL, make_questions("핵심 주장은?"), FakeClient(calls, chat=chat)
    )
    item = result.items[0]
    assert item.answer == "세 가지다."
    assert item.citations == (
        models.Citation(number=1, text="근거 구절", score=0.9),
    )
    assert item.succeeded is True


def test_result_carries_url_and_video_id():
    """결과에 원본 URL 과 추출된 영상 ID 가 담긴다."""
    calls = []
    result = run(URL, make_questions("하나"), FakeClient(calls))
    assert result.url == URL
    assert result.video_id == "dQw4w9WgXcQ"


def test_chat_failure_affects_only_that_question():
    """질문 하나의 실패가 다른 질문에 영향을 주지 않는다."""
    calls = []
    chat = FakeChat(calls, errors={"둘": exceptions.ChatError("깨짐")})
    result = run(
        URL, make_questions("하나", "둘", "셋"), FakeClient(calls, chat=chat)
    )
    assert [item.succeeded for item in result.items] == [True, False, True]
    assert result.items[1].answer is None
    assert result.items[1].error
    assert [call[0] for call in calls].count("ask") == 3
    assert calls[-1][0] == "delete"


def test_failed_question_does_not_break_conversation_isolation():
    """실패한 질문 뒤에도 헛된 대화 삭제를 시도하지 않는다."""
    calls = []
    chat = FakeChat(calls, errors={"하나": exceptions.ChatError("깨짐")})
    run(URL, make_questions("하나", "둘"), FakeClient(calls, chat=chat))
    assert "delete_conversation" not in [call[0] for call in calls]


def test_source_failure_still_deletes_the_notebook():
    """소스 추가가 실패해도 노트북은 삭제된다."""
    calls = []
    sources = FakeSources(
        calls, error=exceptions.SourceAddError("https://youtu.be/x")
    )
    with pytest.raises(exceptions.SourceAddError):
        run(URL, make_questions("하나"), FakeClient(calls, sources=sources))
    assert [call[0] for call in calls] == ["create", "add_url", "delete"]


def test_progress_callback_reports_each_stage():
    """진행 콜백이 각 단계를 순서대로 알린다."""
    calls = []
    messages = []
    run(URL, make_questions("하나", "둘"), FakeClient(calls), messages)
    assert any("노트북" in text for text in messages)
    assert any("인덱싱" in text for text in messages)
    assert "질문 1/2" in " ".join(messages)
    assert "질문 2/2" in " ".join(messages)


def test_incomplete_citations_are_dropped():
    """번호나 본문이 없는 인용은 결과에서 버린다."""
    calls = []
    chat = FakeChat(
        calls,
        results=[
            FakeAskResult(
                "답변",
                "conv-0",
                references=[
                    FakeReference(1, "온전한 구절", 0.9),
                    FakeReference(None, "번호가 없다", 0.5),
                    FakeReference(2, None, 0.5),
                    FakeReference(3, "", 0.5),
                ],
            )
        ],
    )
    result = run(URL, make_questions("하나"), FakeClient(calls, chat=chat))
    assert result.items[0].citations == (
        models.Citation(number=1, text="온전한 구절", score=0.9),
    )


def test_missing_citation_score_becomes_zero():
    """점수가 없는 인용은 0.0 으로 채운다."""
    calls = []
    chat = FakeChat(
        calls,
        results=[
            FakeAskResult(
                "답변",
                "conv-0",
                references=[FakeReference(1, "구절", None)],
            )
        ],
    )
    result = run(URL, make_questions("하나"), FakeClient(calls, chat=chat))
    assert result.items[0].citations[0].score == 0.0


def test_pipeline_carries_the_source_title():
    """소스가 알려 준 영상 제목을 결과에 싣는다."""
    calls = []
    client = FakeClient(
        calls, sources=FakeSources(calls, title="밸류에이션 강의")
    )

    result = run(URL, make_questions("핵심 주장은?"), client)

    assert result.title == "밸류에이션 강의"


def test_pipeline_reports_a_blank_title_as_none():
    """제목이 비어 있으면 없는 것으로 본다."""
    calls = []
    client = FakeClient(calls, sources=FakeSources(calls, title=""))

    result = run(URL, make_questions("핵심 주장은?"), client)

    assert result.title is None


def test_default_factory_enables_unattended_reauth(monkeypatch) -> None:
    """저장된 브라우저 프로필로 무인 재인증을 시도하도록 켠다."""
    captured: dict = {}

    class FakeClientClass:
        """``NotebookLMClient`` 를 대신한다."""

        @staticmethod
        def from_storage(**kwargs):
            """넘어온 인자를 기록만 한다."""
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(nlm.notebooklm, "NotebookLMClient", FakeClientClass)

    nlm.default_client_factory()

    assert captured["allow_headless"] is True
