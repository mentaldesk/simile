import json
import sqlite3
from datetime import timedelta
from itertools import count
from pathlib import Path

import pytest
from starlette.applications import Starlette

from simile.combat.shooting import Shooting
from simile.creatures.engine import Creature, Creatures, Sight, creatures_of
from simile.creatures.grid import Grid
from simile.creatures.kinds import BOT
from simile.creatures.placing import spawns, starting_haul
from simile.creatures.saved import SavedCreature
from simile.economy.economy import economy_of
from simile.persistence import player_of
from simile.persistence.lifespan import FRESH_ENV
from simile.player.pickups import Pickups
from simile.schema import (
    PLAYER_ID,
    CreatureKind,
    Item,
    ItemKind,
    MapTile,
    Material,
    Pile,
    Player,
    SideFacing,
    lamp,
)
from simile.sim import world_of
from simile.world import Point, movement_of
from simile.world.map import level_count, level_of, world_level

from .test_lifespan import run_village, saved
from .test_player import save_from_before_the_player

METRO = "metro"
FLOOR = 15
SCRAP = Item(id="scrap_steel", kind=ItemKind.SALVAGE, name="Scrap steel", weight=4.5)
BOARD = Item(id="circuit_board", kind=ItemKind.SALVAGE, name="Circuit board", weight=0.5)
PISTOL = Item(
    id="pistol",
    kind=ItemKind.WEAPON,
    name="Plastic pistol",
    weight=0.5,
    material=Material.PLASTIC,
    rounds=6,
    capacity=6,
    condition=1.0,
)
BRIEFLY = timedelta(seconds=1)


def beside_the_salvage(app: Starlette) -> None:
    """A bot let off its stretch, one step from the metro's scrap steel, with the circuit board
    further along, and the player on the map but out of its way."""
    bot = creatures_of(app).all["metro_bot_1"]
    bot.grid, bot.x, bot.route = Grid(bot.grid.town, BOT), 62.0, ()
    player = player_of(app)
    creatures_of(app).sense = lambda: Sight(player, Point(80.0, FLOOR, METRO))


def shoot(app: Starlette, bot: Creature) -> None:
    player, movement = player_of(app), movement_of(app)
    player.items = [lamp(), PISTOL]
    x = bot.cell[0]
    movement.track(PLAYER_ID, Point(x - 2.0, FLOOR, METRO))
    shooting = Shooting(player, movement, creatures_of(app))
    for _ in range(BOT.health):
        assert bot.id in creatures_of(app).all
        assert shooting.fire(SideFacing.EAST)
    movement.track(PLAYER_ID, Point(float(x), FLOOR, METRO))


def pickups(app: Starlette) -> Pickups:
    return Pickups(player_of(app), movement_of(app), economy_of(app), world_of(app).clock)


def pick_up(app: Starlette) -> bool:
    return pickups(app).pick_up()


def bots(app: Starlette) -> list[Creature]:
    return [c for c in creatures_of(app).all.values() if c.kind.id is CreatureKind.BOT]


@pytest.mark.anyio
async def test_a_destroyed_bots_haul_can_be_picked_up_and_it_doesnt_come_back(
    database: Path,
) -> None:
    placed: set[str] = set()
    started: list[Item] = []

    async def hunt(app: Starlette) -> None:
        started.extend(creatures_of(app).all["metro_bot_1"].haul)
        assert started
        beside_the_salvage(app)
        placed.update(creatures_of(app).all)

    async def destroy(app: Starlette) -> None:
        creatures, player = creatures_of(app), player_of(app)
        bot = creatures.all["metro_bot_1"]
        assert bot.haul == [*started, SCRAP, BOARD]
        assert {"metro_salvage_2", "metro_salvage_3"} <= player.taken.keys()
        assert creatures.collect("metro_salvage_2") == [], "it's already been taken"
        assert creatures.collect("no_such_pickup") == []

        shoot(app, bot)

        assert "metro_bot_1" not in creatures.all
        at = MapTile(map=METRO, x=bot.cell[0], y=FLOOR)
        assert player.left == [Pile(at=at, items=[*started, SCRAP, BOARD])]
        assert pick_up(app)
        assert player.left == []
        assert player.items == [lamp(), player.items[1], *started, SCRAP, BOARD]

    await run_village(timedelta(seconds=45), before=hunt, after=destroy)
    assert saved(database).creatures == {"metro_bot_1": SavedCreature(gone=True)}

    for _ in range(2):

        async def still_gone(app: Starlette) -> None:
            assert creatures_of(app).all.keys() == placed - {"metro_bot_1"}
            assert player_of(app).left == []

        await run_village(BRIEFLY, after=still_gone)
        assert saved(database).creatures == {"metro_bot_1": SavedCreature(gone=True)}


