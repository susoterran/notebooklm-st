"""패키지가 import 가능한지 확인한다."""

import notebooklm_st


def test_package_has_docstring():
    """notebooklm_st 패키지에 독스트링이 있는지 확인한다."""
    assert notebooklm_st.__doc__
