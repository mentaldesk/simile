from datetime import timedelta
from pathlib import Path

import pytest
from starlette.applications import Starlette

from simile.combat.shooting import Shooting
from simile.creatures.engine import Creature, Creatures, Sight, creatures_of
from simile.creatures.grid import Grid
from simile.creatures.kinds import BOT
from simile.creatures.saved import SavedCreature
from simile.economy.economy import economy_of
from simile.persistence import player_of
from simile.persistence.lifespan import FRESH_ENV
from simile.player.pickups import Pickups
from simile.schema import (
    PLAYER_ID,
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


def pick_up(app: Starlette) -> bool:
    return Pickups(player_of(app), movement_of(app), economy_of(app), world_of(app).clock).pick_up()


@pytest.mark.anyio
async def test_a_destroyed_bots_haul_can_be_picked_up_and_it_doesnt_come_back(
    database: Path,
) -> None:
    placed: set[str] = set()

    async def hunt(app: Starlette) -> None:
        beside_the_salvage(app)
        placed.update(creatures_of(app).all)

    async def destroy(app: Starlette) -> None:
        creatures, player = creatures_of(app), player_of(app)
        bot = creatures.all["metro_bot_1"]
        assert bot.haul == [SCRAP, BOARD]
        assert {"metro_salvage_2", "metro_salvage_3"} <= player.taken.keys()
        assert creatures.collect("metro_salvage_2") == [], "it's already been taken"
        assert creatures.collect("no_such_pickup") == []

        shoot(app, bot)

        assert "metro_bot_1" not in creatures.all
        at = MapTile(map=METRO, x=bot.cell[0], y=FLOOR)
        assert player.left == [Pile(at=at, items=[SCRAP, BOARD])]
        assert pick_up(app)
        assert player.left == [] and player.items == [lamp(), player.items[1], SCRAP, BOARD]

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
    async def hunt(app: Starlette) -> None:
        beside_the_salvage(app)

    async def destroy(app: Starlette) -> None:
        shoot(app, creatures_of(app).all["metro_bot_1"])
        player_of(app).items = [lamp()]

    await run_village(timedelta(seconds=45), before=hunt, after=destroy)

    async def collect_it(app: Starlette) -> None:
        assert [pile.items for pile in player_of(app).left] == [[SCRAP, BOARD]]
        movement_of(app).track(PLAYER_ID, _at(player_of(app).left[0]))
        assert pick_up(app)
        assert player_of(app).items == [lamp(), SCRAP, BOARD]

    await run_village(BRIEFLY, after=collect_it)


def _at(pile: Pile) -> Point:
    return Point(float(pile.at.x), float(pile.at.y), pile.at.map)


@pytest.mark.anyio
async def test_wounds_and_a_haul_outlast_two_restarts_and_the_haul_still_drops(
    database: Path,
) -> None:
    async def wound(app: Starlette) -> None:
        creatures = creatures_of(app)
        bot = creatures.all["metro_bot_2"]
        creatures.hurt(bot, 4)
        bot.haul = [SCRAP]
        creatures.hurt(creatures.all["sewers_dog_1"], 2)

    await run_village(BRIEFLY, after=wound)

    async def unchanged(app: Starlette) -> None:
        creatures = creatures_of(app)
        bot = creatures.all["metro_bot_2"]
        assert (bot.wounds, bot.haul) == (4, [SCRAP])
        assert bot.shown().health == 2 / 6
        assert creatures.all["sewers_dog_1"].wounds == 2
        assert creatures.all["metro_bot_1"].wounds == 0

    await run_village(BRIEFLY, after=unchanged)
    await run_village(BRIEFLY, after=unchanged)

    async def finish(app: Starlette) -> None:
        creatures = creatures_of(app)
        creatures.hurt(creatures.all["metro_bot_2"], 2)
        assert [pile.items for pile in player_of(app).left] == [[SCRAP]]

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
        assert not any(creature.wounds or creature.haul for creature in creatures.all.values())
        assert player_of(app) == Player()

    await run_village(BRIEFLY, after=check)


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
