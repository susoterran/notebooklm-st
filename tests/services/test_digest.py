"""정리본 조립 테스트 — Outline 도 NotebookLM 도 가짜를 쓴다."""

from typing import Any

import pytest

from notebooklm_st.core import models
from notebooklm_st.services import digest, outline

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
