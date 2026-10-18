"""The real voice check, on a clip macOS `say` makes, so no voice is committed."""

import shutil
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.jobs import Jobs
from simile.jobs.capabilities import detect
from simile.library import Library
from simile.voicelib import kinds
from simile.voicelib.kinds import CHECK_KIND, MLX_PYTHON, TORCH_PYTHON

from .conftest import LINE

pytestmark = [
    pytest.mark.mlx,
    pytest.mark.skipif(shutil.which("say") is None, reason="needs macOS's say"),
    pytest.mark.skipif(
        not (TORCH_PYTHON.exists() and MLX_PYTHON.exists()),
        reason="needs voice-lab's virtualenvs (see voice-lab/README.md)",
    ),
]

RECORD = "/api/characters/wren_abernethy/voice/recording"
PICK = "/api/characters/wren_abernethy/voice/pick"
SAID = (
    "Mind the step on your way out, the frost has been at it again and the gate sticks in the cold."
)
CHECKED_WITHIN = 300.0


@pytest.fixture
def client(app: Starlette, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(kinds, "CHECK_KIND", CHECK_KIND)
    app.state.jobs = Jobs(tmp_path / "data" / "jobs", detect())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def clip(tmp_path: Path) -> bytes:
    path = tmp_path / "said.m4a"
    say = ["say", "-v", "Daniel", "-r", "150", "-o", str(path), "--file-format=m4af"]
    made = subprocess.run([*say, "--data-format=aac", SAID], capture_output=True, text=True)
    if made.returncode:
        pytest.skip(f"say couldn't speak as Daniel: {made.stderr.strip()}")
    return path.read_bytes()


def checked(client: TestClient, data: bytes, transcript: str) -> dict[str, Any]:
    submitted = client.post(RECORD, content=data, params={"transcript": transcript})
    assert submitted.status_code == 202, submitted.text
    deadline = time.monotonic() + CHECKED_WITHIN
    while (job := client.get(f"/api/jobs/{submitted.json()['id']}").json())["state"] in (
        "queued",
        "running",
    ):
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.5)
    assert job["state"] == "succeeded", job["error"]
    return job


def test_a_clip_that_says_its_transcript_becomes_the_voice_with_that_line(
    client: TestClient, library: Library, clip: bytes
) -> None:
    job = checked(client, clip, SAID)

    assert job["result"]["usable"] is True, job["result"]
    assert client.post(PICK, json={"recording": job["id"]}).status_code == 200
    character = library.get("wren_abernethy")
    assert character.voice.reference_line == SAID
    assert library.clip(character).read_bytes() == client.get(job["result"]["clip"]).content


def test_a_clip_that_says_something_else_leaves_the_voice_as_it_was(
    client: TestClient, library: Library, clip: bytes
) -> None:
    job = checked(client, clip, LINE)

    assert job["result"]["usable"] is False
    assert "ending missing" in job["result"]["problems"]
    assert client.post(PICK, json={"recording": job["id"]}).status_code == 422
    voice = library.get("wren_abernethy").voice
    assert (voice.reference_line, voice.reference_clip) == (LINE, None)
