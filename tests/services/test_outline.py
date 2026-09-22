"""Outline 클라이언트 테스트."""

import httpx
import pytest

from notebooklm_st.services import outline

BASE_URL = "http://192.168.0.10:3000"
TOKEN = "ol_api_secret_value"
COLLECTION = "0f2c1a4e-0000-4000-8000-000000000001"


def set_env(monkeypatch, base_url=BASE_URL, token=TOKEN, collection=COLLECTION):
    """환경변수 셋을 채운다. 빈 문자열을 주면 그 변수는 지운다."""
    for name, value in (
        (outline.URL_ENV_VAR, base_url),
        (outline.TOKEN_ENV_VAR, token),
        (outline.COLLECTION_ENV_VAR, collection),
    ):
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


def test_config_reads_all_three_variables(monkeypatch) -> None:
    """셋이 다 있으면 설정을 만든다."""
    set_env(monkeypatch)

    config = outline.config_from_env()

    assert config is not None
    assert config.base_url == BASE_URL
    assert config.token == TOKEN
    assert config.collection_id == COLLECTION


def test_config_is_none_without_any_variable(monkeypatch) -> None:
    """하나도 없으면 설정이 아니다."""
    set_env(monkeypatch, base_url="", token="", collection="")

    assert outline.config_from_env() is None


def test_config_is_none_when_only_the_token_is_missing(monkeypatch) -> None:
    """부분 설정은 설정이 아니다. 401 을 맞기 전에 막는다."""
    set_env(monkeypatch, token="")

    assert outline.config_from_env() is None


def test_config_is_none_for_a_blank_value(monkeypatch) -> None:
    """공백만 든 값은 비어 있는 것으로 본다."""
    set_env(monkeypatch, collection="   ")

    assert outline.config_from_env() is None


def test_config_drops_the_trailing_slash(monkeypatch) -> None:
    """끝 슬래시를 여기서 한 번 뗀다. 호출 지점마다 따지지 않는다."""
    set_env(monkeypatch, base_url="http://192.168.0.10:3000/")

    config = outline.config_from_env()

    assert config is not None
    assert config.base_url == "http://192.168.0.10:3000"


def make_config() -> outline.OutlineConfig:
    """테스트용 설정."""
    return outline.OutlineConfig(
        base_url=BASE_URL, token=TOKEN, collection_id=COLLECTION
    )


def fake_poster(response, calls):
    """호출 인자를 기록하고 준비된 응답을 돌려주는 poster 를 만든다."""

    def post(url, **kwargs):
        """httpx.post 를 대신한다."""
        calls.append((url, kwargs))
        if isinstance(response, Exception):
            raise response
        return response

    return post


def made(
    url="/doc/ai-agents-abc123", doc_id="doc-1", title="AI 에이전트의 미래"
):
    """documents.create 가 돌려주는 200 응답을 만든다."""
    return httpx.Response(
        200,
        json={"data": {"id": doc_id, "title": title, "url": url}},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )


def test_create_document_posts_to_the_create_endpoint() -> None:
    """주소·헤더·본문이 API 계약대로 나간다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.create_document(
        make_config(),
        "AI 에이전트의 미래",
        "# 본문",
        poster=fake_poster(made(), calls),
    )

    url, kwargs = calls[0]
    assert url == f"{BASE_URL}/api/documents.create"
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kwargs["json"] == {
        "title": "AI 에이전트의 미래",
        "text": "# 본문",
        "collectionId": COLLECTION,
        "publish": True,
    }
    assert kwargs["timeout"] == outline.CREATE_TIMEOUT


def test_create_document_returns_the_saved_document() -> None:
    """응답에서 ID·제목·URL 을 꺼낸다."""
    document = outline.create_document(
        make_config(),
        "AI 에이전트의 미래",
        "# 본문",
        poster=fake_poster(made(), []),
    )

    assert document.id == "doc-1"
    assert document.title == "AI 에이전트의 미래"
    assert document.url == f"{BASE_URL}/doc/ai-agents-abc123"


def test_create_document_keeps_an_absolute_url_as_is() -> None:
    """절대 URL 로 오는 배포판도 받는다(스펙 13.1)."""
    document = outline.create_document(
        make_config(),
        "제목",
        "# 본문",
        poster=fake_poster(made(url="https://wiki.example.com/doc/x"), []),
    )

    assert document.url == "https://wiki.example.com/doc/x"


def test_create_document_rejects_a_response_without_data() -> None:
    """기대한 모양이 아니면 OutlineError 다."""
    response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.create_document(
            make_config(), "제목", "# 본문", poster=fake_poster(response, [])
        )

    assert "이해하지 못했습니다" in str(excinfo.value)
