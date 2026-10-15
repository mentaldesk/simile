from pathlib import Path

import pytest


def test_mlx_tests_skip_off_apple_silicon(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytester.makeconftest((Path(__file__).parent / "conftest.py").read_text())
    pytester.makeini("[pytest]\nmarkers =\n    mlx: test marker\n")
    pytester.makepyfile(
        "import pytest\n"
        "@pytest.mark.mlx\n"
        "def test_needs_mlx():\n"
        "    raise AssertionError('should have been skipped')\n"
        "def test_plain():\n"
        "    pass\n"
    )
    monkeypatch.setattr("platform.machine", lambda: "x86_64")

    result = pytester.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(passed=1, skipped=1)
