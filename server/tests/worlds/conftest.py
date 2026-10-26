import io
import wave
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.characters.pool import load_pool
from simile.library import Library
from simile.schema import Character
from simile.worlds import Worlds

POOL = [c.id for c in load_pool()]


def clip(seconds: float = 0.5, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x01\x00" * int(seconds * rate))
    return buffer.getvalue()


@pytest.fixture(scope="session")
def pool() -> list[Character]:
    return load_pool()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "worlds"


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(tmp_path / "library")


@pytest.fixture
def app(make_package: Callable[[dict[str, str]], str], root: Path, library: Library) -> Starlette:
    routes = {"worlds/routes.py": "from simile.worlds.routes import routes\n"}
    app = create_app(make_package(routes))
    app.state.worlds = Worlds(root)
    app.state.library = library
    return app


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def folders(root: Path) -> list[str]:
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


def files(folder: Path) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