@pytest.mark.anyio
async def test_a_haul_joins_what_the_player_already_left_after_it(database: Path) -> None:
    collapse = Pile(at=MapTile(map=METRO, x=10, y=FLOOR), items=[BOARD], money=5.0)
    piles: list[Pile] = []

    async def destroy(app: Starlette) -> None:
        creatures, player = creatures_of(app), player_of(app)
        player.left = [collapse]
        bot = creatures.all["metro_bot_1"]
        bot.haul = [SCRAP]

        creatures.hurt(bot, BOT.health)

        haul = Pile(at=MapTile(map=METRO, x=bot.cell[0], y=FLOOR), items=[SCRAP])
        piles.extend([collapse, haul])
        assert player.left == piles

    await run_village(BRIEFLY, after=destroy)
    assert saved(database).player.left == piles


@pytest.mark.anyio
async def test_a_haul_nobody_has_picked_up_is_still_lying_after_a_restart(database: Path) -> None:
    started: list[Item] = []

    async def hunt(app: Starlette) -> None:
        started.extend(creatures_of(app).all["metro_bot_1"].haul)
        beside_the_salvage(app)

    async def destroy(app: Starlette) -> None:
        shoot(app, creatures_of(app).all["metro_bot_1"])
        player_of(app).items = [lamp()]

    await run_village(timedelta(seconds=45), before=hunt, after=destroy)

    async def collect_it(app: Starlette) -> None:
        assert [pile.items for pile in player_of(app).left] == [[*started, SCRAP, BOARD]]
        movement_of(app).track(PLAYER_ID, _at(player_of(app).left[0]))
        assert pick_up(app)
        assert player_of(app).items == [lamp(), *started, SCRAP, BOARD]

    await run_village(BRIEFLY, after=collect_it)


def _at(pile: Pile) -> Point:
    return Point(float(pile.at.x), float(pile.at.y), pile.at.map)


@pytest.mark.anyio
async def test_wounds_and_a_haul_outlast_two_restarts_and_the_haul_still_drops(
    database: Path,
) -> None:
    held: list[Item] = []

    async def wound(app: Starlette) -> None:
        creatures = creatures_of(app)
        bot = creatures.all["metro_bot_2"]
        creatures.hurt(bot, 4)
        bot.haul = [*bot.haul, SCRAP]
        held.extend(bot.haul)
        creatures.hurt(creatures.all["sewers_dog_1"], 2)

    await run_village(BRIEFLY, after=wound)

    async def unchanged(app: Starlette) -> None:
        creatures = creatures_of(app)
        bot = creatures.all["metro_bot_2"]
        assert (bot.wounds, bot.haul) == (4, held)
        assert bot.shown().health == 2 / 6
        assert creatures.all["sewers_dog_1"].wounds == 2
        assert creatures.all["metro_bot_1"].wounds == 0

    await run_village(BRIEFLY, after=unchanged)
    await run_village(BRIEFLY, after=unchanged)

    async def finish(app: Starlette) -> None:
        creatures = creatures_of(app)
        creatures.hurt(creatures.all["metro_bot_2"], 2)
        assert [pile.items for pile in player_of(app).left] == [held]

    await run_village(BRIEFLY, after=finish)
    assert saved(database).creatures == {
        "metro_bot_2": SavedCreature(gone=True),
        "sewers_dog_1": SavedCreature(wounds=2),
    }


@pytest.mark.anyio
async def test_dogs_and_bats_stay_dead_and_rats_keep_respawning(database: Path) -> None:
    async def kill(app: Starlette) -> None:
        creatures = creatures_of(app)
        for id in ("sewers_dog_1", "sewers_bat_1", "sewers_rat_1"):
            creature = creatures.all[id]
            creatures.hurt(creature, creature.kind.health)

    await run_village(BRIEFLY, after=kill)
    assert saved(database).creatures == {
        "sewers_dog_1": SavedCreature(gone=True),
        "sewers_bat_1": SavedCreature(gone=True),
    }

    async def after_restart(app: Starlette) -> None:
        creatures = creatures_of(app).all
        assert "sewers_dog_1" not in creatures and "sewers_bat_1" not in creatures
        assert creatures["sewers_rat_1"].down is None

    await run_village(BRIEFLY, after=after_restart)


@pytest.mark.anyio
async def test_a_save_with_no_creatures_loads_with_every_creature_whole(database: Path) -> None:
    whole: set[str] = set()

    async def remember(app: Starlette) -> None:
        whole.update(creatures_of(app).all)

    await run_village(BRIEFLY, after=remember)
    database.unlink()
    save_from_before_the_player(database)
    assert saved(database).creatures == {}

    async def check(app: Starlette) -> None:
        creatures: Creatures = creatures_of(app)
        assert creatures.all.keys() == whole
        assert not any(creature.wounds for creature in creatures.all.values())
        assert all(bool(c.haul) is (c in bots(app)) for c in creatures.all.values())
        assert player_of(app) == Player()

    await run_village(BRIEFLY, after=check)


