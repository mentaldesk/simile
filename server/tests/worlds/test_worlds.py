import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any, Self

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.memory import MemoryStore
from simile.persistence import SavedWorld, WorldStore
from simile.worlds import Worlds, store, supervisor
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
        asked.append(Index(root).read().next)
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
    assert Index(root).read().last is None


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
    assert client.get("/api/worlds").json()["supervised"] is False


def test_makes_a_world_and_opens_it(
    client: TestClient, root: Path, switches: list[str | None]
) -> None:
    world = made(client, count=2, picks=[A, B], open=True)

    assert world["opening"] is True
    assert switches == [world["id"]]
    assert client.get("/api/worlds").json()["supervised"] is True


def test_makes_a_world_without_opening_it(
    client: TestClient, root: Path, switches: list[str | None]
) -> None:
    world = made(client, count=2, picks=[A, B])

    assert world["opening"] is False
    assert switches == []


def test_without_a_supervisor_a_new_world_isnt_opened(client: TestClient, root: Path) -> None:
    world = made(client, count=2, picks=[A, B], open=True)

    assert world["opening"] is False
    assert Index(root).read().next is None


def test_a_corrupt_index_is_moved_aside(client: TestClient, root: Path) -> None:
    world = made(client, count=2, picks=[A, B], name="Ash Lane")
    (root / "worlds.json").write_text("{not json")

    assert listed(client)[world["id"]]["name"] == world["id"]
    client.patch(f"/api/worlds/{world['id']}", json={"name": "Elm Row"})

    assert (root / "worlds.json.bad").read_text() == "{not json"
    assert Index(root).read().entry(world["id"]).name == "Elm Row"


@pytest.mark.parametrize("supervised", [True, False])
def test_the_world_is_last_played_once_its_server_is_up(
    make_package: Callable[[dict[str, str]], str],
    client: TestClient,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervised: bool,
) -> None:
    world = made(client, count=2, picks=[A, B])
    running_on(monkeypatch, root, world["id"])
    if supervised:
        monkeypatch.setenv(supervisor.SUPERVISOR_ENV, "1")
    hook = {"worlds/lifespan.py": "from simile.worlds.lifespan import running\n"}
    app = create_app(make_package(hook))
    app.state.worlds = Worlds(root)

    with TestClient(app):
        up = Index(root).read()
    down = Index(root).read()

    if supervised:
        assert up.last == world["id"] and up.entry(world["id"]).played is not None
        assert down.entry(world["id"]).played > up.entry(world["id"]).played
    else:
        assert up.last is None and down.entry(world["id"]).played is None


class AtHalfPastTwo(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 18, 14, 32, tzinfo=tz)


def test_a_world_made_in_the_same_minute_as_a_saved_one_gets_a_folder_of_its_own(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "datetime", AtHalfPastTwo)
    played = made(client, count=2, picks=[A, B])
    with MemoryStore(root / played["id"] / "simile.db") as memory, WorldStore(memory) as saves:
        saves.save(SavedWorld(now=datetime(2026, 1, 1, 8, tzinfo=UTC), npcs={}))

    second = made(client, count=2, picks=[C, D])

    assert (played["id"], second["id"]) == ("2026-10-18-1432", "2026-10-18-1432-2")
    assert folders(root) == [played["id"], second["id"]]
