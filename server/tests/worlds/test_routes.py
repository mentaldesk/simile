from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.casting import cast_npcs, load_cast
from simile.library import Library
from simile.memory import MemoryStore
from simile.memory.store import DEFAULT_PATH
from simile.npc import NPCS_DIR, load_npcs
from simile.persistence import SavedWorld, WorldStore
from simile.schema import Character, CharacterSource
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.worlds import Worlds
from simile.worlds.store import REPO, SERVER, shown

from .conftest import POOL, clip, files, folders

A, B, C, D, E, F = POOL[:6]
CONTENT = NPCS_DIR.parent


def today() -> dict[Path, bytes]:
    found: dict[Path, bytes] = {}
    for folder in ("npcs", "voices", "art/characters", "characters/pool"):
        found |= files(CONTENT / folder)
    return found


def made(client: TestClient, **asked: Any) -> dict[str, Any]:
    response = client.post("/api/worlds", json=asked)
    assert response.status_code == 201, response.text
    return response.json()


def test_lists_the_running_world_and_the_houses(client: TestClient) -> None:
    listed = client.get("/api/worlds").json()

    assert listed["houses"] == 10
    assert listed["current"]["name"] == "Today's village"
    assert listed["current"]["default"] is True
    assert [r["id"] for r in listed["current"]["residents"]] == [n.id for n in load_npcs(NPCS_DIR)]


def test_a_new_world_of_six_picked_residents(client: TestClient, root: Path) -> None:
    picks = [A, B, C, D, E, F]

    world = made(client, count=6, picks=picks)

    folder = root / world["name"]
    assert folders(root) == [world["name"]]
    assert world["data"] == shown(folder)
    assert [r["id"] for r in world["residents"]] == picks
    cast = load_cast(folder)
    assert cast is not None and [r.character.id for r in cast.residents] == picks
    assert sorted(npc.id for npc in load_npcs(cast_npcs(folder))) == sorted(picks)
    assert len({r["home"] for r in world["residents"]}) == 6
    assert not (folder / "simile.db").exists()


def test_reports_what_each_resident_still_needs(client: TestClient, root: Path) -> None:
    world = made(client, count=2, picks=[A, B])

    assert [(m["id"], m["needs"]) for m in world["missing"]] == [
        (A, ["voice", "sprite"]),
        (B, ["voice", "sprite"]),
    ]


def test_says_how_to_start_the_server_on_it(
    client: TestClient, root: Path, library: Library
) -> None:
    world = made(client, count=2, picks=[A, B])

    folder = root / world["name"]
    env = {"SIMILE_DB": shown(folder / "simile.db"), "SIMILE_LIBRARY": shown(library.root)}
    assert world["restart"]["env"] == env
    assert world["restart"]["command"] == (
        f"SIMILE_DB={env['SIMILE_DB']} SIMILE_LIBRARY={env['SIMILE_LIBRARY']} make dev"
    )


def test_paths_are_shown_from_the_server_folder(tmp_path: Path) -> None:
    assert shown(SERVER / "worlds" / "2026-10-18-0900") == "worlds/2026-10-18-0900"
    assert shown(SERVER / "data" / "library") == "data/library"
    assert shown(tmp_path / "worlds") == str((tmp_path / "worlds").resolve())


def test_randomise_draws_ten(client: TestClient, pool: list[Character]) -> None:
    world = made(client, count=10)

    ids = [r["id"] for r in world["residents"]]
    assert len(set(ids)) == 10
    assert set(ids) <= {c.id for c in pool}


def test_a_pin_binds_and_casts_both(client: TestClient) -> None:
    world = made(client, count=3, picks=[A], pins=[{"kind": "rival", "actor": A, "target": B}])

    assert {r["id"] for r in world["residents"]} >= {A, B}
    assert {"kind": "rival", "actor": A, "target": B, "pinned": True}.items() <= next(
        bond for bond in world["bonds"] if bond["pinned"]
    ).items()


