import json
import shutil
import time
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.persistence import player_of
from simile.player.health import DEFAULT_HEALTH, Health, beds_in, health_of
from simile.player.sync import PlayerSync
from simile.schema import PLAYER_ID, SOLD, Body, Effect, EffectKind, Player
from simile.sim import Clock, EventBus, World, world_of
from simile.world import Movement, Point, movement_of
from simile.world.map import FLOORS, MAP_DIR, load_maps
from simile.world.paths import Spot

MAPS = load_maps()
NOW = datetime(2026, 1, 1, 12, tzinfo=UTC)
HOUR = 3600.0
TAKES = 0.05
"""What a bite takes here; a rat's own is in `simile.creatures`."""
TUNNEL = Point(65, 15, "metro")
HOME = Point(13, 2, "maker_space_floor_0")
LOFT = "maker_space_floor_2"
BED = Point(1, 2, LOFT)
SPEED = 60.0
BITE, INFECTION = EffectKind.RAT_BITE, EffectKind.INFECTION
ONE_KIDNEY = Body(left_kidney=SOLD)

MakePackage = Callable[[dict[str, str]], str]


class Patient:
    def __init__(
        self,
        player: Player | None = None,
        at: Point = TUNNEL,
        beds: Collection[Spot] | None = None,
    ) -> None:
        self.player = player or Player()
        self.playing = True
        self.collapses = 0
        self.movement = Movement(MAPS, EventBus())
        self.movement.track(PLAYER_ID, at)
        self.clock = Clock(NOW)
        self.health = Health(
            self.player,
            self.movement,
            self.clock,
            playing=lambda: self.playing,
            collapse=self.collapse,
            beds=beds,
        )

    def collapse(self) -> None:
        self.collapses += 1

    def run(self, hours: float, step: float = 60.0) -> None:
        for _ in range(round(hours * HOUR / step)):
            self.clock.advance(step)
            self.health.tick(step)

    def rest(self, seconds: float, step: float = 0.1) -> None:
        """Runs `seconds` of real time at `SPEED`."""
        self.clock.speed = SPEED
        self.run(seconds * SPEED / HOUR, step * SPEED)

    def strength(self, kind: EffectKind) -> float:
        effect = self.health.effect(kind)
        return 0.0 if effect is None else effect.strength


def test_damage_takes_health() -> None:
    patient = Patient()

    patient.health.hurt(0.3)
    patient.health.bite(TAKES)

    assert patient.player.health == pytest.approx(0.7 - TAKES)
    assert patient.collapses == 0


def test_it_comes_back_slowly_and_faster_at_home() -> None:
    out, home = Patient(Player(health=0.2)), Patient(Player(health=0.2), at=HOME)

    out.run(1)
    home.run(1)

    assert out.player.health == pytest.approx(0.3)
    assert home.player.health == pytest.approx(0.7)
    home.run(1)
    assert home.player.health == 1


def home_floors(directory: Path, bed: bool) -> Path:
    """The maker space's floor maps, with a bed at the west end of the loft if `bed`."""
    (directory / FLOORS).mkdir()
    for floor in range(3):
        name = f"maker_space_floor_{floor}.tmj"
        shutil.copy(MAP_DIR / FLOORS / name, directory / FLOORS / name)
    if bed:
        path = directory / FLOORS / f"{LOFT}.tmj"
        data = json.loads(path.read_text())
        [furniture] = [layer for layer in data["layers"] if layer["name"] == "furniture"]
        piece = {"name": "bed", "type": "bed", "x": 16, "y": 32, "width": 32, "height": 16}
        furniture["objects"].append({**piece, "id": 999, "rotation": 0, "visible": True})
        path.write_text(json.dumps(data))
    return directory


def home_beds(directory: Path, bed: bool = True) -> frozenset[Spot]:
    return beds_in(MAPS[HOME.map].location("maker_space"), home_floors(directory, bed))


