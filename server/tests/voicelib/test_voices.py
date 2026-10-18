import hashlib
import json
import subprocess
import sys
import wave

from starlette.testclient import TestClient

from simile.library import Library
from simile.voicelib.voices import LIBRARY, VOICES, tags

PICK = "/api/characters/wren_abernethy/voice/pick"


def digests() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(VOICES.rglob("*"))
        if path.is_file()
    }


def test_tags_every_residents_clip() -> None:
    residents = json.loads((VOICES / "imported.json").read_text()).keys()

    assert tags().keys() == residents
    for id in tags():
        with wave.open(str(VOICES / f"{id}.wav")) as audio:
            assert audio.getframerate() == 24000
        assert (VOICES / f"{id}.txt").read_text().strip()


def test_tags_only_the_imported_voices() -> None:
    imported = json.loads((VOICES / "imported.json").read_text())

    assert json.loads(LIBRARY.read_text()).keys() == imported.keys()


def test_lists_the_library(client: TestClient) -> None:
    listed = client.get("/api/voices").json()

    henrietta = next(voice for voice in listed if voice["id"] == "henrietta")
    assert henrietta == {
        "id": "henrietta",
        "accent": "Scottish",
        "age": "older",
        "gender": "woman",
        "reference_line": (VOICES / "henrietta.txt").read_text().strip(),
        "clip": "/api/voices/henrietta/clip",
    }
    assert len(listed) == len(tags())


def test_plays_a_library_clip(client: TestClient) -> None:
    response = client.get("/api/voices/kofi/clip")

    assert response.headers["content-type"] == "audio/wav"
    assert response.content == (VOICES / "kofi.wav").read_bytes()
    assert client.get("/api/voices/imported/clip").status_code == 404
    assert client.get("/api/voices/..%2Fimported.json/clip").status_code == 404


def test_picking_a_library_voice_copies_its_clip(client: TestClient, library: Library) -> None:
    before = digests()

    picked = client.post(PICK, json={"library": "tobias"})

    assert picked.status_code == 200, picked.text
    character = library.get("wren_abernethy")
    assert library.clip(character).read_bytes() == (VOICES / "tobias.wav").read_bytes()
    assert character.voice.reference_line == (VOICES / "tobias.txt").read_text().strip()
    assert character.voice.reference_clip == "clips/wren_abernethy.wav"
    assert digests() == before


def test_picking_an_unknown_library_voice_is_404(client: TestClient) -> None:
    response = client.post(PICK, json={"library": "rates"})

    assert response.status_code == 404
    assert response.json() == {"error": "There's no 'rates' voice in the library"}


def test_starting_the_server_loads_no_voice_model() -> None:
    code = (
        "import sys; import simile.voicelib, simile.voicelib.routes, simile.voicelib.lifespan; "
        "print(sorted(m for m in ('mlx', 'mlx_audio', 'torch', 'numpy', 'simile.voice.qwen') "
        "if m in sys.modules))"
    )
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert loaded.stdout.strip() == "[]", loaded.stderr
