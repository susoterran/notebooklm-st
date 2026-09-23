"""정리본 백그라운드 실행 테스트."""

from notebooklm import exceptions

from notebooklm_st.core import models
from notebooklm_st.services import digest_runner, outline

INSTRUCTION = "공통 주장과 엇갈리는 지점을 정리해 줘"


def make_config() -> outline.OutlineConfig:
    """테스트용 설정."""
    return outline.OutlineConfig(
        base_url="http://192.168.0.10:3000",
        public_url="http://192.168.0.10:3000",
        token="ol_api_secret_value",
        collection_id="0f2c1a4e-0000-4000-8000-000000000001",
    )


def make_run(run_id: int = 1) -> models.RunSummary:
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
        outline_title="요약 A",
        exported_at="2026-09-20T15:00:00",
    )


def make_draft() -> models.DigestDraft:
    """가짜 초안."""
    return models.DigestDraft(
        body="정리된 글",
        sources=(make_run(),),
        instruction=INSTRUCTION,
        created_on="2026-09-23",
    )


def wait_for(registry) -> digest_runner.DigestHandle:
    """실행이 끝날 때까지 기다렸다가 핸들을 돌려준다."""
    digest_runner.join_all(timeout=5.0)
    handle = registry.get()
    assert handle is not None
    assert handle.status != "running"
    return handle


def start(registry, build) -> bool:
    """가짜 build 로 정리를 시작한다."""
    return digest_runner.start_digest(
        registry,
        make_config(),
        [make_run()],
        INSTRUCTION,
        build=build,
    )


def test_successful_digest_marks_done_with_a_draft() -> None:
    """성공하면 초안을 들고 done 이 된다."""
    registry = digest_runner.DigestRegistry()
    draft = make_draft()

    start(registry, lambda *args, **kwargs: draft)
    handle = wait_for(registry)

    assert handle.status == "done"
    assert handle.draft == draft
    assert handle.finished_at is not None


def test_progress_is_recorded() -> None:
    """Build 가 남긴 진행 문구가 핸들에 쌓인다."""
    registry = digest_runner.DigestRegistry()

    def build(config, runs, instruction, on_progress):
        """진행 문구를 남기고 초안을 돌려준다."""
        on_progress("재료 1/1 읽는 중")
        on_progress("정리 중")
        return make_draft()

    start(registry, build)
    handle = wait_for(registry)

    assert handle.progress == ["재료 1/1 읽는 중", "정리 중"]


def test_outline_failure_keeps_its_message() -> None:
    """Outline 오류는 이미 사람이 읽을 문장이라 그대로 쓴다."""
    registry = digest_runner.DigestRegistry()

    def build(config, runs, instruction, on_progress):
        """읽기 실패를 만든다."""
        raise outline.OutlineError("'요약 A' 을 읽지 못했습니다.")

    start(registry, build)
    handle = wait_for(registry)

    assert handle.status == "failed"
    assert handle.error_message == "'요약 A' 을 읽지 못했습니다."
    assert handle.error_level == "error"


def test_auth_failure_becomes_the_login_hint() -> None:
    """인증 만료는 재로그인 안내로 바뀐다."""
    registry = digest_runner.DigestRegistry()

    def build(config, runs, instruction, on_progress):
        """인증 만료를 만든다."""
        raise exceptions.AuthError("expired")

    start(registry, build)
    handle = wait_for(registry)

    assert handle.status == "failed"
    assert "notebooklm login" in (handle.error_message or "")


def test_unexpected_error_is_reported() -> None:
    """예상 못 한 오류도 running 에 남지 않는다."""
    registry = digest_runner.DigestRegistry()

    def build(config, runs, instruction, on_progress):
        """프로그래밍 오류를 만든다."""
        raise ValueError("어딘가 틀렸다")

    start(registry, build)
    handle = wait_for(registry)

    assert handle.status == "failed"
    assert "ValueError" in (handle.error_message or "")


def test_second_start_is_refused_while_running() -> None:
    """정리는 한 번에 한 건이다."""
    registry = digest_runner.DigestRegistry()
    registry.start()

    accepted = start(registry, lambda *args, **kwargs: make_draft())

    assert accepted is False
    assert registry.is_running() is True


def test_clear_empties_the_slot() -> None:
    """버리면 슬롯이 비어 다음 정리를 시작할 수 있다."""
    registry = digest_runner.DigestRegistry()
    start(registry, lambda *args, **kwargs: make_draft())
    wait_for(registry)

    registry.clear()

    assert registry.get() is None
    assert registry.is_running() is False