def old_save(database: Path, creatures: dict[str, object]) -> None:
    """The saved world, with `creatures` as a save from before starting hauls wrote them."""
    with sqlite3.connect(database) as db:
        [data] = db.execute("SELECT data FROM saved_world WHERE id = 0").fetchone()
        world = json.loads(data)
        world["creatures"] = creatures
        db.execute("UPDATE saved_world SET data = ? WHERE id = 0", (json.dumps(world),))


@pytest.mark.anyio
async def test_an_old_save_keeps_its_destroyed_bots_and_gives_each_living_one_its_haul_once(
    database: Path,
) -> None:
    await run_village(BRIEFLY)
    old_save(
        database,
        {
            "metro_bot_1": {"gone": True},
            "metro_bot_2": {"wounds": 4, "haul": [SCRAP.model_dump(mode="json")]},
        },
    )
    held: list[Item] = []

    async def first(app: Starlette) -> None:
        assert "metro_bot_1" not in creatures_of(app).all
        bot = creatures_of(app).all["metro_bot_2"]
        assert bot.wounds == 4 and len(bot.haul) in (2, 3) and bot.haul[-1] == SCRAP
        held.extend(bot.haul)
        assert creatures_of(app).all["sewers_bot_1"].haul
        held.extend(creatures_of(app).all["sewers_bot_1"].haul)

    await run_village(BRIEFLY, after=first)
    assert saved(database).creatures["metro_bot_1"] == SavedCreature(gone=True)

    async def again(app: Starlette) -> None:
        assert "metro_bot_1" not in creatures_of(app).all
        creatures = creatures_of(app).all
        assert [*creatures["metro_bot_2"].haul, *creatures["sewers_bot_1"].haul] == held

    await run_village(BRIEFLY, after=again)
    await run_village(BRIEFLY, after=again)
    entry = saved(database).creatures["metro_bot_2"]
    assert entry.stocked and entry.haul == held[: len(entry.haul)]


@pytest.mark.anyio
async def test_a_bots_untouched_start_is_the_same_after_a_restart_and_what_changes_is_saved(
    database: Path,
) -> None:
    held: dict[str, list[Item]] = {}

    async def first(app: Starlette) -> None:
        held.update({bot.id: bot.haul for bot in bots(app)})
        assert all(held.values())

    await run_village(BRIEFLY, after=first)
    assert saved(database).creatures == {}

    async def collects(app: Starlette) -> None:
        assert {bot.id: bot.haul for bot in bots(app)} == held
        bot = creatures_of(app).all["metro_bot_1"]
        bot.haul = [*bot.haul, SCRAP]

    await run_village(BRIEFLY, after=collects)
    both = [*held["metro_bot_1"], SCRAP]
    assert saved(database).creatures == {"metro_bot_1": SavedCreature(haul=both, stocked=True)}

    async def kept(app: Starlette) -> None:
        assert {bot.id: bot.haul for bot in bots(app)} == held | {"metro_bot_1": both}

    await run_village(BRIEFLY, after=kept)


@pytest.mark.anyio
@pytest.mark.parametrize("level", range(level_count()))
async def test_every_bot_drops_what_it_started_with_and_none_of_it_lies_on_its_map(
    database: Path, monkeypatch: pytest.MonkeyPatch, level: int
) -> None:
    seed = next(seed for seed in count() if level_of(seed, level_count()) == level)
    monkeypatch.setattr("simile.story.town.world_seed", lambda: seed)

    async def destroy(app: Starlette) -> None:
        assert world_level() == level
        creatures, player = creatures_of(app), player_of(app)
        assert player == Player(), "no pickup was given up to stock them"
        placed = {spawn.id for _, spawn in spawns(level=level) if spawn.kind is CreatureKind.BOT}
        assert {bot.id for bot in bots(app)} == placed
        assert len(placed) >= 3 and {"metro_bot_1", "metro_bot_2"} < placed
        lying = pickups(app).lying.values()
        for bot in bots(app):
            start = bot.haul
            on_its_map = {i.id for pile in lying if pile.at.map == bot.map for i in pile.items}
            assert start == starting_haul(bot.id, seed, on_its_map), bot.id
            assert len(start) in (1, 2), bot.id
            assert not {item.id for item in start} & on_its_map, bot.id
            assert all(economy_of(app).config.salvage[item.id] > 0 for item in start), bot.id

            creatures.hurt(bot, BOT.health)

            assert player.left[-1].items == start, bot.id

    await run_village(BRIEFLY, after=destroy)


@pytest.mark.anyio
async def test_starting_fresh_brings_them_back(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def kill(app: Starlette) -> None:
        creatures = creatures_of(app)
        creatures.hurt(creatures.all["metro_bot_1"], BOT.health)

    await run_village(BRIEFLY, after=kill)

    monkeypatch.setenv(FRESH_ENV, "1")

    async def back(app: Starlette) -> None:
        assert "metro_bot_1" in creatures_of(app).all

    await run_village(BRIEFLY, after=back)
