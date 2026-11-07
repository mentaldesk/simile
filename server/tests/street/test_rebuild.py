import json
import math
from collections import Counter
from collections.abc import Callable
from datetime import timedelta

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import Behaviour
from simile.clinic.clinic import Clinic
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import player_of
from simile.player.config import DEFAULT_CONFIG, SALVAGE
from simile.player.corpses import Death
from simile.player.pickups import Pickups
from simile.player.trade import Trade
from simile.protocol import Vital, hub_of
from simile.schema import PLAYER_ID, SOLD, Bionic, Body, ItemKind, Mind
from simile.sim import world_of
from simile.street.charge import Ways
from simile.street.jump import JUMP, LEGS
from simile.street.metro import ARRIVAL, LIFT_FOOT, METRO, REBUILD_PARTS
from simile.street.sewers import LANDING, SEWERS
from simile.world import Point, movement_of
from simile.world.map import PickupKind, TownMap
from simile.world.paths import Spot

MakePackage = Callable[[dict[str, str]], str]

DAY = timedelta(hours=24)
WORLD_LIFESPAN = {"world/lifespan.py": "from simile.world.lifespan import lifespan\n"}
CLINIC = Point(6, 2, "clinic_floor_0")
STALL = Point(26, 15, METRO)
BED = Spot("maker_space_floor_2", 5, 2)
FIRST_BODY = Body(
    legs=Bionic.BIONIC_LEGS,
    vertebra=Bionic.DATAJACK,
    stomach=Bionic.POWER_CELL,
    left_kidney=SOLD,
)
KNOWN = [Bionic.POWER_CELL, Bionic.DATAJACK, Bionic.BIONIC_LEGS]
PARTS = [SALVAGE[f"metro_salvage_{number}"].item for number in REBUILD_PARTS]
WAITS = 14
"""The most days it could wait for, well past any timer."""


class Run:
    """The player's real pickups, trade, clinic and death, moving by `player_move` through the
    world's guard."""

    def __init__(self, app: Starlette) -> None:
        self.app, self.player = app, player_of(app)
        world = world_of(app)
        self.clock, self.movement = world.clock, movement_of(app)
        behaviour = Behaviour(
            self.clock, world.bus, self.movement, load_npcs()[:2], MemoryStore(":memory:"), seed=0
        )
        self.economy = Economy(self.clock, behaviour, player=self.player)
        self.pickups = Pickups(self.player, self.movement, self.economy, self.clock)
        self.trade = Trade(self.player, self.movement, self.economy, self.clock)
        self.clinic = Clinic(self.player, self.movement, self.economy, self.clock)
        self.death = Death(
            self.player, self.movement, self.clock, economy=self.economy, bed=lambda: BED
        )

    def go(self, x: float, y: float, map: str) -> None:
        position = json.dumps({"x": x, "y": y, "map": map})
        hub_of(self.app).receive(f'{{"type": "player_move", "position": {position}}}')

    def at(self) -> Point:
        return self.movement.position(PLAYER_ID)

    def wanted(self) -> Counter[str]:
        """What the doctor still needs for what's not fitted yet."""
        wanted: Counter[str] = Counter()
        for bionic in (Bionic.POWER_CELL, Bionic.BIONIC_LEGS):
            if not self.player.body.has(bionic):
                wanted.update(self.clinic.config.recipes[bionic].parts)
        return wanted

    def sell_what_is_spare(self) -> None:
        self.go(STALL.x, STALL.y, STALL.map)
        wanted = self.wanted()
        for item in list(self.player.items):
            if item.kind is ItemKind.LAMP:
                continue
            if wanted[item.id] > 0:
                wanted[item.id] -= 1
            else:
                self.trade.sell(item.id)

    def round(self) -> None:
        """Takes what lies on the metro that their own legs get to, selling all it can't use, and
        has the doctor fit what she can."""
        metro = self.movement.maps[METRO]
        own = Ways(metro)
        for pickup in metro.pickups:
            reached = own.cost((ARRIVAL.x, ARRIVAL.y), (pickup.x, pickup.y)) < math.inf
            if pickup.kind is PickupKind.SALVAGE and reached:
                self.go(pickup.x, pickup.y, METRO)
                self.pickups.pick_up()
                self.sell_what_is_spare()
        self.go(CLINIC.x, CLINIC.y, CLINIC.map)
        self.clinic.sell_part("left_kidney")
        self.clinic.fit(Bionic.POWER_CELL, "stomach")
        self.clinic.fit(Bionic.BIONIC_LEGS, "legs")


