from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from simile.app import create_app
from simile.jobs import Jobs, jobs_of

from .conftest import eventually, fake_kind


@pytest.fixture
def app(make_package: Callable[[dict[str, str]], str], root: Path) -> Starlette:
    package = make_package(
        {
            "jobs/lifespan.py": "from simile.jobs.lifespan import lifespan\n",
            "jobs/routes.py": "from simile.jobs.routes import routes\n",
        }
    )
    return create_app(package)


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        jobs_of(app).register(fake_kind())
        yield client


def job(client: TestClient, job_id: str) -> dict[str, Any]:
    return client.get(f"/api/jobs/{job_id}").json()


def test_clears_up_after_a_killed_server(app: Starlette, root: Path) -> None:
    left = root / "work" / "0123456789abcdef"
    left.mkdir(parents=True)
    (left / "params.json").write_text("{}")
    (root / "work" / "notes").mkdir()

    with TestClient(app):
        assert sorted(path.name for path in (root / "work").iterdir()) == ["notes"]


def test_reports_what_this_machine_can_run(app: Starlette, root: Path) -> None:
    app.state.jobs = Jobs(root, {"blender": False, "apple_silicon": True})
    with TestClient(app) as client:
        jobs_of(app).register(fake_kind("render", requires=("blender",)))
        response = client.get("/api/jobs/capabilities")

    assert response.json() == {
        "machine": {"blender": False, "apple_silicon": True},
        "kinds": {
            "sprite": {"available": True, "reason": None},
            "render": {
                "available": False,
                "reason": "render jobs need Blender (install it or set $BLENDER), "
                "which this machine doesn't have",
            },
        },
    }


def test_submits_and_watches_a_job(client: TestClient, tmp_path: Path) -> None:
    hold = tmp_path / "hold"
    submitted = client.post("/api/jobs", json={"kind": "fake", "params": {"hold": str(hold)}})
    job_id = submitted.json()["id"]

    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        updates = [ws.receive_json()]
        while updates[-1]["progress"] < 0.5:
            updates.append(ws.receive_json())
        halfway = updates[-1]
        hold.touch()
        while updates[-1]["state"] != "succeeded":
            updates.append(ws.receive_json())
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()

    assert submitted.status_code == 202
    assert submitted.json()["kind"] == "fake"
    assert halfway["state"] == "running" and halfway["message"] == "Halfway"
    assert closed.value.code == 1000
    assert job(client, job_id) == updates[-1]
    assert updates[-1]["result"] == {"file": "/api/jobs/files/fake/out.txt"}
    assert client.get("/api/jobs/files/fake/out.txt").text == "out"
    assert [listed["id"] for listed in client.get("/api/jobs").json()] == [job_id]


def test_a_job_keeps_going_when_its_watcher_leaves(client: TestClient, tmp_path: Path) -> None:
    hold = tmp_path / "hold"
    params = {"hold": str(hold)}
    job_id = client.post("/api/jobs", json={"kind": "fake", "params": params}).json()["id"]

    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        ws.receive_json()
    eventually(lambda: job(client, job_id)["progress"] == 0.5)
    hold.touch()

    eventually(lambda: job(client, job_id)["state"] == "succeeded")


def test_cancels_a_job(client: TestClient, tmp_path: Path) -> None:
    params = {"hold": str(tmp_path / "never")}
    job_id = client.post("/api/jobs", json={"kind": "fake", "params": params}).json()["id"]
    eventually(lambda: job(client, job_id)["state"] == "running")

    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    again = client.post(f"/api/jobs/{job_id}/cancel")
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        watched = ws.receive_json()

    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    assert again.status_code == 409
    assert again.json() == {"error": "the job has already cancelled"}
    assert watched == cancelled.json()
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_refuses_more_waiting_jobs_than_it_holds(client: TestClient, tmp_path: Path) -> None:
    hold = {"kind": "fake", "params": {"hold": str(tmp_path / "hold")}}
    statuses = [client.post("/api/jobs", json=hold).status_code for _ in range(6)]
    (tmp_path / "hold").touch()

    assert statuses == [202] * 5 + [429]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (b"not json", "Invalid JSON"),
        (b'{"params": {}}', "kind: Field required"),
        (b'{"kind": "fake", "params": [1]}', "params: Input should be an object"),
        (b'{"kind": "fake", "extra": 1}', "extra: Extra inputs are not permitted"),
        (b'{"kind": "nope"}', "there's no 'nope' job"),
        (b'{"kind": "fake", "params": {"exit": "x"}}', "exit: Input should be a valid integer"),
        (b'{"kind": "sprite", "params": {"character": "../up"}}', "character: String should"),
    ],
)
def test_refuses_a_bad_job(client: TestClient, body: bytes, error: str) -> None:
    response = client.post("/api/jobs", content=body)

    assert response.status_code == 422
    assert error in response.json()["error"]
    assert client.get("/api/jobs").json() == []


def test_refuses_a_huge_request(client: TestClient) -> None:
    response = client.post("/api/jobs", content=b"x" * (65 * 1024))

    assert response.status_code == 413


def test_knows_no_other_jobs(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404
    with client.websocket_connect("/ws/jobs/nope") as ws, pytest.raises(WebSocketDisconnect) as e:
        ws.receive_json()
    assert e.value.code == 4404


@pytest.mark.parametrize(
    "path",
    [
        "/api/jobs/files/fake/missing.txt",
        "/api/jobs/files/fake/params.json",
        "/api/jobs/files/nope/out.txt",
        "/api/jobs/files/fake/..%2F..%2Fwork%2Fout.txt",
        "/api/jobs/files/fake/%2E%2E%2Fout.txt",
        "/api/jobs/files/work/out.txt",
        "/api/jobs/files/sprite/kofi.png",
    ],
)
def test_serves_nothing_but_published_files(
    client: TestClient, root: Path, tmp_path: Path, path: str
) -> None:
    job_id = client.post("/api/jobs", json={"kind": "fake"}).json()["id"]
    eventually(lambda: job(client, job_id)["state"] == "succeeded")
    (root / "work").mkdir(exist_ok=True)
    (root / "work" / "out.txt").write_text("scratch")
    (root / "fake" / "params.json").write_text("{}")

    assert client.get(path).status_code == 404
