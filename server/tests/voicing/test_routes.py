import io
import json
import os
import wave
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.library import Library
from simile.voicing.greetings import GREETINGS, files, players

POOL = Path(__file__).resolve().parents[3] / "content" / "characters" / "pool"
PREMADE = "abena_asamoah"


def clip(seconds: float = 6.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x01\x00" * int(seconds * 24000))
    return buffer.getvalue()


@pytest.fixture
def library(tmp_path: Path) -> Library:
    premade = json.loads((POOL / f"{PREMADE}.json").read_text())
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / f"{PREMADE}.json").write_text(json.dumps(premade))
    library = Library(tmp_path / "library", pool)
    library.create(premade | {"id": "wren_abernethy", "name": "Wren Abernethy", "source": "player"})
    return library


@pytest.fixture
def client(make_package: Callable[[dict[str, str]], str], library: Library) -> Iterator[TestClient]:
    package = make_package({"voicing/routes.py": "from simile.voicing.routes import routes\n"})
    app = create_app(package)
    app.state.library = library
    with TestClient(app) as client:
        yield client


def greet(library: Library, id: str, count: int = 3) -> list[Path]:
    folder = players(library)
    folder.mkdir(parents=True, exist_ok=True)
    for n in range(1, count + 1):
        (folder / f"{id}_{n}.m4a").write_bytes(f"greeting {n}".encode())
    return files(folder, id)


def test_lists_a_residents_greetings(client: TestClient) -> None:
    listed = client.get("/api/greetings/tobias").json()

    assert listed == {
        "greetings": [f"/api/greetings/tobias/{path.name}" for path in files(GREETINGS, "tobias")]
    }
    assert len(listed["greetings"]) >= 3


def test_serves_a_greeting(client: TestClient) -> None:
    response = client.get("/api/greetings/kofi/kofi_2.m4a")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert response.content == (GREETINGS / "kofi_2.m4a").read_bytes()


@pytest.mark.parametrize(
    "path",
    [
        "/api/greetings/kofi/kofi_9.m4a",
        "/api/greetings/kofi/tobias_1.m4a",
        "/api/greetings/kofi/..%2Flines.json",
        "/api/greetings/nobody/nobody_1.m4a",
        "/api/greetings/Kofi/kofi_1.m4a",
    ],
)
def test_serves_nothing_else(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_someone_without_greetings_has_none(client: TestClient) -> None:
    assert client.get("/api/greetings/nobody").json() == {"greetings": []}
    assert client.get(f"/api/greetings/{PREMADE}").json() == {"greetings": []}
    assert client.get("/api/greetings/Not-An-Id").json() == {"greetings": []}


def test_a_player_character_has_greetings_once_made_for_its_voice(
    client: TestClient, library: Library
) -> None:
    made = greet(library, "wren_abernethy")
    assert client.get("/api/greetings/wren_abernethy").json() == {"greetings": []}

    library.save_clip("wren_abernethy", clip())
    clip_changed = library.clip(library.get("wren_abernethy")).stat().st_mtime_ns
    for path in made:
        os.utime(path, ns=(clip_changed - 10**9, clip_changed - 10**9))
    assert client.get("/api/greetings/wren_abernethy").json() == {"greetings": []}

    made = greet(library, "wren_abernethy")
    listed = client.get("/api/greetings/wren_abernethy").json()["greetings"]
    assert listed == [f"/api/greetings/wren_abernethy/wren_abernethy_{n}.m4a" for n in (1, 2, 3)]
    response = client.get(listed[1])
    assert response.content == b"greeting 2"
