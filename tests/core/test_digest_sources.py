"""정리본 소스에 S 번호를 매기는 순수 함수 테스트."""

from notebooklm_st.core import digest_sources

INSTRUCTION = "상충하는 지점마다 출처를 밝혀 정리해 줘"


def test_rule_is_the_agreed_wording() -> None:
    """머리 줄 뒤의 규칙이 정한 문구 그대로다."""
    assert digest_sources.RULE == (
        "소스 패널의 각 소스 이름은 S1, S2… 번호로 시작합니다. 소스를"
        " 가리킬 때는 이 S 번호만 쓰고, 번호를 새로 매기거나 바꾸지"
        " 마세요."
    )


def test_prompt_is_the_header_the_rule_and_the_instruction() -> None:
    """머리 줄·규칙 뒤에 빈 줄 하나를 두고 지시가 온다."""
    prompt = digest_sources.prepend("지시")

    assert prompt == f"[소스 목록]\n{digest_sources.RULE}\n\n지시"


def test_instruction_is_kept_verbatim() -> None:
    """사람이 고른 지시는 공백·줄바꿈까지 손대지 않는다."""
    instruction = "  첫 줄\n\n둘째 줄  "

    prompt = digest_sources.prepend(instruction)

    assert prompt.endswith(f"{digest_sources.RULE}\n\n{instruction}")


def test_source_title_starts_with_its_number() -> None:
    """소스 이름 앞에 S 번호가 붙는다."""
    assert digest_sources.source_title(3, "요약 C") == "S3: 요약 C"


def test_source_title_is_folded_into_one_line() -> None:
    """제목의 줄바꿈·제어문자가 소스 이름에 남지 않는다."""
    title = digest_sources.source_title(1, "첫 줄\n둘째 줄\x85끝")

    assert title == "S1: 첫 줄 둘째 줄끝"
