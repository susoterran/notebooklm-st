"""Outline 클라이언트 테스트."""

import httpx
import pytest

from notebooklm_st.services import outline

BASE_URL = "http://192.168.0.10:3000"
TOKEN = "ol_api_secret_value"
COLLECTION = "0f2c1a4e-0000-4000-8000-000000000001"


PUBLIC_URL = "https://outline.example.com"


def set_env(
    monkeypatch,
    base_url=BASE_URL,
    token=TOKEN,
    collection=COLLECTION,
    public_url="",
):
    """환경변수를 채운다. 빈 문자열을 주면 그 변수는 지운다."""
    for name, value in (
        (outline.URL_ENV_VAR, base_url),
        (outline.TOKEN_ENV_VAR, token),
        (outline.COLLECTION_ENV_VAR, collection),
        (outline.PUBLIC_URL_ENV_VAR, public_url),
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


def make_config(public_url=None) -> outline.OutlineConfig:
    """테스트용 설정. 공개 주소를 안 주면 연결 주소와 같다."""
    return outline.OutlineConfig(
        base_url=BASE_URL,
        public_url=public_url if public_url is not None else BASE_URL,
        token=TOKEN,
        collection_id=COLLECTION,
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
    headers = kwargs["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == f"Bearer {TOKEN}"
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


def _failed_create(status: int):
    """오류 상태 코드의 응답을 만든다. 문서 생성 전용."""
    return httpx.Response(
        status,
        json={"message": "nope"},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )


def create_with(response) -> str:
    """준비된 응답(또는 예외)으로 저장을 시도하고 오류 문구를 돌려준다."""
    with pytest.raises(outline.OutlineError) as excinfo:
        outline.create_document(
            make_config(), "제목", "# 본문", poster=fake_poster(response, [])
        )
    return str(excinfo.value)


def test_rejected_token_says_so() -> None:
    """401 은 토큰 문제다."""
    assert "토큰" in create_with(_failed_create(401))


def test_forbidden_points_at_the_collection_first() -> None:
    """403 은 토큰보다 컬렉션을 먼저 의심하게 한다.

    실측: 없는 컬렉션 ID 로 documents.create 를 부르면 404 가 아니라
    403 authorization_error 가 온다. Outline 이 "없다" 와 "권한 없다" 를
    한 응답으로 뭉치기 때문이다. 토큰을 먼저 의심하게 하면 멀쩡한
    토큰을 파게 된다.
    """
    message = create_with(_failed_create(403))

    assert "컬렉션" in message
    assert message.index("컬렉션") < message.index("scope")


def test_validation_error_points_at_the_collection_id() -> None:
    """400 은 값이 틀렸다는 뜻이다. 컬렉션 ID 가 첫 용의자다.

    실측: 컬렉션 이름을 UUID 자리에 넣으면 400 이 온다.
    """
    assert "UUID" in create_with(_failed_create(400))


def test_error_carries_outlines_own_message() -> None:
    """Outline 이 보낸 설명을 함께 보여 준다.

    이유를 버리고 상태 코드만 남기면 사람이 추측으로 파게 된다.
    토큰은 헤더에 있지 응답 본문에 없으므로 본문을 보여 줘도 샐 것이
    없다.
    """
    response = httpx.Response(
        400,
        json={
            "ok": False,
            "error": "validation_error",
            "message": "collectionId: must be uuid",
        },
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )

    assert "collectionId: must be uuid" in create_with(response)


def test_error_without_a_readable_body_says_only_the_status() -> None:
    """본문이 비어 있으면 상태 코드만 남긴다. 지어내지 않는다."""
    response = httpx.Response(
        500,
        text="",
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )

    message = create_with(response)

    assert "500" in message
    assert "Outline 이 말한 것:" not in message


def test_a_body_that_echoes_the_secret_is_dropped() -> None:
    """서버가 무엇을 돌려주든 비밀값은 화면에 올리지 않는다.

    Outline 은 그러지 않지만, 화면에 무엇이 실리는지는 우리가 통제할
    수 있어야 한다.
    """
    response = httpx.Response(
        400,
        json={"message": "rejected value " + TOKEN},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )

    message = create_with(response)

    assert TOKEN not in message
    assert "UUID" in message  # 설명만 버리고 안내는 남는다


def test_a_long_body_is_truncated() -> None:
    """본문이 길어도 화면을 덮지 않는다."""
    response = httpx.Response(
        400,
        json={"message": "가" * 1000},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.create"),
    )

    assert len(create_with(response)) < 500


def test_not_found_points_at_the_address() -> None:
    """404 는 주소 문제다.

    컬렉션이 없을 때는 404 가 아니라 403 이 온다(실측). 그래서 404 에서
    컬렉션을 의심하게 하면 엉뚱한 곳을 보게 된다.
    """
    assert "주소" in create_with(_failed_create(404))


def test_server_error_carries_the_status_code() -> None:
    """5xx 는 상태 코드를 그대로 보여 준다."""
    assert "503" in create_with(_failed_create(503))


def test_timeout_reads_as_a_connection_failure() -> None:
    """응답이 없으면 연결 실패로 묶는다."""
    assert "연결하지 못했습니다" in create_with(
        httpx.TimeoutException("timed out")
    )


def test_connection_error_reads_as_a_connection_failure() -> None:
    """붙지 못한 경우도 같은 문장이다."""
    assert "연결하지 못했습니다" in create_with(httpx.ConnectError("refused"))


def test_the_token_never_appears_in_an_error_message() -> None:
    """어떤 실패 경로에서도 토큰이 새지 않는다."""
    for response in (
        _failed_create(401),
        _failed_create(500),
        httpx.TimeoutException("timed out"),
    ):
        assert TOKEN not in create_with(response)


def test_a_malformed_base_url_reads_as_a_connection_failure() -> None:
    """주소가 망가져 있어도 화면에 원문 예외를 흘리지 않는다.

    ``httpx.InvalidURL`` 은 ``HTTPError`` 를 상속하지 않아 따로 잡지
    않으면 화면까지 그대로 올라간다. 자리표시자를 그대로 둔 첫
    설정에서 실제로 나오는 경로다.
    """
    config = outline.OutlineConfig(
        base_url="http://host:port",
        public_url="http://host:port",
        token=TOKEN,
        collection_id=COLLECTION,
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.create_document(config, "제목", "# 본문")

    assert "연결하지 못했습니다" in str(excinfo.value)
    assert TOKEN not in str(excinfo.value)


def test_config_public_url_defaults_to_the_base_url(monkeypatch) -> None:
    """공개 주소를 안 주면 연결 주소를 그대로 쓴다.

    주소가 하나뿐인 흔한 구성에서는 설정이 늘지 않아야 한다.
    """
    set_env(monkeypatch)

    config = outline.config_from_env()

    assert config is not None
    assert config.public_url == BASE_URL


def test_config_reads_a_separate_public_url(monkeypatch) -> None:
    """주면 그 값이 공개 주소가 된다. 연결 주소는 그대로다."""
    set_env(monkeypatch, public_url=PUBLIC_URL)

    config = outline.config_from_env()

    assert config is not None
    assert config.base_url == BASE_URL
    assert config.public_url == PUBLIC_URL


def test_config_drops_the_trailing_slash_of_the_public_url(
    monkeypatch,
) -> None:
    """공개 주소의 끝 슬래시도 여기서 한 번 뗀다."""
    set_env(monkeypatch, public_url=PUBLIC_URL + "/")

    config = outline.config_from_env()

    assert config is not None
    assert config.public_url == PUBLIC_URL


def test_config_without_a_base_url_is_none_even_with_a_public_url(
    monkeypatch,
) -> None:
    """공개 주소만 있어서는 설정이 되지 않는다. 붙을 곳이 없다."""
    set_env(monkeypatch, base_url="", public_url=PUBLIC_URL)

    assert outline.config_from_env() is None


def test_create_document_builds_the_link_from_the_public_url() -> None:
    """상대 경로는 공개 주소를 앞에 붙여 절대 URL 로 만든다.

    앱이 붙는 곳과 사람이 브라우저로 여는 곳이 다를 수 있다. 저장되는
    링크는 세션이 있는 쪽을 가리켜야 한다.
    """
    document = outline.create_document(
        make_config(public_url=PUBLIC_URL),
        "제목",
        "# 본문",
        poster=fake_poster(made(url="/doc/ai-agents-abc123"), []),
    )

    assert document.url == f"{PUBLIC_URL}/doc/ai-agents-abc123"


def test_create_document_still_posts_to_the_base_url() -> None:
    """공개 주소를 따로 줘도 API 는 연결 주소로 부른다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.create_document(
        make_config(public_url=PUBLIC_URL),
        "제목",
        "# 본문",
        poster=fake_poster(made(), calls),
    )

    assert calls[0][0] == f"{BASE_URL}/api/documents.create"


def test_create_document_keeps_an_absolute_url_over_the_public_url() -> None:
    """Outline 이 절대 URL 을 주면 공개 주소를 붙이지 않는다."""
    document = outline.create_document(
        make_config(public_url=PUBLIC_URL),
        "제목",
        "# 본문",
        poster=fake_poster(made(url="https://wiki.example.com/doc/x"), []),
    )

    assert document.url == "https://wiki.example.com/doc/x"


def fetched(
    doc_id="doc-1",
    title="AI 에이전트의 미래",
    text="- 제목: AI 에이전트의 미래\n\n## 첫 질문\n\n세 가지다.\n",
):
    """documents.info 가 돌려주는 200 응답을 만든다."""
    return httpx.Response(
        200,
        json={"data": {"id": doc_id, "title": title, "text": text}},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.info"),
    )


def failed(status, body=None):
    """오류 응답을 만든다."""
    return httpx.Response(
        status,
        json=body if body is not None else {},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.info"),
    )


def test_fetch_document_posts_to_the_info_endpoint() -> None:
    """주소·헤더·본문이 API 계약대로 나간다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.fetch_document(
        make_config(), "doc-1", poster=fake_poster(fetched(), calls)
    )

    url, kwargs = calls[0]
    assert url == f"{BASE_URL}/api/documents.info"
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert kwargs["json"] == {"id": "doc-1"}
    assert kwargs["timeout"] == outline.FETCH_TIMEOUT


def test_fetch_document_uses_the_connect_url_not_the_public_one() -> None:
    """읽기는 연결 주소로 나간다. 공개 주소는 링크에만 쓴다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.fetch_document(
        make_config(public_url=PUBLIC_URL),
        "doc-1",
        poster=fake_poster(fetched(), calls),
    )

    assert calls[0][0].startswith(BASE_URL)


def test_fetch_document_returns_id_title_and_markdown() -> None:
    """응답에서 셋을 꺼내 온다."""
    document = outline.fetch_document(
        make_config(),
        "doc-1",
        poster=fake_poster(fetched(text="## 첫 질문\n\n세 가지다."), []),
    )

    assert document.id == "doc-1"
    assert document.title == "AI 에이전트의 미래"
    assert document.markdown == "## 첫 질문\n\n세 가지다."


def test_fetch_document_rejects_a_response_without_text() -> None:
    """본문이 없는 응답은 이해하지 못한 것으로 친다."""
    response = httpx.Response(
        200,
        json={"data": {"id": "doc-1", "title": "제목"}},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.info"),
    )

    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(response, [])
        )

    assert "이해하지 못했습니다" in str(error.value)


def test_fetch_document_reports_a_connection_failure() -> None:
    """연결 실패는 httpx 원문이 아니라 우리 문장으로 나간다."""
    boom = httpx.ConnectError("nope")

    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(boom, [])
        )

    assert "연결하지 못했습니다" in str(error.value)
    assert "nope" not in str(error.value)


def test_fetch_document_401_points_at_the_scope_before_the_token() -> None:
    """401 은 scope 를 먼저, 토큰을 나중에 보게 한다.

    실측: scope 밖 엔드포인트를 부르면 403 이 아니라 401 이 온다.
    토큰부터 의심하게 하면 멀쩡한 토큰을 파게 된다.
    """
    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(failed(401), [])
        )

    message = str(error.value)
    assert "documents.info" in message
    assert "토큰" in message
    assert message.index("scope") < message.index("토큰")


def test_fetch_document_403_points_at_the_scope() -> None:
    """403 은 scope 를 짚는다. R4 의 키는 쓰기 전용일 수 있다."""
    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(failed(403), [])
        )

    message = str(error.value)
    assert "scope" in message
    assert "읽기" in message
    # 쓰기 경로의 안내(컬렉션 ID)가 새어 나오면 안 된다.
    assert "컬렉션" not in message


def test_fetch_document_404_says_the_document_may_be_gone() -> None:
    """404 는 위키에서 지워졌을 가능성을 말한다."""
    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(failed(404), [])
        )

    assert "지워졌을" in str(error.value)


def test_fetch_document_keeps_the_outline_detail() -> None:
    """Outline 이 보낸 설명을 함께 싣는다."""
    response = failed(403, {"message": "Authorization error"})

    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(response, [])
        )

    assert "Authorization error" in str(error.value)


def test_fetch_document_drops_a_detail_holding_the_token() -> None:
    """토큰이 섞인 설명은 통째로 버린다."""
    response = failed(403, {"message": f"bad key {TOKEN}"})

    with pytest.raises(outline.OutlineError) as error:
        outline.fetch_document(
            make_config(), "doc-1", poster=fake_poster(response, [])
        )

    assert TOKEN not in str(error.value)