def test_leaves_todays_village_and_its_save_alone(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    village = tmp_path / "today" / "simile.db"
    village.parent.mkdir()
    with MemoryStore(village) as memory, WorldStore(memory) as store:
        store.save(SavedWorld(now=datetime(2026, 1, 1, 8, tzinfo=UTC), npcs={}))
    monkeypatch.setenv("SIMILE_DB", str(village))
    before, content = files(village.parent), today()

    made(client, count=10)
    made(client, count=6, picks=[A, B, C, D, E, F])

    assert files(village.parent) == before
    assert today() == content
    assert client.get("/api/worlds").json()["current"]["name"] == "Today's village"
    assert load_npcs() == load_npcs(NPCS_DIR)


def test_each_new_world_gets_a_folder_of_its_own(client: TestClient, root: Path) -> None:
    first = made(client, count=4, seed=7)
    kept = files(root / first["name"])

    second = made(client, count=4, seed=7)

    assert first["name"] != second["name"]
    assert folders(root) == sorted([first["name"], second["name"]])
    assert files(root / first["name"]) == kept


BAD = [
    ({"count": 0}, "count"),
    ({"count": 11}, "10 houses"),
    ({"count": 3, "picks": ["nobody"]}, "No character nobody"),
    ({"count": 3, "picks": [A, A]}, "picked twice"),
    ({"count": 1, "picks": [A, B]}, "can't hold the 2 picked"),
    ({"count": 3, "picks": ["Not An Id"]}, "picks.0"),
    ({"count": 3, "pins": [{"kind": "feud", "actor": A, "target": B}]}, "pins.0.kind"),
    ({"count": 3, "pins": [{"kind": "rival", "actor": A, "target": A}]}, "two residents"),
    ({"count": 3, "pins": [{"kind": "rival", "actor": A, "target": "nobody"}]}, "nobody"),
    (
        {
            "count": 3,
            "pins": [
                {"kind": "rival", "actor": A, "target": B},
                {"kind": "debt", "actor": B, "target": A},
            ],
        },
        "pinned twice",
    ),
    ({"count": 3, "world": "mine"}, "world"),
    ({"count": "six"}, "count"),
    ([3], "an object"),
    ({}, "count"),
]


@pytest.mark.parametrize("path", ["/api/worlds", "/api/worlds/draw"])
@pytest.mark.parametrize(("asked", "reason"), BAD)
def test_a_bad_request_is_refused_with_a_reason(
    client: TestClient, root: Path, path: str, asked: object, reason: str
) -> None:
    response = client.post(path, json=asked)

    assert response.status_code == 422
    assert reason in response.json()["error"]
    assert folders(root) == []


def test_a_request_that_isnt_json_is_refused(client: TestClient, root: Path) -> None:
    response = client.post("/api/worlds", content=b"count=6")

    assert response.status_code == 422
    assert "JSON" in response.json()["error"]
    assert folders(root) == []


def test_a_large_request_is_refused(client: TestClient, root: Path) -> None:
    response = client.post("/api/worlds", json={"count": 3, "picks": [A] * 10_000})

    assert response.status_code == 413
    assert folders(root) == []


def test_draw_fills_up_the_picks_and_writes_nothing(client: TestClient, root: Path) -> None:
    response = client.post("/api/worlds/draw", json={"count": 10, "picks": [A, B]})

    assert response.status_code == 200
    drawn = response.json()["residents"]
    assert drawn[:2] == [A, B] and len(set(drawn)) == 10
    assert not root.exists()


def test_the_running_world_is_the_one_the_server_points_at(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = made(client, count=3, picks=[A, B, C])
    monkeypatch.setenv("SIMILE_DB", world["restart"]["env"]["SIMILE_DB"])
    monkeypatch.chdir(SERVER)

    running = client.get("/api/worlds").json()["current"]

    assert running["name"] == world["name"]
    assert running["default"] is False
    assert running["data"] == world["data"]
    assert sorted(r["id"] for r in running["residents"]) == sorted([A, B, C])


def test_a_player_characters_clip_goes_with_them(
    client: TestClient, root: Path, library: Library, pool: list[Character]
) -> None:
    data = pool[0].model_dump(mode="json") | {"id": "wren_abernethy", "name": "Wren Abernethy"}
    player = library.create(data | {"source": CharacterSource.PLAYER})
    library.save_clip(player.id, clip())

    world = made(client, count=1, picks=[player.id])

    copy = root / world["name"] / "clips" / f"{player.id}.wav"
    assert copy.read_bytes() == clip()
    (npc,) = load_npcs(cast_npcs(root / world["name"]))
    assert npc.voice.reference_clip is not None
    assert (REPO / npc.voice.reference_clip).resolve() == copy.resolve()
    assert world["missing"] == [{"id": player.id, "name": player.name, "needs": ["sprite"]}]


def test_a_player_character_whose_clip_is_gone_is_cast_unvoiced(
    client: TestClient, root: Path, library: Library, pool: list[Character]
) -> None:
    data = pool[0].model_dump(mode="json") | {"id": "wren_abernethy", "name": "Wren Abernethy"}
    player = library.save_clip(library.create(data).id, clip())
    library.clip(player).unlink()

    world = made(client, count=1, picks=[player.id])

    (npc,) = load_npcs(cast_npcs(root / world["name"]))
    assert npc.voice.reference_clip is None
    assert not (root / world["name"] / "clips").exists()
    assert world["missing"][0]["needs"] == ["voice", "sprite"]


@pytest.mark.parametrize("where", [DEFAULT_PATH.parent / "worlds", CONTENT / "worlds"])
def test_new_worlds_never_go_in_todays_data_directory_or_content(
    app: Starlette, client: TestClient, where: Path
) -> None:
    existed = where.exists()
    app.state.worlds = Worlds(where)

    response = client.post("/api/worlds", json={"count": 3})

    assert response.status_code == 409
    assert where.exists() == existed


@pytest.mark.anyio
async def test_the_village_starts_with_the_new_cast(
    root: Path, library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    from simile.worlds import NewWorld

    picks = [A, B, C, D, E, F]
    world = Worlds(root).create(NewWorld(count=6, picks=picks), library)
    monkeypatch.setenv("SIMILE_DB", str(root / world.name / "simile.db"))
    app = create_app()
    app.state.world = World(Clock(datetime(2026, 10, 18, 8, tzinfo=UTC)), FakeWallClock())
    app.state.headless = True

    async with app.router.lifespan_context(app):
        await world_of(app).loop.run(timedelta(minutes=1))

    assert sorted(behaviour_of(app).npcs) == sorted(picks)
    assert (root / world.name / "simile.db").exists()
