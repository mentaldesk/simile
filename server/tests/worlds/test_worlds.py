import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from simile.memory import MemoryStore
from simile.persistence import SavedWorld, WorldStore
from simile.worlds import supervisor
from simile.worlds.index import Index
from simile.worlds.store import TODAY, TODAY_ID

from .conftest import POOL, folders

A, B, C, D = POOL[:4]


def made(client: TestClient, **asked: Any) -> dict[str, Any]:
    response = client.post("/api/worlds", json=asked)
    assert response.status_code == 201, response.text
    return response.json()


def listed(client: TestClient) -> dict[str, dict[str, Any]]:
    return {w["id"]: w for w in client.get("/api/worlds").json()["worlds"]}


@pytest.fixture
def switches(monkeypatch: pytest.MonkeyPatch, root: Path) -> list[str | None]:
    """The server runs under a supervisor, and these are the worlds it was asked to open."""
    asked: list[str | None] = []

    def switch() -> bool:
        asked.append(Index(root).read().last)
        return True

    monkeypatch.setenv(supervisor.SUPERVISOR_ENV, "1")
    monkeypatch.setattr(supervisor, "switch", switch)
    return asked


def running_on(monkeypatch: pytest.MonkeyPatch, root: Path, id: str) -> None:
    monkeypatch.setenv("SIMILE_DB", str(root / id / "simile.db"))


def test_lists_todays_village_and_the_new_worlds_newest_first(
    client: TestClient, root: Path
) -> None:
    first = made(client, count=2, picks=[A, B])
    second = made(client, count=3, picks=[A, B, C], name="Ash Lane")

    worlds = client.get("/api/worlds").json()["worlds"]

    assert [w["id"] for w in worlds] == [TODAY_ID, *sorted([first["id"], second["id"]])[::-1]]
    today, *_ = worlds
    assert today["name"] == TODAY and today["default"] is True
    assert today["player"] == "Visitor"
    by_id = {w["id"]: w for w in worlds}
    assert by_id[first["id"]]["name"] == first["id"]
    assert by_id[second["id"]]["name"] == "Ash Lane" == second["name"]
    assert by_id[second["id"]]["residents"] == 3
    assert by_id[second["id"]]["made"] is not None
    assert by_id[second["id"]]["played"] is None
    assert by_id[second["id"]]["day"] is None
    assert not any(w["running"] for w in worlds)


