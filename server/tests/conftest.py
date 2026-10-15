import importlib.util
import platform
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest


def apple_silicon_with_mlx() -> bool:
    return (
        sys.platform == "darwin"
        and platform.machine() == "arm64"
        and importlib.util.find_spec("mlx") is not None
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if apple_silicon_with_mlx():
        return
    skip = pytest.mark.skip(reason="needs macOS on Apple Silicon with MLX installed")
    for item in items:
        if item.get_closest_marker("mlx"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def in_memory_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_DB", ":memory:")


@pytest.fixture
def make_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[dict[str, str]], str]:
    """Write an importable throwaway package from {relative path: source}; returns its name."""
    monkeypatch.syspath_prepend(tmp_path)

    def make(files: dict[str, str]) -> str:
        name = f"fake_{uuid.uuid4().hex}"
        root = tmp_path / name
        for path, source in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(source)
        for folder in [root, *(p for p in root.rglob("*") if p.is_dir())]:
            (folder / "__init__.py").touch()
        return name

    return make
