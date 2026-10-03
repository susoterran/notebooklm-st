"""정리본 조립 테스트 — Outline 도 NotebookLM 도 가짜를 쓴다."""

import types
from typing import Any

import pytest

from notebooklm_st.core import digest_markdown, models
from notebooklm_st.services import digest, nlm, outline

INSTRUCTION = "공통 주장과 엇갈리는 지점을 정리해 줘"


def make_config() -> outline.OutlineConfig:
    """테스트용 설정."""
    return outline.OutlineConfig(
        base_url="http://192.168.0.10:3000",
        public_url="http://192.168.0.10:3000",
        token="ol_api_secret_value",
        collection_id="0f2c1a4e-0000-4000-8000-000000000001",
    )


def make_run(run_id: int, outline_title: str) -> models.RunSummary:
    """저장된 실행 하나를 만든다."""
    return models.RunSummary(
        id=run_id,
        url="https://youtu.be/dQw4w9WgXcQ",
        video_id="dQw4w9WgXcQ",
        title="영상 제목",
        created_at="2026-09-20T14:02:11",
        answer_count=0,
        outline_id=f"doc-{run_id}",
        outline_url=f"https://wiki.example.com/doc/{run_id}",
        outline_title=outline_title,
        exported_at="2026-09-20T15:00:00",
    )


@pytest.fixture
def fake_outline(monkeypatch: Any) -> list[str]:
    """문서를 돌려주는 가짜 읽기를 심고 호출 기록을 준다."""
    calls: list[str] = []

    def fetch(config: Any, document_id: Any, **kwargs: Any) -> Any:
        """읽은 문서 ID 를 기록하고 가짜 문서를 돌려준다."""
        calls.append(document_id)
        return outline.OutlineDocument(
            id=document_id,
            title=f"문서 {document_id}",
            markdown=f"{document_id} 의 본문",
        )

    monkeypatch.setattr(digest.outline, "fetch_document", fetch)
    return calls


@pytest.fixture
def fake_pipeline(
    monkeypatch: Any,
) -> dict[str, object]:
    """정리 파이프라인을 가짜로 바꾸고 받은 재료를 기록한다."""
    received: dict[str, object] = {}

    async def run(
        sources: Any, instruction: Any, on_progress: Any, **kwargs: Any
    ) -> tuple[str | None, str]:
        """받은 인자를 기록하고 고정된 주제·본문을 돌려준다."""
        received["sources"] = list(sources)
        received["instruction"] = instruction
        return "밸류에이션 세 강의", "정리된 글"

    monkeypatch.setattr(digest.nlm, "run_digest_pipeline", run)
    return received


def test_build_reads_every_run_in_order(fake_outline, fake_pipeline) -> None:
    """고른 순서대로 문서를 읽는다."""
    runs = [make_run(1, "요약 A"), make_run(2, "요약 B")]

    digest.build(make_config(), runs, INSTRUCTION, lambda _: None)

    assert fake_outline == ["doc-1", "doc-2"]


def test_build_hands_documents_to_the_pipeline(
    fake_outline, fake_pipeline
) -> None:
    """읽은 문서가 그대로 재료가 된다."""
    digest.build(
        make_config(), [make_run(1, "요약 A")], INSTRUCTION, lambda _: None
    )

    sources = fake_pipeline["sources"]
    assert sources == [
        models.DigestSource(title="문서 doc-1", text="doc-1 의 본문")
    ]
    assert fake_pipeline["instruction"] == INSTRUCTION


def test_build_reports_reading_progress(fake_outline, fake_pipeline) -> None:
    """읽는 동안 진행 문구를 남긴다."""
    progress: list[str] = []
    runs = [make_run(1, "요약 A"), make_run(2, "요약 B")]

    digest.build(make_config(), runs, INSTRUCTION, progress.append)

    assert progress[0] == "재료 1/2 읽는 중"
    assert progress[1] == "재료 2/2 읽는 중"


def test_build_names_the_document_it_could_not_read(
    monkeypatch,
) -> None:
    """실패 메시지가 어느 재료에서 막혔는지 짚는다."""

    def boom(config, document_id, **kwargs):
        """읽기가 실패하는 상황을 만든다."""
        raise outline.OutlineError("Outline 에서 문서를 찾지 못했습니다.")

    monkeypatch.setattr(digest.outline, "fetch_document", boom)

    with pytest.raises(outline.OutlineError) as error:
        digest.build(
            make_config(),
            [make_run(1, "AI 에이전트의 미래")],
            INSTRUCTION,
            lambda _: None,
        )

    message = str(error.value)
    assert "AI 에이전트의 미래" in message
    assert "찾지 못했습니다" in message


