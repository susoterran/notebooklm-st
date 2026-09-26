"""사이드카 모듈이 앱 의존성을 끌어오지 않는지."""

import subprocess
import sys


def test_sidecar_modules_import_nothing_from_the_app() -> None:
    """사이드카 이미지에는 streamlit·notebooklm_st 의 나머지가 없다."""
    code = (
        "import sys\n"
        "import notebooklm_st.login_browser.supervisor\n"
        "roots = {'notebooklm_st', 'streamlit', 'notebooklm'}\n"
        "names = sorted(m for m in sys.modules"
        " if m.split('.')[0] in roots)\n"
        "print(','.join(names))\n"
    )

    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert set(out.split(",")) == {
        "notebooklm_st",
        "notebooklm_st.core",
        "notebooklm_st.core.login_protocol",
        "notebooklm_st.login_browser",
        "notebooklm_st.login_browser.supervisor",
    }
