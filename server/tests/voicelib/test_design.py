from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.jobs import Jobs
from simile.library import Library
from simile.voicelib import kinds
from simile.voicelib.kinds import DESIGN_KIND

from .conftest import LINE, clip, finished

DESCRIPTION = "A Fife accent. A woman in her fifties, low and even."
NEW_LINE = "Mind the step on your way out, the frost has been at it again since the weekend."


def design(client: TestClient, **params: object) -> dict:
    asked = {"description": DESCRIPTION, "reference_line": NEW_LINE} | params
    submitted = client.post("/api/jobs", json={"kind": "voice_design", "params": asked})
    assert submitted.status_code == 202, submitted.text
    return finished(client, submitted.json()["id"])


def test_a_design_job_yields_candidates(client: TestClient) -> None:
    job = design(client, seed=7)

    assert job["state"] == "succeeded", job["error"]
    result = job["result"]
    assert result["description"] == DESCRIPTION
    assert result["reference_line"] == NEW_LINE
    assert result["seed"] == 7
    assert [c["n"] for c in result["candidates"]] == [1, 2, 3, 4]
    first = result["candidates"][0]
    assert first["clip"] == f"/api/jobs/files/voice_design/{job['id']}_1.wav"
    assert first["clone"] == f"/api/jobs/files/voice_design/{job['id']}_1_clone.wav"
    assert first["problems"] == ["7.0s long"]
    assert first["clone_accent"] == "england 60%, scotland 30%"
    assert client.get(first["clip"]).content == clip(sample=1)
    assert client.get(first["clone"]).content == clip(sample=101)


def test_picking_a_candidate_sets_the_clip_and_its_line(
    client: TestClient, library: Library
) -> None:
    job = design(client)

    picked = client.post(
        "/api/characters/wren_abernethy/voice/pick", json={"design": job["id"], "candidate": 3}
    )

    assert picked.status_code == 200, picked.text
    assert picked.json()["voice"]["reference_clip"] == "clips/wren_abernethy.wav"
    assert picked.json()["voice"]["reference_line"] == NEW_LINE
    character = library.get("wren_abernethy")
    assert library.clip(character).read_bytes() == clip(sample=3)
    assert character.voice.reference_line == NEW_LINE
    assert character.voice.description == "A Fife accent. Low and even."


def test_a_design_keeps_the_line_when_it_is_the_same(client: TestClient, library: Library) -> None:
    job = design(client, reference_line=LINE)

    client.post(
        "/api/characters/wren_abernethy/voice/pick", json={"design": job["id"], "candidate": 1}
    )

    character = library.get("wren_abernethy")
    assert character.voice.reference_line == LINE
    assert character.version == 2


@pytest.mark.parametrize(
    ("pick", "status", "error"),
    [
        ({"design": "0123456789abcdef", "candidate": 1}, 404, "Those designed voices are gone"),
        ({"design": "{job}", "candidate": 5}, 404, "That design has no voice 5"),
        ({"design": "{job}"}, 422, "Only a designed voice has a candidate"),
        ({"design": "../../etc", "candidate": 1}, 422, "design: String should match pattern"),
        ({"design": "{job}", "candidate": 1, "library": "tobias"}, 422, "Pick one of"),
        ({}, 422, "Pick one of"),
    ],
)
def test_a_bad_pick_is_refused_with_a_reason(
    client: TestClient, library: Library, pick: dict, status: int, error: str
) -> None:
    job = design(client)
    pick = {
        key: value.format(job=job["id"]) if isinstance(value, str) else value
        for key, value in pick.items()
    }

    response = client.post("/api/characters/wren_abernethy/voice/pick", json=pick)

    assert response.status_code == status
    assert response.json()["error"].startswith(error)
    assert library.get("wren_abernethy").voice.reference_clip is None


def test_a_premade_character_keeps_its_voice(client: TestClient) -> None:
    job = design(client)

    response = client.post(
        "/api/characters/tobiah_rennick/voice/pick", json={"design": job["id"], "candidate": 1}
    )

    assert response.status_code == 403


def test_an_unknown_character_is_404(client: TestClient) -> None:
    response = client.post("/api/characters/nobody/voice/pick", json={"library": "tobias"})

    assert response.json() == {"error": "No such character"}
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({"description": "   "}, "description: can't be blank"),
        ({"count": 7}, "count: Input should be less than or equal to 6"),
        ({"reference_line": "x" * 401}, "reference_line: String should have at most 400"),
        ({"seed": -1}, "seed: Input should be greater than or equal to 0"),
    ],
)
def test_a_bad_design_is_refused(client: TestClient, params: dict, error: str) -> None:
    asked = {"description": DESCRIPTION, "reference_line": NEW_LINE} | params

    response = client.post("/api/jobs", json={"kind": "voice_design", "params": asked})

    assert response.status_code == 422
    assert response.json()["error"].startswith(error)


def test_without_apple_silicon_a_design_fails_with_the_reason(
    app: Starlette, tmp_path: Path
) -> None:
    app.state.jobs = Jobs(tmp_path / "jobs", {"apple_silicon": False, "voice_lab": True})
    app.state.jobs.register(DESIGN_KIND)
    with TestClient(app) as client:
        submitted = client.post(
            "/api/jobs",
            json={"kind": "voice_design", "params": {"description": "A", "reference_line": "B"}},
        )

    assert submitted.json()["state"] == "failed"
    assert submitted.json()["error"] == (
        "voice_design jobs need a Mac with Apple Silicon and voice-lab/.venv-mlx (see "
        "voice-lab/README.md), which this machine doesn't have"
    )


def test_runs_voice_job_in_voice_labs_virtualenv(tmp_path: Path) -> None:
    work = tmp_path / "jobs" / "work" / "0123456789abcdef"
    params = kinds.VoiceDesign(description="A", reference_line="B")

    command = kinds.design_command(params, work)

    assert command == [str(kinds.TORCH_PYTHON), str(kinds.SCRIPT), "design", str(work)]
    assert kinds.SCRIPT.is_file()


def test_keeps_the_latest_designs(
    client: TestClient, jobs: Jobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kinds, "KEEP", 2)
    first, *rest = [design(client, count=1)["id"] for _ in range(3)]

    left = sorted(path.name for path in (jobs.root / "voice_design").iterdir())

    assert left == sorted(
        f"{job}{end}" for job in rest for end in (".json", "_1.wav", "_1_clone.wav")
    )
    assert first not in "".join(left)
