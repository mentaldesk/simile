import dataclasses
import io
import json
import sys
import time
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.jobs import Jobs, jobs_of
from simile.library import Library
from simile.schema import CoreValue
from simile.voicelib import kinds
from simile.voicelib.kinds import VoiceCheck, VoiceDesign, uploads_dir
from simile.voicing import eleven

FAKE_VOICE_JOB = Path(__file__).with_name("fake_voice_job.py")
LINE = "The early bus leaves at twenty to seven, and I like to be at the stop by half past."
TIMEOUT = 15.0


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
        "interests": ["stained glass"],
        "past": [{"age": 19, "content": "I cut my first pane.", "salience": 0.5, "valence": 0.4}],
        "hooks": [{"kind": "rival", "side": "mutual", "description": "Lost a contract."}],
        "traits": {
            "sociability": 0.4,
            "negativity_bias": 0.5,
            "forgiveness": 0.6,
            "first_impressions": 0.5,
        },
        "appearance": {
            "skin": "#c28569",
            "hair_style": "bob",
            "hair_colour": "#8b9bb4",
            "top_colour": "#3a4466",
            "bottom_colour": "#262b44",
            "shoe_colour": "#262b44",
            "build": "average",
            "accessories": [],
        },
        "voice": {
            "description": "A Fife accent. Low and even.",
            "reference_line": LINE,
            "reference_clip": None,
            "needs_recording": False,
        },
        "craft": None,
        "source": "player",
        "created": "2026-09-01T10:00:00Z",
        "updated": "2026-09-02T10:00:00Z",
        "version": 1,
    } | changes


PREMADE = character(id="tobiah_rennick", name="Tobiah Rennick", source="premade")


def clip(seconds: float = 7.0, sample: int = 1, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(sample.to_bytes(2, "little") * int(seconds * rate))
    return buffer.getvalue()


def eventually(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def finished(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + TIMEOUT
    while True:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed", "cancelled"):
            return job
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


class FakeVoiceLab:
    """The voice kinds, running `fake_voice_job.py` instead of voice-lab's models."""

    def __init__(self) -> None:
        self.heard = LINE
        self.hold = ""

    def design(self, params: VoiceDesign, work: Path) -> list[str]:
        return [sys.executable, str(FAKE_VOICE_JOB), "design", str(work)]

    def check(self, params: VoiceCheck, work: Path) -> list[str]:
        upload = str(uploads_dir(work.parents[1]) / params.upload)
        return [
            sys.executable,
            str(FAKE_VOICE_JOB),
            "check",
            str(work),
            upload,
            self.heard,
            self.hold,
        ]


@pytest.fixture(autouse=True)
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMILE_JOBS", str(tmp_path / "data" / "jobs"))
    monkeypatch.setenv("SIMILE_LIBRARY", str(tmp_path / "data" / "library"))


@pytest.fixture(autouse=True)
def no_elevenlabs(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reads the real key or reaches ElevenLabs."""
    monkeypatch.delenv(eleven.ENV, raising=False)
    monkeypatch.setattr(eleven, "_keychain", lambda *flags: None)
    monkeypatch.setattr(eleven, "API", "http://elevenlabs.invalid")


@pytest.fixture
def voice_lab() -> FakeVoiceLab:
    return FakeVoiceLab()


@pytest.fixture
def library(tmp_path: Path) -> Library:
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / f"{PREMADE['id']}.json").write_text(json.dumps(PREMADE))
    library = Library(tmp_path / "data" / "library", pool)
    library.create(character())
    return library


@pytest.fixture
def app(
    make_package: Callable[[dict[str, str]], str],
    library: Library,
    voice_lab: FakeVoiceLab,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Starlette:
    design = dataclasses.replace(kinds.DESIGN_KIND, command=voice_lab.design, requires=())
    check = dataclasses.replace(kinds.CHECK_KIND, command=voice_lab.check, requires=())
    monkeypatch.setattr(kinds, "DESIGN_KIND", design)
    monkeypatch.setattr(kinds, "CHECK_KIND", check)
    package = make_package(
        {
            "jobs/lifespan.py": "from simile.jobs.lifespan import lifespan\n",
            "jobs/routes.py": "from simile.jobs.routes import routes\n",
            "voicelib/lifespan.py": "from simile.voicelib.lifespan import lifespan\n",
            "voicelib/routes.py": "from simile.voicelib.routes import routes\n",
        }
    )
    app = create_app(package)
    app.state.library = library
    app.state.jobs = Jobs(tmp_path / "data" / "jobs", {})
    return app


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def jobs(app: Starlette) -> Jobs:
    return jobs_of(app)
