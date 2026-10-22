import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.applications import Starlette

from simile.app import create_app
from simile.memory import MemoryStore
from simile.persistence import WorldStore, capture, player_of
from simile.persistence.lifespan import FRESH_ENV
from simile.schema import PRESENT, SOLD, Bionic, Body, Item, ItemKind, Player, lamp
from simile.sim import world_of

from .test_lifespan import run_village, saved
from .test_state import Village

OLD_SAVE = (Path(__file__).parent / "save_before_the_player.json").read_text()

DELVING = Player(
    money=120,
    items=[
        lamp().model_copy(update={"charge": 0.35}),
        Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5),
    ],
    body=Body(legs=Bionic.HYDRAULIC_LEGS, vertebra=Bionic.DATAJACK, left_kidney=SOLD),
    hunger=0.55,
)


@contextmanager
def opened(path: Path) -> Iterator[WorldStore]:
    with MemoryStore(path) as memory, WorldStore(memory) as store:
        yield store


def save_from_before_the_player(path: Path) -> None:
    with opened(path):
        pass
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO saved_world (id, data) VALUES (0, ?)", (OLD_SAVE,))


def test_a_save_from_before_the_player_loads_with_the_starting_player(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    save_from_before_the_player(path)

    with opened(path) as store:
        loaded = store.load()

    assert "player" not in json.loads(OLD_SAVE)
    assert loaded is not None and loaded.npcs.keys() == {"desmond", "henrietta"}
    assert loaded.player == Player()
    assert all(state == PRESENT for _, state in loaded.player.body)
    assert loaded.player.money == 0
    assert loaded.player.items == [lamp()] and loaded.player.items[0].charge == 1


def test_the_player_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "simile.db"
    with opened(path) as store:
        store.save(capture(Village().behaviour, player=DELVING))

    with opened(path) as reopened:
        loaded = reopened.load()

    assert loaded is not None and loaded.player == DELVING


def test_capture_saves_the_starting_player_without_one() -> None:
    assert capture(Village().behaviour).player == Player()


def test_capture_takes_a_copy_of_the_player() -> None:
    player = DELVING.model_copy(deep=True)
    world = capture(Village().behaviour, player=player)

    player.money = 0
    player.items.clear()
    player.body.right_eye = Bionic.INFRARED_EYE

    assert world.player == DELVING


async def delve(app: Starlette) -> None:
    player = player_of(app)
    player.money = DELVING.money
    player.items = DELVING.model_copy(deep=True).items
    player.body = DELVING.body.model_copy()
    player.hunger = DELVING.hunger


@pytest.mark.anyio
async def test_a_saved_player_survives_a_restart(database: Path) -> None:
    await run_village(timedelta(minutes=5), after=delve)
    assert saved(database).player == DELVING

    async def resumed(app: Starlette) -> None:
        assert player_of(app) == DELVING

    await run_village(timedelta(minutes=5), before=resumed)
    assert saved(database).player == DELVING


@pytest.mark.anyio
async def test_a_player_taken_before_startup_is_the_one_restored_and_saved(
    database: Path,
) -> None:
    await run_village(timedelta(minutes=1), after=delve)
    app = create_app()
    early = player_of(app)

    async def spend(app: Starlette) -> None:
        assert player_of(app) is early
        assert early == DELVING
        early.money = 7.5

    await run_village(timedelta(minutes=1), app=app, after=spend)
    assert saved(database).player.money == 7.5


@pytest.mark.anyio
async def test_a_save_from_before_the_player_starts_them_afresh(database: Path) -> None:
    save_from_before_the_player(database)

    async def starting(app: Starlette) -> None:
        assert world_of(app).clock.now == datetime(2026, 1, 3, 8, 30, tzinfo=UTC)
        assert player_of(app) == Player()

    await run_village(timedelta(minutes=1), before=starting)
    assert saved(database).player == Player()


@pytest.mark.anyio
async def test_a_fresh_start_has_the_starting_player(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await run_village(timedelta(minutes=1), after=delve)
    assert saved(database).player == DELVING
    monkeypatch.setenv(FRESH_ENV, "1")

    async def starting(app: Starlette) -> None:
        assert player_of(app) == Player()

    await run_village(timedelta(minutes=1), before=starting)
    assert saved(database).player == Player()


@pytest.mark.anyio
async def test_with_an_in_memory_database_the_player_starts_afresh_unsaved() -> None:
    async def check(app: Starlette) -> None:
        assert not hasattr(app.state, "persistence")
        assert player_of(app) is player_of(app) == Player()

    await run_village(timedelta(minutes=1), before=check)
