import io
import wave
from collections.abc import Iterator

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.library import Library
from simile.voice import FakeSynthesiser, VoiceService
from simile.voicelib.voices import VOICES

from .conftest import LINE, clip

TRY = "/api/characters/wren_abernethy/voice/try"
SAID = "Put the kettle on, would you, and mind the cat."


@pytest.fixture
def synthesiser() -> FakeSynthesiser:
    return FakeSynthesiser(chunks=3)


@pytest.fixture
def voiced(app: Starlette, synthesiser: FakeSynthesiser) -> Iterator[TestClient]:
    with TestClient(app) as client:
        service = VoiceService(synthesiser)
        client.portal.call(service.__aenter__)
        app.state.voice = service
        try:
            yield client
        finally:
            client.portal.call(service.__aexit__, None, None, None)


def frames(audio: bytes) -> tuple[int, int, bytes]:
    with wave.open(io.BytesIO(audio)) as reader:
        return reader.getframerate(), reader.getnchannels(), reader.readframes(reader.getnframes())


def test_try_it_speaks_through_the_voice_service(
    voiced: TestClient, library: Library, synthesiser: FakeSynthesiser
) -> None:
    library.save_clip("wren_abernethy", clip())

    response = voiced.post(TRY, json={"line": f"  {SAID} "})

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "audio/wav"
    pcm = b"".join(FakeSynthesiser.chunk(index) for index in range(3))
    assert frames(response.content) == (24000, 1, pcm)
    assert synthesiser.started == [SAID]
    path, transcript = synthesiser.voices["try/wren_abernethy"]
    assert path == library.clip(library.get("wren_abernethy")).resolve()
    assert transcript == LINE


def test_a_new_clip_is_given_to_the_voice_service(
    voiced: TestClient, library: Library, synthesiser: FakeSynthesiser
) -> None:
    library.save_clip("wren_abernethy", clip())
    voiced.post(TRY, json={"line": SAID})
    synthesiser.voices.clear()
    voiced.post(TRY, json={"line": SAID})
    assert synthesiser.voices == {}

    voiced.post("/api/characters/wren_abernethy/voice/pick", json={"library": "tobias"})
    voiced.post(TRY, json={"line": SAID})

    path, transcript = synthesiser.voices["try/wren_abernethy"]
    assert transcript == (VOICES / "tobias.txt").read_text().strip()


def test_a_premade_character_can_be_tried(
    voiced: TestClient, library: Library, synthesiser: FakeSynthesiser
) -> None:
    premade = library.get("tobiah_rennick")
    voice = premade.voice.model_copy(update={"reference_clip": "content/voices/kofi.wav"})
    library.premade["tobiah_rennick"] = premade.model_copy(update={"voice": voice})

    response = voiced.post("/api/characters/tobiah_rennick/voice/try", json={"line": SAID})

    assert response.status_code == 200
    assert synthesiser.voices["try/tobiah_rennick"][0] == VOICES / "kofi.wav"


def test_a_character_without_a_voice_cant_be_tried(voiced: TestClient) -> None:
    response = voiced.post(TRY, json={"line": SAID})

    assert response.status_code == 409
    assert response.json() == {"error": "Wren Abernethy has no voice yet"}


@pytest.mark.parametrize(
    ("line", "error"),
    [("  ", "line: can't be blank"), ("x" * 301, "line: String should have at most")],
)
def test_a_bad_line_is_refused(voiced: TestClient, library: Library, line: str, error: str) -> None:
    library.save_clip("wren_abernethy", clip())

    response = voiced.post(TRY, json={"line": line})

    assert response.status_code == 422
    assert response.json()["error"].startswith(error)


def test_without_the_voice_model_try_it_says_why(client: TestClient) -> None:
    response = client.post(TRY, json={"line": SAID})

    assert response.status_code == 503
    assert response.json()["error"].startswith("Try it needs the voice model")
