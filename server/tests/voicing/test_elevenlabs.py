import importlib.util
import json
import logging
import secrets
import shutil
import subprocess
import threading
import traceback
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.clinic.doctor import load_doctor
from simile.npc import NPCS_DIR, load_npcs
from simile.voicing import eleven, gpu, greetings, speak
from simile.voicing.eleven import ElevenLabs, FakeElevenLabs, Refused
from simile.voicing.greetings import Engine, files, load_chosen, load_made

residents = [*load_npcs(NPCS_DIR), load_doctor()]
KEYCHAIN = eleven._keychain
TOBIAS = [{"text": "Hello there."}, {"text": "A word, if you would."}]
ALDER = {"voice": "alder", "name": "Alder", "accent": "Irish", "delivery": "[slowly]"}


def test_every_resident_and_the_doctor_has_a_library_voice() -> None:
    chosen = load_chosen()

    assert chosen.keys() == {npc.id for npc in residents}
    assert len({voice.voice for voice in chosen.values()}) == len(chosen)
    assert len({voice.accent for voice in chosen.values()}) >= 10
    assert {"New Zealand", "Irish", "Danish", "Singaporean", "Cook Islands", "South African"} <= {
        voice.accent for voice in chosen.values()
    }
    assert chosen["annelie"].accent == "South African"


def test_the_key_comes_from_the_environment_or_the_keychain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = []

    def keychain(*flags: str, timeout: float = eleven.KEYCHAIN_TIMEOUT) -> Any:
        asked.append((flags, timeout))
        return subprocess.CompletedProcess([], 0, stdout="sk-keychain\n" if flags else "")

    monkeypatch.setattr(eleven, "_keychain", keychain)
    assert eleven.configured()
    assert eleven.api_key(timeout=60) == "sk-keychain"
    assert asked == [((), eleven.KEYCHAIN_TIMEOUT), (("-w",), 60)]
    monkeypatch.setenv(eleven.ENV, " sk-environment ")
    assert eleven.api_key() == "sk-environment"
    assert eleven.configured()
    monkeypatch.setattr(eleven, "_keychain", lambda *flags, **options: None)
    monkeypatch.delenv(eleven.ENV)
    assert eleven.api_key() is None
    assert not eleven.configured()


def test_a_keychain_that_doesnt_answer_counts_as_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    waited = []

    def stuck(command: list[str], **options: Any) -> None:
        waited.append(options["timeout"])
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(eleven, "_keychain", KEYCHAIN)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(subprocess, "run", stuck)

    assert not eleven.configured()
    assert eleven.api_key() is None
    assert waited == [eleven.KEYCHAIN_TIMEOUT] * 2
    assert eleven.KEYCHAIN_TIMEOUT <= 2


def test_says_a_line_in_a_library_voice_with_v4() -> None:
    fake = FakeElevenLabs()

    audio = fake.say("alder", "[slowly] Hello there.", 42)

    assert fake.said == [("alder", "[slowly] Hello there.", 42)]
    assert audio.dtype == np.float32 and len(audio) == speak.SAMPLE_RATE
    assert 0.29 <= np.abs(audio).max() <= 0.31
    assert fake.credits == 7


def test_a_refusal_says_why() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"message": "missing permission"}})

    client = ElevenLabs("sk-secret", transport=httpx.MockTransport(refuse))

    with pytest.raises(Refused, match="401: missing permission") as refused:
        client.say("alder", "Hello.", 1)

    assert "sk-secret" not in str(refused.value)


