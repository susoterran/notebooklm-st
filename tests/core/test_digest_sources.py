"""정리 지시 앞에 붙는 소스 목록 테스트."""

from notebooklm_st.core import digest_sources

INSTRUCTION = "상충하는 지점마다 출처를 밝혀 정리해 줘"


def test_intro_is_the_agreed_wording() -> None:
    """안내 문장이 정한 문구 그대로다."""
    assert digest_sources.INTRO == (
        "이 노트북의 소스 목록입니다. 소스를 가리킬 때는 아래 S 번호만 쓰고,"
        " 번호를 새로 매기거나 바꾸지 마세요. 소스 패널의 이름과 아래"
        " 이름이 조금 달라도 가장 비슷한 소스로 대응시키세요."
    )


def test_prompt_is_the_list_a_blank_line_and_the_instruction() -> None:
    """머리 줄·안내·목록 뒤에 빈 줄 하나를 두고 지시가 온다."""
    prompt = digest_sources.prepend("지시", ["가", "나"])

    assert prompt == (
        f"[소스 목록]\n{digest_sources.INTRO}\n- S1: 가\n- S2: 나\n\n지시"
    )


def test_sources_are_numbered_in_the_given_order() -> None:
    """S 번호는 주어진 순서대로 1 부터 매긴다."""
    prompt = digest_sources.prepend(
        INSTRUCTION, ["첫 글", "둘째 글", "셋째 글"]
    )

    lines = prompt.splitlines()
    assert lines[2:5] == ["- S1: 첫 글", "- S2: 둘째 글", "- S3: 셋째 글"]


def test_instruction_is_kept_verbatim() -> None:
    """사람이 고른 지시는 공백·줄바꿈까지 손대지 않는다."""
    instruction = "  첫 줄\n\n둘째 줄  "

    prompt = digest_sources.prepend(instruction, ["가"])

    assert prompt.endswith("- S1: 가\n\n" + instruction)


def test_title_is_folded_into_one_line() -> None:
    """제목의 줄바꿈·제어문자가 목록 한 줄을 두 동강 내지 않는다."""
    prompt = digest_sources.prepend(INSTRUCTION, ["첫 줄\n둘째 줄\x85끝"])

    assert "- S1: 첫 줄 둘째 줄끝" in prompt.splitlines()
