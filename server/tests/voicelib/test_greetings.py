import json
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.jobs import Jobs
from simile.library import Library
from simile.voicelib import greetings
from simile.voicelib.greetings import GREET, Greet
from simile.voicing import eleven
from simile.voicing.greetings import GREETINGS, files, lines_for, load_chosen, players

from .conftest import finished

FAKE = Path(__file__).with_name("fake_greetings.py")
PICK = "/api/characters/wren_abernethy/voice/pick"


@pytest.fixture
def job_here(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(params: Greet, work: Path) -> list[str]:
        return [sys.executable, str(FAKE), str(work)]

    for needs, command in (("NEEDS", "command"), ("ELEVENLABS_NEEDS", "elevenlabs_command")):
        monkeypatch.setattr(greetings, needs, ())
        monkeypatch.setattr(greetings, command, fake)


def greeting_jobs(client: TestClient) -> list[dict]:
    return [job for job in client.get("/api/jobs").json() if job["kind"] == GREET]


def made(library: Library) -> list[str]:
    return [path.read_text() for path in files(players(library), "wren_abernethy")]


def test_setting_a_voice_records_the_characters_greetings(
    job_here: None, client: TestClient, library: Library
) -> None:
    assert client.post(PICK, json={"library": "tobias"}).status_code == 200

    [job] = greeting_jobs(client)
    job = finished(client, job["id"])

    assert job["state"] == "succeeded", job["error"]
    lines = lines_for(library.get("wren_abernethy"))
    assert made(library) == [f"{line} in wren_abernethy.wav" for line in lines]
    assert job["result"] == {
        "greetings": [
            f"/api/greetings/wren_abernethy/wren_abernethy_{n}.m4a" for n in (1, 2, 3, 4)
        ],
        "lines": lines,
        "seconds": [1.0, 1.1, 1.2, 1.3],
        "stale": False,
        "voice": None,
    }


def test_a_new_voice_drops_the_old_greetings_at_once(
    job_here: None, client: TestClient, library: Library
) -> None:
    folder = players(library)
    folder.mkdir(parents=True)
    (folder / "wren_abernethy_1.m4a").write_text("old voice")
    (folder / "wren_abernethy_5.m4a").write_text("old voice")
    (folder / "ada_1.m4a").write_text("someone else")

    client.post(PICK, json={"library": "kofi"})

    assert not (folder / "wren_abernethy_5.m4a").exists()
    assert (folder / "ada_1.m4a").read_text() == "someone else"
    finished(client, greeting_jobs(client)[0]["id"])
    assert len(made(library)) == 4


def test_without_the_job_a_library_voice_brings_its_residents_greetings(
    client: TestClient, library: Library
) -> None:
    client.post(PICK, json={"library": "henrietta"})

    assert greeting_jobs(client) == []
    copied = files(players(library), "wren_abernethy")
    assert [path.read_bytes() for path in copied] == [
        path.read_bytes() for path in files(GREETINGS, "henrietta")
    ]
    assert len(copied) >= 3


def test_needs_apple_silicon_and_voice_labs_mlx_virtualenv(library: Library) -> None:
    jobs = Jobs(library.root.parent / "jobs", {"apple_silicon": True, "voice_lab_mlx": False})
    jobs.register(greetings.kind(library))

    kind = jobs.capabilities()["kinds"][GREET]

    assert kind["available"] is False
    assert "voice-lab/.venv-mlx" in kind["reason"]


def test_runs_the_speaker_in_voice_labs_mlx_virtualenv(tmp_path: Path) -> None:
    command = greetings.command(Greet(character="wren_abernethy"), tmp_path)

    assert command[0].endswith("voice-lab/.venv-mlx/bin/python")
    assert command[1:] == ["-I", str(greetings.SCRIPT), str(tmp_path)]
    assert greetings.SCRIPT.name == "speak.py"


def test_a_character_without_a_voice_gets_no_greetings(library: Library, tmp_path: Path) -> None:
    prepare = greetings.kind(library).command

    with pytest.raises(Exception, match="has no voice of their own yet"):
        prepare(Greet(character="wren_abernethy"), tmp_path)
    with pytest.raises(Exception, match="has no voice of their own yet"):
        prepare(Greet(character="tobiah_rennick"), tmp_path)


def test_greetings_for_a_voice_changed_since_are_dropped(library: Library, tmp_path: Path) -> None:
    from .conftest import clip

    library.save_clip("wren_abernethy", clip())
    kind = greetings.kind(library)
    work = tmp_path / "work"
    work.mkdir()
    kind.command(Greet(character="wren_abernethy"), work)
    (work / "wren_abernethy_1.m4a").write_text("first voice")
    (work / "spoken.json").write_text(json.dumps({"seconds": [1.0]}))
    library.save_clip("wren_abernethy", clip(sample=2))

    result = kind.publish(Greet(character="wren_abernethy"), work, tmp_path / "out")

    assert result["stale"] is True
    assert result["greetings"] == []
    assert files(players(library), "wren_abernethy") == []


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(eleven.ENV, "sk-test")


def test_with_a_key_elevenlabs_says_them_on_any_mac(
    keyed: None, library: Library, tmp_path: Path
) -> None:
    from .conftest import clip

    library.save_clip("wren_abernethy", clip())
    kind = greetings.kind(library)

    command = kind.command(Greet(character="wren_abernethy"), tmp_path)

    assert kind.requires == ("apple_silicon",)
    assert command == [sys.executable, "-I", "-m", "simile.voicing.eleven", str(tmp_path)]
    asked = json.loads((tmp_path / "greetings.json").read_text())
    assert asked["lines"] == lines_for(library.get("wren_abernethy"))
    assert asked["delivery"].startswith("[")
    assert asked["elevenlabs"] is None
    assert (asked["gender"], asked["age"]) == ("female", "middle_aged")
    assert asked["places"] == ["Fife", "Scotland"]


def test_a_library_voice_brings_its_residents_elevenlabs_voice(
    keyed: None, job_here: None, client: TestClient, library: Library
) -> None:
    client.post(PICK, json={"library": "tobias"})

    job = finished(client, greeting_jobs(client)[0]["id"])

    assert job["result"]["voice"] == load_chosen()["tobias"].name