def test_marks_the_running_world(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = made(client, count=2, picks=[A, B])
    running_on(monkeypatch, root, world["id"])

    answer = client.get("/api/worlds").json()

    assert answer["current"]["id"] == world["id"]
    assert [w["id"] for w in answer["worlds"] if w["running"]] == [world["id"]]


def test_reports_the_day_and_time_its_saved_on(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = made(client, count=2, picks=[A, B])
    database = root / world["id"] / "simile.db"
    saved = datetime(2026, 3, 4, 15, 30, tzinfo=UTC)
    with MemoryStore(database) as memory, WorldStore(memory) as store:
        store.save(SavedWorld(now=saved, npcs={}))
    with closing(sqlite3.connect(database)) as db, db:
        first = datetime(2026, 3, 2, 9, tzinfo=UTC).timestamp()
        db.execute(f"INSERT INTO events VALUES (1, 'a', 'b', {first}, 0, '{{}}')")

    found = listed(client)[world["id"]]

    assert found["day"] == 3
    assert datetime.fromisoformat(found["time"]) == saved


def test_renames_a_world_and_todays_village(client: TestClient) -> None:
    world = made(client, count=2, picks=[A, B])

    renamed = client.patch(f"/api/worlds/{world['id']}", json={"name": "  Ash Lane "})
    today = client.patch(f"/api/worlds/{TODAY_ID}", json={"name": "Home"})

    assert renamed.status_code == 200 and renamed.json()["name"] == "Ash Lane"
    assert today.json()["name"] == "Home"
    assert listed(client)[world["id"]]["name"] == "Ash Lane"
    assert client.get(f"/api/worlds/{world['id']}").json()["name"] == "Ash Lane"


@pytest.mark.parametrize("name", ["", "   ", "x" * 65, None])
def test_a_bad_name_is_refused(client: TestClient, name: object) -> None:
    world = made(client, count=2, picks=[A, B])

    response = client.patch(f"/api/worlds/{world['id']}", json={"name": name})

    assert response.status_code == 422
    assert listed(client)[world["id"]]["name"] == world["id"]


def test_deletes_a_world(client: TestClient, root: Path) -> None:
    kept = made(client, count=2, picks=[A, B])
    gone = made(client, count=2, picks=[C, D], name="Gone")

    response = client.delete(f"/api/worlds/{gone['id']}")

    assert response.status_code == 204
    assert folders(root) == [kept["id"]]
    assert set(listed(client)) == {TODAY_ID, kept["id"]}
    assert gone["id"] not in Index(root).read().worlds


def test_wont_delete_todays_village(client: TestClient) -> None:
    response = client.delete(f"/api/worlds/{TODAY_ID}")

    assert response.status_code == 409
    assert "can't be deleted" in response.json()["error"]


def test_wont_delete_the_running_world(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = made(client, count=2, picks=[A, B])
    running_on(monkeypatch, root, world["id"])

    response = client.delete(f"/api/worlds/{world['id']}")

    assert response.status_code == 409
    assert folders(root) == [world["id"]]


@pytest.mark.parametrize("id", ["nobody", "..", ".worlds.json.lock", "worlds.json"])
def test_an_unknown_world_is_not_found(client: TestClient, root: Path, id: str) -> None:
    made(client, count=2, picks=[A, B])

    assert client.get(f"/api/worlds/{id}").status_code == 404
    assert client.patch(f"/api/worlds/{id}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/worlds/{id}").status_code == 404
    assert client.post(f"/api/worlds/{id}/open").status_code == 404
    assert len(folders(root)) == 1


def test_a_folder_without_a_cast_isnt_a_world(client: TestClient, root: Path) -> None:
    (root / "notes").mkdir(parents=True)

    assert set(listed(client)) == {TODAY_ID}
    assert client.delete("/api/worlds/notes").status_code == 404
    assert (root / "notes").is_dir()


def test_opens_a_world_through_the_supervisor(
    client: TestClient, root: Path, switches: list[str | None]
) -> None:
    world = made(client, count=2, picks=[A, B])

    response = client.post(f"/api/worlds/{world['id']}/open")

    assert response.status_code == 202
    assert response.json() == {"id": world["id"], "opening": True}
    assert switches == [world["id"]]


def test_opening_the_running_world_does_nothing(
    client: TestClient, root: Path, switches: list[str | None], monkeypatch: pytest.MonkeyPatch
) -> None:
    world = made(client, count=2, picks=[A, B])
    running_on(monkeypatch, root, world["id"])

    response = client.post(f"/api/worlds/{world['id']}/open")

    assert response.status_code == 200
    assert response.json() == {"id": world["id"], "opening": False}
    assert switches == []


def test_cant_open_a_world_without_a_supervisor(client: TestClient, root: Path) -> None:
    world = made(client, count=2, picks=[A, B])

    response = client.post(f"/api/worlds/{world['id']}/open")

    assert response.status_code == 409
    assert "simile worlds serve" in response.json()["error"]
    assert client.get("/api/worlds").json()["switching"] is False


def test_makes_a_world_and_opens_it(
    client: TestClient, root: Path, switches: list[str | None]
) -> None:
    world = made(client, count=2, picks=[A, B], open=True)

    assert world["opening"] is True
    assert switches == [world["id"]]
    assert client.get("/api/worlds").json()["switching"] is True


def test_makes_a_world_without_opening_it(
    client: TestClient, root: Path, switches: list[str | None]
) -> None:
    world = made(client, count=2, picks=[A, B])

    assert world["opening"] is False
    assert switches == []