def test_the_beds_are_read_from_the_home_floor_maps(tmp_path: Path) -> None:
    assert home_beds(tmp_path) == {Spot(LOFT, 1, 2), Spot(LOFT, 2, 2)}


def test_resting_in_bed_heals_from_a_tenth_to_full_in_about_three_real_seconds(
    tmp_path: Path,
) -> None:
    patient = Patient(Player(health=0.1), at=BED, beds=home_beds(tmp_path))

    patient.rest(2.5)
    assert patient.player.health == pytest.approx(0.1 + 2.5 / DEFAULT_HEALTH.rest)
    patient.rest(0.3)
    assert patient.player.health == 1


def test_off_the_bed_healing_is_unchanged(tmp_path: Path) -> None:
    beds = home_beds(tmp_path)
    out = Patient(Player(health=0.1), beds=beds)
    home = Patient(Player(health=0.1), at=Point(5, 2, LOFT), beds=beds)

    out.rest(3)
    home.rest(3)

    assert out.player.health == pytest.approx(0.1 + DEFAULT_HEALTH.heal * 3 * SPEED / HOUR)
    assert home.player.health == pytest.approx(0.1 + DEFAULT_HEALTH.heal_at_home * 3 * SPEED / HOUR)


def test_a_home_without_a_bed_heals_as_it_does_today(tmp_path: Path) -> None:
    beds = home_beds(tmp_path, bed=False)
    patient = Patient(Player(health=0.1), at=BED, beds=beds)

    patient.rest(3)

    assert beds == frozenset()
    assert patient.player.health == pytest.approx(
        0.1 + DEFAULT_HEALTH.heal_at_home * 3 * SPEED / HOUR
    )


def test_an_infection_keeps_health_from_coming_back_in_bed(tmp_path: Path) -> None:
    patient = Patient(Player(health=0.5), at=BED, beds=home_beds(tmp_path))
    patient.health.afflict(INFECTION, 1.0)

    patient.rest(3)

    assert patient.player.health < 0.5


def test_nothing_changes_while_nobody_is_playing() -> None:
    patient = Patient(Player(health=0.5))
    patient.health.bite(TAKES)
    patient.playing = False

    patient.run(5)

    assert patient.player.health == pytest.approx(0.5 - TAKES)
    assert patient.strength(BITE) == DEFAULT_HEALTH.bitten


def test_at_none_they_collapse_and_wake_with_some_health() -> None:
    patient = Patient(Player(health=0.04))

    patient.health.bite(TAKES)

    assert patient.collapses == 1
    assert patient.player.health == DEFAULT_HEALTH.waking


def test_a_single_bite_fades_before_it_can_turn() -> None:
    patient = Patient()
    patient.health.bite(TAKES)

    patient.run(DEFAULT_HEALTH.infects + 1)

    assert patient.player.effects == []


def test_each_bite_makes_it_worse_from_when_they_were_first_bitten() -> None:
    patient = Patient()
    patient.health.bite(TAKES)
    patient.run(0.5)

    patient.health.bite(TAKES)

    [bite] = patient.player.effects
    assert bite.strength == pytest.approx(2 * DEFAULT_HEALTH.bitten - 0.5 * 0.25)
    assert bite.since == NOW


def test_a_handful_of_bites_turns_infected_and_lasts_until_its_treated() -> None:
    patient = Patient()
    for _ in range(5):
        patient.health.bite(TAKES)

    patient.run(DEFAULT_HEALTH.infects)
    [infection] = patient.player.effects
    assert infection.kind is INFECTION and infection.fades is None
    assert infection.strength == pytest.approx(1 - DEFAULT_HEALTH.infects * 0.25)
    patient.run(48)

    assert patient.strength(INFECTION) == infection.strength


def test_an_infection_takes_health_and_lets_none_come_back_even_at_home() -> None:
    patient = Patient(Player(health=0.5), at=HOME)
    patient.health.afflict(INFECTION, 1.0)

    patient.run(5)

    assert patient.player.health == pytest.approx(0.5 - 5 * DEFAULT_HEALTH.infection)