def past_the_gate(town: TownMap) -> tuple[int, int]:
    """The first cell past the gate that the bionic legs get to and their own don't."""
    [gate] = [light.area for light in town.light if light.id == "sewers_gate"]
    legs, own, landing = Ways(town, LEGS[Bionic.BIONIC_LEGS]), Ways(town), (LANDING.x, LANDING.y)
    return next(
        (x, y)
        for x in range(gate.x + gate.width, town.width)
        for y in range(town.height)
        if town.standing(x, y)
        and legs.cost(landing, (x, y)) < math.inf
        and own.cost(landing, (x, y)) == math.inf
    )


@pytest.mark.parametrize(
    ("taken_ago", "days"),
    [(timedelta(0), 6), (10 * DAY, 4)],
    ids=["just taken all of them", "taken long ago"],
)
def test_a_body_that_died_past_the_gate_with_its_lithium_rebuilds_and_reaches_its_corpse(
    make_package: MakePackage, taken_ago: timedelta, days: int
) -> None:
    app = create_app(make_package(WORLD_LIFESPAN))
    with TestClient(app):
        run = Run(app)
        player, town = run.player, run.movement.maps[SEWERS]
        lithium, *rest = PARTS
        player.body = FIRST_BODY
        player.mind = Mind(recipes=KNOWN)
        player.items = [*player.items, lithium, lithium, *rest]
        player.taken = {
            f"metro_salvage_{number}": run.clock.now - taken_ago for number in REBUILD_PARTS
        }
        fell = past_the_gate(town)
        run.go(LIFT_FOOT.x, LIFT_FOOT.y, METRO)
        run.go(LANDING.x, LANDING.y, SEWERS)
        run.go(*fell, SEWERS)
        assert run.at() == Point(*fell, SEWERS)

        run.death.die(Vital.HEALTH)

        [corpse] = player.corpses
        assert (corpse.at.map, corpse.at.x, corpse.at.y) == (SEWERS, *fell)
        assert sum(item.id == lithium.id for item in corpse.items) == 2
        assert {Bionic.POWER_CELL, Bionic.BIONIC_LEGS} <= set(corpse.bionics)
        assert player.body == Body()
        assert run.clinic.missing(Bionic.POWER_CELL) == {lithium.id: 3, "charge_controller": 1}
        assert Ways(town, JUMP).cost((LANDING.x, LANDING.y), fell) == math.inf

        waited = 0
        while not player.body.has(Bionic.BIONIC_LEGS) and waited < WAITS:
            run.round()
            if not player.body.has(Bionic.BIONIC_LEGS):
                run.clock.advance(DAY.total_seconds())
                waited += 1

        assert waited == days
        assert player.body.has(Bionic.POWER_CELL)
        assert Bionic.DATAJACK not in player.body.bionics

        run.go(LIFT_FOOT.x, LIFT_FOOT.y, METRO)
        run.go(LANDING.x, LANDING.y, SEWERS)
        assert run.at() == Point(LANDING.x, LANDING.y, SEWERS)

        for x, y in Ways(town, LEGS[Bionic.BIONIC_LEGS]).cells((LANDING.x, LANDING.y), fell):
            run.go(x, y, SEWERS)
            assert run.at() == Point(x, y, SEWERS)
        assert math.dist((run.at().x, run.at().y), fell) <= DEFAULT_CONFIG.reach