def test_build_does_not_run_the_pipeline_when_a_read_fails(
    monkeypatch,
) -> None:
    """한 건이라도 못 읽으면 부분 정리본을 만들지 않는다."""
    started = []

    def boom(config, document_id, **kwargs):
        """읽기가 실패하는 상황을 만든다."""
        raise outline.OutlineError("못 읽음")

    async def run(sources, instruction, on_progress, **kwargs):
        """불리면 기록을 남긴다."""
        started.append(True)
        return "정리된 글"

    monkeypatch.setattr(digest.outline, "fetch_document", boom)
    monkeypatch.setattr(digest.nlm, "run_digest_pipeline", run)

    with pytest.raises(outline.OutlineError):
        digest.build(
            make_config(),
            [make_run(1, "요약 A")],
            INSTRUCTION,
            lambda _: None,
        )

    assert started == []


def test_build_returns_a_draft(fake_outline, fake_pipeline) -> None:
    """초안에 본문·재료·지시·날짜가 담긴다."""
    runs = [make_run(1, "요약 A")]

    draft = digest.build(make_config(), runs, INSTRUCTION, lambda _: None)

    assert draft.body == "정리된 글"
    assert draft.sources == tuple(runs)
    assert draft.instruction == INSTRUCTION
    assert len(draft.created_on) == len("2026-09-23")


def test_build_carries_the_topic_into_the_draft(
    fake_outline, fake_pipeline
) -> None:
    """파이프라인이 지은 주제가 초안에 실린다."""
    draft = digest.build(
        make_config(), [make_run(1, "요약 A")], INSTRUCTION, lambda _: None
    )

    assert draft.topic == "밸류에이션 세 강의"


class FakeNotebookLM:
    """넣은 소스 이름만 기록하는 가짜 NotebookLM 클라이언트.

    정리 파이프라인이 부르는 생성·소스 추가·질의·삭제만 흉내 낸다.
    ``test_nlm_digest`` 의 가짜들처럼 타입을 달지 않는다. 달면 mypy 가
    쓰지 않는 메서드까지 ``ClientLike`` 를 다 갖췄는지 따진다.
    """

    def __init__(self):
        """하위 API 를 모두 자기 자신으로 둔다."""
        self.source_titles = []
        self.notebooks = self
        self.sources = self
        self.chat = self

    async def __aenter__(self):
        """자기 자신을 컨텍스트 값으로 돌려준다."""
        return self

    async def __aexit__(self, *args):
        """예외를 삼키지 않는다."""
        return False

    async def create(self, title):
        """가짜 노트북을 돌려준다."""
        return types.SimpleNamespace(id="nb-1", title=title)

    async def delete(self, notebook_id):
        """지우는 척한다."""

    async def add_text(self, notebook_id, title, content, **kwargs):
        """넣은 소스 이름을 기록한다."""
        self.source_titles.append(title)

    async def ask(self, notebook_id, question):
        """고정된 답변을 돌려준다."""
        return types.SimpleNamespace(answer="제목: 주제\n\n정리된 글")


def test_s_numbers_point_to_the_saved_source_numbers(
    fake_outline, monkeypatch
) -> None:
    """노트북의 Sn 소스와 저장 문서의 출처 n. 이 같은 재료다.

    재료 ID 를 섞어 두어, 번호가 ID 가 아니라 고른 순서를 따르는지도
    본다. 문서 읽기 순서가 바뀌면 이 테스트가 깨진다.
    """
    client = FakeNotebookLM()
    real_pipeline = nlm.run_digest_pipeline

    async def run(
        sources: Any, instruction: Any, on_progress: Any, **kwargs: Any
    ) -> tuple[str | None, str]:
        """진짜 파이프라인을 가짜 클라이언트로 돌린다."""
        return await real_pipeline(
            sources, instruction, on_progress, client_factory=lambda: client
        )

    monkeypatch.setattr(digest.nlm, "run_digest_pipeline", run)
    run_ids = [5, 3, 1, 4, 2]
    runs = [make_run(run_id, f"요약 {run_id}") for run_id in run_ids]

    draft = digest.build(make_config(), runs, INSTRUCTION, lambda _: None)
    lines = digest_markdown.to_markdown(draft).splitlines()

    sources = [line for line in lines if line.startswith("    ")]
    assert len(client.source_titles) == len(sources) == len(run_ids)
    for number, run_id in enumerate(run_ids, start=1):
        assert client.source_titles[number - 1] == (
            f"S{number}: 문서 doc-{run_id}"
        )
        assert sources[number - 1].startswith(f"    {number}. [요약 {run_id}](")
