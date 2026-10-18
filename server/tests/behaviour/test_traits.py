import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, BehaviourConfig, Goal, Need
from simile.behaviour.simulate import report, simulate
from simile.casting import Cast, Resident, village_houses, write_cast
from simile.characters.pool import load_pool
from simile.npc import load_npcs
from simile.schema import CoreValue, Npc, Traits
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_maps

MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)
NPCS = load_npcs()
STAY_HOME = DEFAULT_CONFIG.model_copy(update={"start_dwell": (120, 120)})


NO_WORK = {"workplace": None, "shifts": [], "pay": None}


def resident(id: str, home: str) -> Npc:
    values = {value: 0.5 for value in CoreValue}
    return NPCS[0].model_copy(
        update={"id": id, "home": home, "values": values, "craft": None, **NO_WORK}
    )


SOCIABLE, ALOOF = resident("sociable", "house_1"), resident("aloof", "house_2")
TRAITS = {"sociable": Traits(sociability=0.9), "aloof": Traits(sociability=0.1)}


def village(config: BehaviourConfig) -> tuple[World, Behaviour]:
    world = World(Clock(MORNING), FakeWallClock())
    movement = Movement(load_maps(), world.bus)
    behaviour = Behaviour(
        world.clock, world.bus, movement, [SOCIABLE, ALOOF], config=config, traits=TRAITS
    )
    world.loop.register(behaviour)
    world.loop.register(movement)
    behaviour.start()
    return world, behaviour


def run(world: World, minutes: float) -> None:
    for _ in range(round(minutes * 60 / STEP)):
        world.loop.tick()


def everyone(sociability: float) -> dict[str, Traits]:
    return {npc.id: Traits(sociability=sociability) for npc in NPCS}


def test_neutral_traits_reproduce_todays_day() -> None:
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)

    today, _ = asyncio.run(simulate(2, start=start, seed=2, talk=3))
    neutral, _ = asyncio.run(simulate(2, start=start, seed=2, traits=everyone(0.5), talk=3))

    assert report(neutral, 2, start, 2, 0) == report(today, 2, start, 2, 0)
    assert neutral.goals == today.goals
    assert neutral.started == today.started


def test_over_a_simulated_hour_sociable_residents_start_more_conversations() -> None:
    start = datetime(2026, 1, 1, 11, tzinfo=UTC)

    def started(sociability: float, seed: int) -> int:
        observer, _ = asyncio.run(
            simulate(1, start=start, seed=seed, traits=everyone(sociability), talk=3)
        )
        return sum(observer.started.values())

    low, high = [started(0.1, seed) for seed in range(3)], [started(0.9, seed) for seed in range(3)]

    assert all(h > lo for h, lo in zip(high, low, strict=True))
    assert sum(high) >= 2 * sum(low)


def test_sociability_makes_them_lonely_faster() -> None:
    world, behaviour = village(STAY_HOME)
    for mind in behaviour.minds.values():
        mind.needs[Need.SOCIAL] = 0.2

    run(world, 60)

    lonelier = {npc: behaviour.needs(npc)[Need.SOCIAL] - 0.2 for npc in TRAITS}
    spread = DEFAULT_CONFIG.sociability_spread
    assert lonelier["sociable"] == pytest.approx(lonelier["aloof"] * spread**1.6)
    assert lonelier["aloof"] > 0


def test_talking_meets_a_sociable_residents_need_more_slowly() -> None:
    config = STAY_HOME.model_copy(
        update={
            "rise": DEFAULT_CONFIG.rise | {Need.SOCIAL: 0.0},
            "rise_values": DEFAULT_CONFIG.rise_values | {Need.SOCIAL: {}},
            "company": 0.0,
        }
    )
    world, behaviour = village(config)
    behaviour.pause("sociable", "aloof")
    behaviour.pause("aloof", "sociable")
    for mind in behaviour.minds.values():
        mind.needs[Need.SOCIAL] = 0.9

    run(world, 3)

    met = {npc: 0.9 - behaviour.needs(npc)[Need.SOCIAL] for npc in TRAITS}
    assert behaviour.goal("sociable") == Goal(Activity.TALK, "aloof")
    assert met["aloof"] == pytest.approx(met["sociable"] * DEFAULT_CONFIG.sociability_spread**1.6)
    assert met["sociable"] > 0


def test_the_cast_gives_each_resident_their_traits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = sorted(load_pool(), key=lambda c: c.traits.sociability)
    chosen = [pool[0], pool[-1]]
    made = Cast(
        game_date=date(2026, 1, 1),
        seed=0,
        residents=[
            Resident(character=c, home=home)
            for c, home in zip(chosen, village_houses(), strict=False)
        ],
    )
    write_cast(made, tmp_path / "world")
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "world" / "simile.db"))

    observer, _ = asyncio.run(simulate(0.1, start=MORNING))

    assert set(observer.behaviour.npcs) == {c.id for c in chosen}
    assert observer.behaviour.traits == {c.id: c.traits for c in chosen}
    assert observer.behaviour.traits_of("someone_else") == Traits()
