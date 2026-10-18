import os
import time
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.jobs import Jobs
from simile.library import Library
from simile.voicelib import kinds
from simile.voicelib.kinds import CHECK_KIND, uploads_dir
from simile.voicelib.uploads import MAX_UPLOAD, remove_stale

from .conftest import LINE, FakeVoiceLab, clip, eventually, finished

RECORD = "/api/characters/wren_abernethy/voice/recording"
PICK = "/api/characters/wren_abernethy/voice/pick"


def record(client: TestClient, data: bytes) -> dict:
    submitted = client.post(RECORD, content=data, headers={"Content-Type": "audio/wav"})
    assert submitted.status_code == 202, submitted.text
    return finished(client, submitted.json()["id"])


def test_a_recording_that_passes_its_checks_becomes_the_voice(
    client: TestClient, library: Library, jobs: Jobs
) -> None:
    job = record(client, clip(8.0, sample=9))

    assert job["state"] == "succeeded", job["error"]
    result = job["result"]
    assert result["usable"] is True
    assert result["heard"] == LINE
    assert result["reference_line"] == LINE
    assert result["accent"] == "scotland 90%"
    assert len(result["samples"]) == 3
    assert client.get(result["clip"]).content == clip(8.0, sample=9)
    assert list(uploads_dir(jobs.root).iterdir()) == []

    picked = client.post(PICK, json={"recording": job["id"]})

    assert picked.status_code == 200, picked.text
    character = library.get("wren_abernethy")
    assert library.clip(character).read_bytes() == clip(8.0, sample=9)
    assert character.voice.reference_line == LINE


def test_a_recording_whose_transcript_doesnt_match_is_refused(
    client: TestClient, library: Library, voice_lab: FakeVoiceLab
) -> None:
    voice_lab.heard = "The early bus leaves at seven, and I am never late for it."
    job = record(client, clip(8.0))

    assert job["result"]["usable"] is False
    assert job["result"]["problems"] == ["word error rate 58%", "ending missing"]

    picked = client.post(PICK, json={"recording": job["id"]})

    assert picked.status_code == 422
    assert picked.json()["error"] == (
        "The recording didn't pass its checks: word error rate 58%; ending missing"
    )
    assert library.get("wren_abernethy").voice.reference_clip is None


def test_a_recording_too_short_is_refused(client: TestClient) -> None:
    job = record(client, clip(3.0))

    picked = client.post(PICK, json={"recording": job["id"]})

    assert picked.json()["error"] == "The recording didn't pass its checks: 3.0 s long, not 5-25 s"


def test_a_recording_that_wont_convert_is_refused(client: TestClient) -> None:
    job = record(client, b"ID3" + bytes(1000))

    assert job["result"]["errors"] == ["couldn't convert upload.mp3: Couldn't open input file"]
    assert job["result"]["clip"] is None
    picked = client.post(PICK, json={"recording": job["id"]})
    assert picked.json()["error"].startswith("The recording didn't pass its checks: couldn't")


def test_a_recording_that_cant_be_used_isnt_kept(client: TestClient, library: Library) -> None:
    data = library.get("wren_abernethy").model_dump(mode="json")
    data["voice"]["reference_line"] = "Mind the step."
    library.update("wren_abernethy", data)

    job = record(client, clip(8.0))

    assert job["result"]["errors"][0].startswith("the transcript is 3 words, but a reference line")
    assert job["result"]["clip"] is None
    assert job["result"]["usable"] is False


def webm() -> bytes:
    return b"\x1aE\xdf\xa3" + bytes(100)


@pytest.mark.parametrize(
    ("data", "status", "error"),
    [
        (b"", 422, "The recording is empty"),
        (webm(), 415, "WebM recordings aren't supported: send a WAV, MP3 or M4A file"),
        (b"%PDF-1.7" + bytes(100), 415, "A recording has to be a WAV, MP3 or M4A file"),
        (clip()[:-1000], 422, "The voice clip is cut short"),
        (clip(61.0), 422, "The voice clip can be at most 60 seconds long"),
        (b"RIFF\x00\x00\x00\x00WAVEjunk", 422, "The voice clip isn't a WAV file that decodes"),
        (bytes(MAX_UPLOAD + 1), 413, "That can be at most 10240 KB"),
    ],
)
def test_a_bad_upload_is_refused_with_a_reason(
    client: TestClient, jobs: Jobs, data: bytes, status: int, error: str
) -> None:
    response = client.post(RECORD, content=data)

    assert response.status_code == status
    assert response.json()["error"].startswith(error)
    assert client.get("/api/jobs").json() == []
    assert not uploads_dir(jobs.root).exists() or not list(uploads_dir(jobs.root).iterdir())


def test_a_premade_character_cant_record(client: TestClient) -> None:
    response = client.post("/api/characters/tobiah_rennick/voice/recording", content=clip())

    assert response.status_code == 403


def test_without_the_voice_lab_recordings_are_refused(
    app: Starlette, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kinds, "CHECK_KIND", CHECK_KIND)
    app.state.jobs = Jobs(tmp_path / "jobs", {"apple_silicon": True, "voice_lab": False})
    with TestClient(app) as client:
        response = client.post(RECORD, content=clip())

    assert response.status_code == 503
    assert response.json()["error"].startswith("voice_check jobs need voice-lab/.venv (see")
    assert not (tmp_path / "jobs" / "voice_check").exists()


def test_a_check_cant_be_pointed_at_another_file(client: TestClient) -> None:
    params = {"upload": "../../../etc/passwd", "reference_line": LINE}

    response = client.post("/api/jobs", json={"kind": "voice_check", "params": params})

    assert response.status_code == 422
    assert response.json()["error"].startswith("upload: String should match pattern")


def test_clears_uploads_a_day_old(tmp_path: Path) -> None:
    folder = tmp_path / "uploads"
    folder.mkdir()
    for name in ("old.wav", "new.wav"):
        (folder / name).write_bytes(b"RIFF")
    two_days_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(folder / "old.wav", (two_days_ago, two_days_ago))

    remove_stale(folder)

    assert [path.name for path in folder.iterdir()] == ["new.wav"]


def test_a_cancelled_check_deletes_its_upload(
    client: TestClient, jobs: Jobs, voice_lab: FakeVoiceLab, tmp_path: Path
) -> None:
    voice_lab.hold = str(tmp_path / "hold")
    running = client.post(RECORD, content=clip()).json()
    queued = client.post(RECORD, content=clip()).json()
    uploads = uploads_dir(jobs.root)
    assert len(list(uploads.iterdir())) == 2

    assert client.post(f"/api/jobs/{queued['id']}/cancel").json()["state"] == "cancelled"
    eventually(lambda: len(list(uploads.iterdir())) == 1)
    client.post(f"/api/jobs/{running['id']}/cancel")

    eventually(lambda: list(uploads.iterdir()) == [])


def test_stopping_the_server_deletes_waiting_uploads(
    app: Starlette, jobs: Jobs, voice_lab: FakeVoiceLab, tmp_path: Path
) -> None:
    voice_lab.hold = str(tmp_path / "hold")
    with TestClient(app) as client:
        client.post(RECORD, content=clip())
        client.post(RECORD, content=clip())
        assert len(list(uploads_dir(jobs.root).iterdir())) == 2

    assert list(uploads_dir(jobs.root).iterdir()) == []
