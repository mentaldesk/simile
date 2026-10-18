import hashlib
import io
import json
import re
import wave
import zipfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.library import Library
from simile.llm import FakeProvider, LLMClient, Request
from simile.schema import CoreValue

LINE = "The early bus leaves at twenty to seven, and I like to be at the stop by half past."
LOOK = {
    "skin": "#c28569",
    "hair_style": "bob",
    "hair_colour": "#8b9bb4",
    "top_colour": "#3a4466",
    "bottom_colour": "#262b44",
    "shoe_colour": "#262b44",
    "build": "average",
    "accessories": ["glasses"],
}


def character(**changes: Any) -> dict[str, Any]:
    """A fictional player character, as JSON."""
    return {
        "id": "wren_abernethy",
        "name": "Wren Abernethy",
        "birth_year": 1971,
        "gender": "woman",
        "origin": "Scotland",
        "arrival": {"age": 40, "reason": "for a job"},
        "occupation": "Glazier",
        "values": {value.value: 0.5 for value in CoreValue},
        "backstory": "Fits windows in old cottages and refuses to rush a putty line.",
        "persona": "Patient, blunt and quietly proud of straight lines.",
        "speaking_style": "Few words, most of them about weather and glass.",
        "interests": ["stained glass", "hill walking"],
        "past": [{"age": 19, "content": "I cut my first pane.", "salience": 0.5, "valence": 0.4}],
        "hooks": [
            {"kind": "rival", "side": "mutual", "description": "Lost a contract to someone."}
        ],
        "traits": {
            "sociability": 0.4,
            "negativity_bias": 0.5,
            "forgiveness": 0.6,
            "first_impressions": 0.5,
        },
        "appearance": LOOK,
        "voice": {
            "description": "A Fife accent. Low and even.",
            "reference_line": LINE,
            "reference_clip": None,
            "needs_recording": True,
        },
        "craft": {"medium": "mural", "form": "harbour scenes"},
        "source": "player",
        "created": "2026-09-01T10:00:00Z",
        "updated": "2026-09-02T10:00:00Z",
        "version": 2,
    } | changes


PREMADE = character(
    id="tobiah_rennick",
    name="Tobiah Rennick",
    occupation="Postman",
    backstory="Walks the long rural round and knows every dog by name.",
    persona="Cheerful, nosy and never late.",
    source="premade",
)


def clip(seconds: float = 0.5, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x01\x00" * int(seconds * rate))
    return buffer.getvalue()


def archive(files: dict[str, bytes | str], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as zipped:
        for name, content in files.items():
            zipped.writestr(name, content)
    return buffer.getvalue()


def requested(request: Request) -> dict[str, Any]:
    """The JSON Schema `LLMClient.structured` put in the system prompt."""
    return json.loads(request.system.split("no code fence:\n", 1)[1])


def answer(request: Request) -> str:
    """A valid reply to a biography or critic request."""
    critic = request.system.startswith("You edit")
    reply: dict[str, Any] = {}
    for name, spec in requested(request)["properties"].items():
        if name == "notes":
            reply[name] = ["Swapped a stock phrase for something specific."]
        elif name in ("past", "hooks"):
            reply[name] = [f"Written {name} {i}." for i in range(spec["minItems"])]
        elif name == "interests":
            reply[name] = ["bowls", "allotments"]
        elif name == "craft":
            reply[name] = None
        elif name == "voice":
            reply[name] = {"description": "A woman in her fifties.", "reference_line": LINE}
        elif name == "appearance":
            reply[name] = LOOK
        else:
            reply[name] = f"{'Revised' if critic else 'Written'} {name}."
    return json.dumps(reply)


class HashingEmbedder:
    """Bag-of-words vectors: the same words embed the same."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 512
            for word in re.findall(r"\w+", text.lower()):
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 512] += 1
            vectors.append(vector)
        return vectors


@pytest.fixture(autouse=True)
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data" / "library"
    monkeypatch.setenv("SIMILE_LIBRARY", str(root))
    return root


@pytest.fixture
def premade_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "pool"
    directory.mkdir()
    (directory / f"{PREMADE['id']}.json").write_text(json.dumps(PREMADE, indent=2))
    return directory


@pytest.fixture
def replies() -> list[str]:
    return []


@pytest.fixture
def fake(replies: list[str]) -> FakeProvider:
    def reply(request: Request) -> str:
        replies.append(answer(request))
        return replies[-1]

    return FakeProvider(default=reply)


@pytest.fixture
def library(root: Path, premade_dir: Path) -> Library:
    return Library(root, premade_dir, embedder=HashingEmbedder())


@pytest.fixture
def app(
    make_package: Callable[[dict[str, str]], str], library: Library, fake: FakeProvider
) -> Starlette:
    app = create_app(
        make_package({"library/routes.py": "from simile.library.routes import routes\n"})
    )
    app.state.library = library
    app.state.llm = LLMClient(fake)
    return app


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client
