"""Outline 클라이언트 테스트."""

import datetime
import typing

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


def listed_item(doc_id: str, text: str = "- 영상 URL: x\n") -> dict:
    """documents.list 응답의 문서 하나."""
    return {
        "id": doc_id,
        "title": f"제목 {doc_id}",
        "url": f"/doc/{doc_id}",
        "createdAt": "2026-09-25T01:00:00.000Z",
        "text": text,
    }


def page(items: list[dict]) -> httpx.Response:
    """documents.list 가 돌려주는 200 응답."""
    return httpx.Response(
        200,
        json={
            "data": items,
            "pagination": {"limit": 100, "offset": 0, "nextPath": "/x"},
        },
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )


def paged_poster(responses, calls):
    """호출마다 준비된 응답을 차례로 돌려주는 poster 를 만든다."""
    queue = list(responses)

    def post(url, **kwargs):
        """httpx.post 를 대신한다."""
        calls.append((url, kwargs))
        response = queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    return post


def test_list_documents_posts_the_collection_filter() -> None:
    """주소·헤더·본문이 API 계약대로 나간다."""
    calls: list[tuple[str, dict[str, object]]] = []

    outline.list_documents(make_config(), poster=fake_poster(page([]), calls))

    url, kwargs = calls[0]
    assert url == f"{BASE_URL}/api/documents.list"
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN}"}
    assert kwargs["json"] == {
        "filters": [
            {"field": "collectionId", "operator": "eq", "value": COLLECTION}
        ],
        "sort": "createdAt",
        "direction": "DESC",
        "limit": outline.LIST_PAGE_SIZE,
        "offset": 0,
    }
    assert kwargs["timeout"] == outline.FETCH_TIMEOUT


def test_list_documents_returns_listed_documents() -> None:
    """응답의 다섯 값을 꺼내 온다. URL 은 공개 주소로 절대화한다."""
    documents = outline.list_documents(
        make_config(public_url=PUBLIC_URL),
        poster=fake_poster(page([listed_item("doc-1", "본문\n")]), []),
    )

    assert len(documents) == 1
    document = documents[0]
    assert document.id == "doc-1"
    assert document.title == "제목 doc-1"
    assert document.url == f"{PUBLIC_URL}/doc/doc-1"
    assert document.markdown == "본문\n"


def test_list_documents_converts_created_at_to_local_time() -> None:
    """``createdAt`` 이 ``store.now()`` 와 같은 로컬 초 단위 ISO 가 된다."""
    documents = outline.list_documents(
        make_config(), poster=fake_poster(page([listed_item("doc-1")]), [])
    )

    expected = (
        datetime.datetime(2026, 9, 25, 1, 0, 0, tzinfo=datetime.UTC)
        .astimezone()
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )
    assert documents[0].created_at == expected
    assert "+" not in documents[0].created_at
    assert "Z" not in documents[0].created_at


def test_list_documents_follows_offsets_until_a_short_page() -> None:
    """가득 찬 페이지 뒤에는 다음 offset 으로 다시 부른다."""
    full = [listed_item(f"doc-{i}") for i in range(outline.LIST_PAGE_SIZE)]
    calls: list[tuple[str, dict[str, object]]] = []

    documents = outline.list_documents(
        make_config(),
        poster=paged_poster([page(full), page([listed_item("last")])], calls),
    )

    assert len(documents) == outline.LIST_PAGE_SIZE + 1
    assert documents[-1].id == "last"
    offsets = [
        typing.cast("dict[str, object]", c[1]["json"])["offset"] for c in calls
    ]
    assert offsets == [0, outline.LIST_PAGE_SIZE]


def test_list_documents_stops_after_an_empty_page() -> None:
    """빈 페이지가 오면 더 부르지 않는다."""
    calls: list[tuple[str, dict[str, object]]] = []

    documents = outline.list_documents(
        make_config(), poster=paged_poster([page([])], calls)
    )

    assert documents == []
    assert len(calls) == 1