def test_with_one_kidney_an_effect_fades_half_as_fast() -> None:
    two, one = Patient(), Patient(Player(body=ONE_KIDNEY))
    for patient in (two, one):
        patient.health.afflict(EffectKind.RADIATION, 1.0)

    for patient in (two, one):
        patient.run(4)

    assert two.strength(EffectKind.RADIATION) == pytest.approx(0.8)
    assert one.strength(EffectKind.RADIATION) == pytest.approx(0.9)
    assert one.player.effects[0].fades == pytest.approx(0.025)


def test_with_one_kidney_two_bites_last_long_enough_to_turn() -> None:
    two, one = Patient(), Patient(Player(body=ONE_KIDNEY))
    for patient in (two, one):
        patient.health.bite(TAKES)
        patient.health.bite(TAKES)

    for patient in (two, one):
        patient.run(DEFAULT_HEALTH.infects)

    assert two.player.effects == []
    assert [effect.kind for effect in one.player.effects] == [INFECTION]


def test_selling_a_kidney_slows_what_they_have_already() -> None:
    patient = Patient()
    patient.health.afflict(EffectKind.RADIATION, 1.0)
    patient.player.body = ONE_KIDNEY

    patient.run(4)

    assert patient.strength(EffectKind.RADIATION) == pytest.approx(0.9)


def test_a_change_to_health_or_an_effects_strength_alone_waits_for_a_hundredth() -> None:
    since = NOW - timedelta(hours=1)
    bite = Effect(kind=BITE, strength=0.5, fades=0.25, since=since)
    player, sent = Player(health=0.5, effects=[bite]), []
    sync = PlayerSync(player, lambda: None, sent.append)

    player.health = 0.505
    sync.update()
    player.effects = [bite.model_copy(update={"strength": 0.495})]
    sync.update()
    assert sent == []
    player.health = 0.51
    sync.update()
    player.effects = [bite.model_copy(update={"strength": 0.48})]
    sync.update()
    player.effects = []
    sync.update()

    assert [(m.player.health, m.player.effects) for m in sent] == [
        (0.51, [bite.model_copy(update={"strength": 0.495})]),
        (0.51, [bite.model_copy(update={"strength": 0.48})]),
        (0.51, []),
    ]


def make_app(make_package: MakePackage) -> Starlette:
    lifespans = ("behaviour", "economy", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in lifespans}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["player/lifespan.py"] = "from simile.player.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(NOW))
    return app


def next_of(ws: Any, type: str) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == type:
            return message
    raise AssertionError(f"no {type}")


def test_a_bite_at_no_health_collapses_them_for_health_and_they_wake_at_home(
    make_package: MakePackage,
) -> None:
    app = make_app(make_package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        player = player_of(app)
        next_of(ws, "player_state")
        ws.send_json({"type": "player_move", "position": {"x": 65, "y": 15, "map": "metro"}})
        deadline = time.monotonic() + 2
        while client.portal.call(movement_of(app).entities).get(PLAYER_ID) != TUNNEL:
            assert time.monotonic() < deadline, "the server never had the player there"
            time.sleep(0.001)
        client.portal.call(lambda: setattr(player, "health", 0.01))
        client.portal.call(health_of(app).bite, TAKES)
        collapsed = next_of(ws, "player_collapsed")
        client.portal.call(world_of(app).loop.tick)
        woken = next_of(ws, "player_state")

    assert collapsed["cause"] == "health"
    assert collapsed["position"]["map"] == "maker_space_floor_0"
    assert woken["player"]["health"] == pytest.approx(DEFAULT_HEALTH.waking, abs=0.01)
    assert woken["player"]["hunger"] < 0.01
    assert [effect["kind"] for effect in woken["player"]["effects"]] == ["rat_bite"]