@pytest.fixture
def here(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Tobias's greetings in `tmp_path`, each encoded as its raw samples."""
    (tmp_path / "lines.json").write_text(json.dumps({"tobias": TOBIAS}))
    (tmp_path / "elevenlabs.json").write_text(json.dumps({"tobias": ALDER}))
    monkeypatch.setattr(greetings, "GREETINGS", tmp_path)
    monkeypatch.setattr(greetings, "LINES", tmp_path / "lines.json")
    monkeypatch.setattr(greetings, "MADE", tmp_path / "made.json")
    monkeypatch.setattr(greetings, "CHOSEN", tmp_path / "elevenlabs.json")
    monkeypatch.setattr(speak, "encode", lambda audio, path: path.write_bytes(audio.tobytes()))
    which = shutil.which
    monkeypatch.setattr(
        shutil, "which", lambda name: "/usr/bin/afconvert" if name == "afconvert" else which(name)
    )
    monkeypatch.setattr(speak, "load", lambda: pytest.fail("loaded V1's model"))
    return tmp_path


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeElevenLabs:
    fake = FakeElevenLabs()

    def client(key: str) -> FakeElevenLabs:
        fake.credits = 0
        return fake

    monkeypatch.setenv(eleven.ENV, "sk-test")
    monkeypatch.setattr(eleven, "ElevenLabs", client)
    return fake


def greet(*args: str) -> str:
    result = CliRunner().invoke(create_cli(), ["greetings", "tobias", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_says_only_the_lines_that_changed(here: Path, fake: FakeElevenLabs) -> None:
    greet()
    first = (here / "tobias_1.m4a").read_bytes()

    assert [text for _, text, _ in fake.said] == [
        "[slowly] Hello there.",
        "[slowly] A word, if you would.",
    ]
    assert {voice for voice, _, _ in fake.said} == {"alder"}
    made = load_made(here / "made.json")["tobias"]
    assert made.engine is Engine.ELEVENLABS and len(made.digests) == 2
    assert "Every greeting is up to date" in greet()
    assert len(fake.said) == 2

    (here / "lines.json").write_text(json.dumps({"tobias": [TOBIAS[0], {"text": "A word."}]}))
    output = greet()

    assert [text for _, text, _ in fake.said[2:]] == ["[slowly] A word."]
    assert "tobias: 'A word.'" in output and "ElevenLabs credits used: 7" in output
    assert (here / "tobias_1.m4a").read_bytes() == first

    (here / "lines.json").write_text(json.dumps({"tobias": [TOBIAS[0]]}))
    greet()

    assert len(fake.said) == 3
    assert [path.name for path in files(here, "tobias")] == ["tobias_1.m4a"]
    assert len(load_made(here / "made.json")["tobias"].digests) == 1


def test_a_new_voice_says_them_all_again(here: Path, fake: FakeElevenLabs) -> None:
    greet()
    (here / "elevenlabs.json").write_text(json.dumps({"tobias": ALDER | {"voice": "paddy"}}))

    greet()

    assert [voice for voice, _, _ in fake.said] == ["alder", "alder", "paddy", "paddy"]


def test_an_audition_says_only_the_first_line(here: Path, fake: FakeElevenLabs) -> None:
    greet("--audition")

    assert [text for _, text, _ in fake.said] == ["[slowly] Hello there."]
    assert len(load_made(here / "made.json")["tobias"].digests) == 1

    greet()

    assert [text for _, text, _ in fake.said[1:]] == ["[slowly] A word, if you would."]


def test_without_a_key_greetings_made_with_elevenlabs_stay(
    here: Path, fake: FakeElevenLabs, monkeypatch: pytest.MonkeyPatch
) -> None:
    greet()
    monkeypatch.delenv(eleven.ENV)

    assert "Every greeting is up to date" in greet()


@pytest.fixture
def v1(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """V1's model, saying each greeting as ones and noting what it said."""
    said: list[str] = []
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: object() if name == "mlx_audio" else find_spec(name, *a),
    )
    monkeypatch.setattr(gpu, "wait_for_gpu", lambda echo: None)
    monkeypatch.setattr(speak, "load", lambda: "model")
    monkeypatch.setattr(
        speak,
        "cloning",
        lambda model, clip, transcript: lambda text, seed: said.append(text) or np.ones(24000),
    )
    return said


def test_without_a_key_v1_replaces_elevenlabs_greetings_only_with_local(
    here: Path, fake: FakeElevenLabs, v1: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    greet()
    made = (here / "made.json").read_text()
    monkeypatch.delenv(eleven.ENV)

    forced = CliRunner().invoke(create_cli(), ["greetings", "tobias", "--force"])
    monkeypatch.setattr(greetings, "SYNTHESIS", greetings.SYNTHESIS + 1)
    bumped = CliRunner().invoke(create_cli(), ["greetings", "tobias"])

    for refused in (forced, bumped):
        assert refused.exit_code == 1
        assert "would replace greetings made with ElevenLabs: tobias" in refused.output
    assert (here / "made.json").read_text() == made
    assert v1 == []

    greet("--local")

    assert v1 == ["Hello there.", "A word, if you would."]
    assert load_made(here / "made.json")["tobias"].engine is Engine.LOCAL


def test_local_says_them_with_v1_even_with_a_key(
    here: Path, fake: FakeElevenLabs, v1: list[str]
) -> None:
    greet("--local")

    assert fake.said == []
    assert len(v1) == 2


def test_a_refusal_partway_keeps_what_was_said_and_says_what_it_cost(
    here: Path, fake: FakeElevenLabs, monkeypatch: pytest.MonkeyPatch
) -> None:
    say = fake.say

    def out_of_credits(voice: str, text: str, seed: int) -> Any:
        if fake.said:
            raise Refused("ElevenLabs answered 401: quota_exceeded")
        return say(voice, text, seed)

    monkeypatch.setattr(fake, "say", out_of_credits)

    result = CliRunner().invoke(create_cli(), ["greetings", "tobias"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Stopped: ElevenLabs answered 401: quota_exceeded" in result.output
    assert "ElevenLabs credits used: 7" in result.output
    assert "Traceback" not in result.output
    assert len(load_made(here / "made.json")["tobias"].digests) == 1


def test_with_a_key_greetings_made_with_v1_are_said_again(here: Path, fake: FakeElevenLabs) -> None:
    tobias = next(npc for npc in residents if npc.id == "tobias")
    made = load_made(here / "made.json")
    lines = greetings.load_lines()["tobias"]
    greetings.record(tobias, lines, made, Engine.LOCAL, None, lambda t, s: np.ones(24000), here)
    assert load_made(here / "made.json")["tobias"].engine is Engine.LOCAL

    greet()

    assert len(fake.said) == 2
    assert load_made(here / "made.json")["tobias"].engine is Engine.ELEVENLABS


class Api(BaseHTTPRequestHandler):
    """ElevenLabs on localhost: says lines in `alder` and refuses any other voice."""

    keys: list[str] = []

    def do_POST(self) -> None:
        self.keys.append(self.headers["xi-api-key"])
        self.rfile.read(int(self.headers["content-length"]))
        if self.path.startswith("/v1/text-to-speech/alder"):
            body = (np.ones(12_000) * 8000).astype("<i2").tobytes()
            self.send_response(200)
            self.send_header("character-cost", "9")
        else:
            body = json.dumps({"detail": {"message": "voice_not_found"}}).encode()
            self.send_response(404)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Api)
    Api.keys = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(eleven, "API", f"http://127.0.0.1:{server.server_port}")
    yield Api.keys
    server.shutdown()


def test_the_key_never_reaches_a_log(
    here: Path,
    api: list[str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    key = f"sk_{secrets.token_hex(24)}"
    monkeypatch.setenv(eleven.ENV, key)
    caplog.set_level(logging.DEBUG)

    made = CliRunner().invoke(create_cli(), ["greetings", "tobias"])
    (here / "elevenlabs.json").write_text(json.dumps({"tobias": ALDER | {"voice": "nobody"}}))
    refused = CliRunner().invoke(create_cli(), ["greetings", "tobias"])

    assert made.exit_code == 0, made.output
    assert refused.exit_code == 1
    assert "Stopped: ElevenLabs answered 404: voice_not_found" in refused.output
    assert api == [key] * 3
    printed = capfd.readouterr()
    everything = [
        caplog.text,
        made.output,
        refused.output,
        "".join(traceback.format_exception(refused.exception)),
        printed.out,
        printed.err,
        *(path.read_bytes().decode(errors="replace") for path in here.iterdir()),
    ]
    assert caplog.records
    assert all(key not in text for text in everything)


VOICES = [
    {
        "voice_id": "isla",
        "name": "Isla",
        "accent": "scottish",
        "gender": "female",
        "age": "middle_aged",
        "use_case": "conversational",
        "description": "Born and raised in Scotland.",
    },
    {
        "voice_id": "morag",
        "name": "Morag",
        "accent": "scottish",
        "gender": "female",
        "age": "middle_aged",
        "use_case": "narrative_story",
        "description": "Storyteller from Scotland.",
    },
    {
        "voice_id": "brian",
        "name": "Brian",
        "accent": "american",
        "gender": "male",
        "age": "old",
        "use_case": "narrative_story",
        "description": "Warm.",
    },
]


def test_a_new_character_gets_a_library_voice_from_where_their_accent_is() -> None:
    fake = FakeElevenLabs(voices=VOICES)

    scot = fake.choose("wren", "female", "middle_aged", ["Fife", "Scotland"])
    american = fake.choose("ada", "male", "old", ["Atlantis"])

    assert scot is not None and scot["voice_id"] in {"isla", "morag"}
    assert scot == fake.choose("wren", "female", "middle_aged", ["Fife", "Scotland"])
    assert american is not None and american["voice_id"] == "brian"
    assert fake.searched[0]["accent"] == "fife"
    assert fake.choose("cy", "male", "young", ["Atlantis"]) is not None
    assert FakeElevenLabs().choose("cy", "male", "young", []) is None


def test_a_search_hit_has_to_name_the_place() -> None:
    voices = [
        {"name": "Shana", "accent": "british", "description": "Clear."},
        {"name": "Kofi", "accent": "british", "description": "A Ghana-born voice."},
    ]

    assert [voice["name"] for voice in eleven._naming("Ghana", voices)] == ["Kofi"]


def test_reads_the_accent_and_age_band_from_a_character() -> None:
    assert eleven.places("A heavy Cook Islands accent. A man in his forties.", "Rarotonga") == [
        "Cook Islands",
        "Rarotonga",
    ]
    assert eleven.places("A Fife accent. Low and even.", "Scotland") == ["Fife", "Scotland"]
    assert eleven.places("An auntie from Mumbai speaking Indian English.", "India") == [
        "Indian",
        "India",
    ]
    assert eleven.places("Low and even.", "Ghana") == ["Ghana"]
    assert [eleven.age_band(age) for age in (21, 35, 59, 60, 75)] == [
        "young",
        "middle_aged",
        "middle_aged",
        "old",
        "old",
    ]


def test_the_job_says_the_lines_in_the_voice_it_chose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = {
        "voice": "wren",
        "lines": ["Hi!", "Hello there."],
        "delivery": "[warmly]",
        "elevenlabs": None,
        "gender": "female",
        "age": "middle_aged",
        "places": ["Fife", "Scotland"],
        "said": str(tmp_path / "said"),
    }
    (tmp_path / "greetings.json").write_text(json.dumps(asked))
    fake = FakeElevenLabs(voices=VOICES)
    monkeypatch.setenv(eleven.ENV, "sk-test")
    monkeypatch.setattr(eleven, "ElevenLabs", lambda key: fake)
    monkeypatch.setattr(speak, "encode", lambda audio, path: path.write_bytes(b"m4a"))

    eleven.main([str(tmp_path)])

    voice = fake.said[0][0]
    assert voice in {"isla", "morag"}
    assert [(v, text) for v, text, _ in fake.said] == [
        (voice, "[warmly] Hi!"),
        (voice, "[warmly] Hello there."),
    ]
    spoken = json.loads((tmp_path / "spoken.json").read_text())
    assert spoken == {
        "seconds": spoken["seconds"],
        "voice": {"isla": "Isla", "morag": "Morag"}[voice],
        "credits": 14,
    }
    assert [path.name for path in files(tmp_path, "wren")] == ["wren_1.m4a", "wren_2.m4a"]
    assert '"progress": 0.5' in capsys.readouterr().out
    assert [path.name for path in files(tmp_path / "said", "wren")] == ["wren_1.m4a", "wren_2.m4a"]
    assert json.loads((tmp_path / "said" / "spoken.json").read_text()) == spoken


def test_the_job_says_a_voice_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    said, work = tmp_path / "said", tmp_path / "work"
    said.mkdir()
    work.mkdir()
    (said / "wren_1.m4a").write_bytes(b"said before")
    (said / "spoken.json").write_text(json.dumps({"seconds": [1.2], "voice": "Isla", "credits": 7}))
    (work / "greetings.json").write_text(
        json.dumps({"voice": "wren", "lines": ["Hi!"], "said": str(said)})
    )
    fake = FakeElevenLabs()
    monkeypatch.setattr(eleven, "ElevenLabs", lambda key: fake)

    eleven.main([str(work)])

    assert fake.said == []
    assert (work / "wren_1.m4a").read_bytes() == b"said before"
    spoken = json.loads((work / "spoken.json").read_text())
    assert spoken == {"seconds": [1.2], "voice": "Isla", "credits": 0}


def test_the_job_says_them_in_a_library_residents_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = {
        "voice": "wren",
        "lines": ["Hi!"],
        "delivery": "",
        "elevenlabs": {"voice_id": "alder", "name": "Alder"},
        "gender": None,
        "age": "old",
        "places": [],
        "said": str(tmp_path / "said"),
    }
    (tmp_path / "greetings.json").write_text(json.dumps(asked))
    fake = FakeElevenLabs()
    monkeypatch.setenv(eleven.ENV, "sk-test")
    monkeypatch.setattr(eleven, "ElevenLabs", lambda key: fake)
    monkeypatch.setattr(speak, "encode", lambda audio, path: path.write_bytes(b"m4a"))

    eleven.main([str(tmp_path)])

    assert fake.said == [("alder", "Hi!", speak.seed(0, "wren", "Hi!"))]
    assert fake.searched == []


def test_the_job_without_a_key_says_so(tmp_path: Path) -> None:
    asked = {"voice": "wren", "lines": ["Hi!"], "said": str(tmp_path / "said")}
    (tmp_path / "greetings.json").write_text(json.dumps(asked))

    with pytest.raises(SystemExit, match="No ElevenLabs key"):
        eleven.main([str(tmp_path)])


def test_levels_a_quiet_greeting_without_clipping() -> None:
    rate = speak.SAMPLE_RATE
    quiet = (0.01 * np.sin(np.linspace(0, 2 * np.pi * 220, rate))).astype(np.float32)
    spiky = quiet.copy()
    spiky[100] = 0.5

    loud = speak.level(quiet)
    capped = speak.level(spiky)

    rms = float(np.sqrt((loud**2).mean()))
    assert rms == pytest.approx(speak.LOUDNESS, rel=0.05)
    assert np.abs(capped).max() == pytest.approx(speak.CEILING, rel=0.01)
    assert len(speak.level(np.zeros(10, dtype=np.float32))) == 10


def test_ci_never_reaches_elevenlabs() -> None:
    assert eleven.api_key() is None
    assert not eleven.configured()
    assert eleven.API == "http://elevenlabs.invalid"
