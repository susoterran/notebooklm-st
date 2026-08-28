"""임시 노트북 정리 테스트."""

import asyncio

from notebooklm_st.services import nlm


class FakeNotebook:
    """가짜 노트북 한 권."""

    def __init__(self, notebook_id, title):
        """필드를 그대로 저장한다."""
        self.id = notebook_id
        self.title = title


class FakeNotebooks:
    """가짜 노트북 API."""

    def __init__(self, calls, existing):
        """호출 기록과 기존 노트북 목록을 저장한다."""
        self._calls = calls
        self._existing = existing

    async def create(self, title):
        """노트북 생성을 기록하고 새 가짜 노트북을 돌려준다."""
        self._calls.append(("create", title))
        return FakeNotebook("nb-new", title)

    async def delete(self, notebook_id):
        """삭제를 기록한다."""
        self._calls.append(("delete", notebook_id))

    async def list(self):
        """조회를 기록하고 기존 노트북 목록을 돌려준다."""
        self._calls.append(("list",))
        return list(self._existing)


class FakeClient:
    """가짜 NotebookLM 클라이언트."""

    def __init__(self, calls, existing=()):
        """가짜 노트북 API 를 준비한다."""
        self.notebooks = FakeNotebooks(calls, list(existing))
        self.sources = None
        self.chat = None

    async def __aenter__(self):
        """자신을 그대로 돌려준다."""
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        """예외를 삼키지 않는다."""
        return False


def test_list_temp_notebooks_keeps_only_the_prefixed_ones():
    """제목이 tmp- 로 시작하는 노트북만 고른다."""
    calls = []
    client = FakeClient(
        calls,
        existing=[
            FakeNotebook("nb-1", "tmp-abc12345"),
            FakeNotebook("nb-2", "내 연구 노트"),
            FakeNotebook("nb-3", "tmp-def67890"),
        ],
    )
    found = asyncio.run(nlm.list_temp_notebooks(lambda: client))
    assert [item.id for item in found] == ["nb-1", "nb-3"]
    assert [item.title for item in found] == ["tmp-abc12345", "tmp-def67890"]


def test_list_temp_notebooks_is_empty_when_nothing_matches():
    """일치하는 노트북이 없으면 빈 목록을 돌려준다."""
    calls = []
    client = FakeClient(calls, existing=[FakeNotebook("nb-2", "내 연구 노트")])
    assert asyncio.run(nlm.list_temp_notebooks(lambda: client)) == []


def test_delete_notebooks_deletes_each_and_counts():
    """주어진 노트북을 모두 지우고 개수를 센다."""
    calls = []
    client = FakeClient(calls)
    deleted = asyncio.run(
        nlm.delete_notebooks(["nb-1", "nb-3"], lambda: client)
    )
    assert deleted == 2
    assert calls == [("delete", "nb-1"), ("delete", "nb-3")]


def test_delete_notebooks_handles_an_empty_list():
    """빈 목록이면 아무것도 지우지 않는다."""
    calls = []
    assert asyncio.run(nlm.delete_notebooks([], lambda: FakeClient(calls))) == 0
    assert calls == []
