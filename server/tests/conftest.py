import importlib.util
import platform
import sys

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