def test_list_documents_gives_up_past_the_page_limit() -> None:
    """가득 찬 페이지가 상한만큼 이어지면 오류다. 무한히 돌지 않는다."""
    full = [listed_item(f"doc-{i}") for i in range(outline.LIST_PAGE_SIZE)]
    responses = [page(full)] * (outline.LIST_PAGE_LIMIT + 1)

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(), poster=paged_poster(responses, [])
        )

    assert "너무" in str(excinfo.value)


def test_list_documents_drops_a_partial_list_when_a_page_fails() -> None:
    """두 번째 페이지가 죽으면 첫 페이지도 버린다.

    반쪽 목록으로 지우지 않는다.
    """
    full = [listed_item(f"doc-{i}") for i in range(outline.LIST_PAGE_SIZE)]
    failure = httpx.Response(
        500,
        json={"message": "boom"},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )

    with pytest.raises(outline.OutlineError):
        outline.list_documents(
            make_config(), poster=paged_poster([page(full), failure], [])
        )


def test_list_documents_rejects_a_response_without_data() -> None:
    """``data`` 가 없으면 이해하지 못한 것이다."""
    response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(make_config(), poster=fake_poster(response, []))

    assert "이해하지 못했습니다" in str(excinfo.value)


def test_list_documents_rejects_an_item_without_text() -> None:
    """본문이 빠진 문서가 하나라도 있으면 목록 전체가 실패다."""
    item = listed_item("doc-1")
    del item["text"]

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(), poster=fake_poster(page([item]), [])
        )

    assert "이해하지 못했습니다" in str(excinfo.value)


def test_list_documents_rejects_an_unreadable_created_at() -> None:
    """날짜로 읽히지 않는 ``createdAt`` 도 목록 전체를 실패시킨다.

    그 문서만 조용히 빠지면 다음 동기화가 그 행을 지운다.
    """
    item = listed_item("doc-1")
    item["createdAt"] = "어제"

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(), poster=fake_poster(page([item]), [])
        )

    assert "이해하지 못했습니다" in str(excinfo.value)


def test_list_documents_accepts_a_created_at_without_a_zone() -> None:
    """접미가 없으면 UTC 로 본다."""
    item = listed_item("doc-1")
    item["createdAt"] = "2026-09-25T01:00:00"

    documents = outline.list_documents(
        make_config(), poster=fake_poster(page([item]), [])
    )

    assert documents[0].created_at.startswith("2026-09-2")


def test_list_documents_reports_a_connection_failure() -> None:
    """연결 실패는 사람이 읽을 문장으로 온다."""
    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(
            make_config(),
            poster=fake_poster(httpx.ConnectError("refused"), []),
        )

    assert "연결하지 못했습니다" in str(excinfo.value)


def list_with(status: int) -> str:
    """오류 상태 코드로 목록을 시도하고 문구를 돌려준다."""
    response = httpx.Response(
        status,
        json={},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )
    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(make_config(), poster=fake_poster(response, []))
    return str(excinfo.value)


def test_list_documents_401_points_at_the_list_scope() -> None:
    """저장·조회만 하던 키에는 목록 scope 가 없다."""
    message = list_with(401)

    assert "documents.list" in message
    assert "documents.info" not in message


def test_list_documents_403_points_at_the_list_scope() -> None:
    """403 도 scope 를 짚는다."""
    assert "documents.list" in list_with(403)


def test_list_documents_404_points_at_the_address() -> None:
    """목록 엔드포인트의 404 는 주소 문제다."""
    assert "주소" in list_with(404)


def test_list_documents_429_asks_to_wait() -> None:
    """요청 한도는 잠시 뒤 다시 시도하라고 한다."""
    assert "잠시" in list_with(429)


def test_list_documents_5xx_carries_the_status() -> None:
    """나머지는 상태 코드를 그대로 보여 준다."""
    assert "502" in list_with(502)


def test_list_documents_never_leaks_the_token() -> None:
    """토큰이 어떤 문구에도 실리지 않는다."""
    response = httpx.Response(
        403,
        json={"message": f"bad token {TOKEN}"},
        request=httpx.Request("POST", f"{BASE_URL}/api/documents.list"),
    )

    with pytest.raises(outline.OutlineError) as excinfo:
        outline.list_documents(make_config(), poster=fake_poster(response, []))

    assert TOKEN not in str(excinfo.value)
