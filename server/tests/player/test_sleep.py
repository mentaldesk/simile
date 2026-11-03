import asyncio
import random
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour.config import DEFAULT_CONFIG as DEFAULT_BEHAVIOUR
from simile.behaviour.config import Activity
from simile.llm import LLMClient
from simile.llm.provider import Request, Usage
from simile.player.health import DEFAULT_HEALTH, Health
from simile.player.sleep import DEFAULT_SLEEP, NIGHT_STARTS, Sleep
from simile.schema import PLAYER_ID, Effect, EffectKind, Player
from simile.sim import Clock, ConversationStarted, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
DAY = datetime(2026, 1, 1, tzinfo=UTC)
BED = Point(5, 2, "maker_space_floor_2")
OFF_THE_BED = Point(7, 2, "maker_space_floor_2")
SPEED = DEFAULT_SLEEP.speed
SLEEP = Activity.SLEEP


def at(hours: float) -> datetime:
    return DAY + timedelta(hours=hours)


def infection(strength: float = 0.5) -> Effect:
    return Effect(kind=EffectKind.INFECTION, strength=strength, fades=None, since=DAY)


class Sleeper:
    def __init__(self, hours: float, player: Player | None = None, speed: float = 1.0) -> None:
        self.player = player or Player()
        self.world = World(Clock(at(hours), speed), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.movement.track(PLAYER_ID, BED)
        self.sleep: Sleep
        self.health = Health(
            self.player, self.movement, self.world.clock, night=lambda: self.sleep.night()
        )
        self.sleep = Sleep(self.health, self.world.clock)
        self.woke: tuple[datetime, float] | None = None
        self.skipped = False
        self.world.loop.register(self.health)
        self.world.loop.register(self.sleep)
        self.world.loop.register(self)

    def tick(self, dt: float) -> None:
        if self.skipped and not self.sleep.skipping and self.woke is None:
            self.woke = self.world.clock.now, self.world.loop.wall.now()
        self.skipped = self.skipped or self.sleep.skipping

    def run(self, until: float) -> None:
        asyncio.run(self.world.loop.run(at(until) - self.world.clock.now))

    def real(self, seconds: float) -> None:
        """Runs `seconds` of real time."""
        wall = self.world.loop.wall
        start = wall.now()
        while wall.now() - start < seconds:
            asyncio.run(self.world.loop.run(timedelta(seconds=self.world.loop.dt())))


def test_a_rest_at_night_at_full_health_sleeps_until_seven_then_gets_up() -> None:
    sleeper = Sleeper(2.75)

    assert sleeper.health.rest(True)
    sleeper.real(1)
    skipping, speed = sleeper.world.clock.skipping, sleeper.world.clock.speed
    sleeper.run(7.01)

    assert (skipping, speed) == (True, SPEED)
    assert not sleeper.health.resting()
    assert sleeper.world.clock.speed == 1
    assert not sleeper.world.clock.skipping
    assert sleeper.player.health == 1
    assert sleeper.woke is not None
    woke, woke_at = sleeper.woke
    assert at(7) <= woke < at(7) + timedelta(seconds=10)
    lie_down = DEFAULT_HEALTH.lie_down
    assert woke_at == pytest.approx(lie_down + 4.25 * 3600 / SPEED, abs=0.05)


def test_a_rest_at_night_heals_them_to_full_on_the_way() -> None:
    sleeper = Sleeper(23, Player(health=0.2))

    assert sleeper.health.rest(True)
    sleeper.run(24 + 7.01)

    assert sleeper.player.health == 1
    assert not sleeper.health.resting()
    assert sleeper.world.clock.speed == 1


def test_infected_at_night_they_sleep_until_morning_without_healing() -> None:
    sleeper = Sleeper(1, Player(health=0.5, effects=[infection()]))

    assert sleeper.health.rest(True)
    sleeper.run(6.5)
    sleeping = sleeper.health.sleeping()
    sleeper.run(7.01)

    assert sleeping
    assert sleeper.player.health < 0.5
    assert not sleeper.health.resting()
    assert sleeper.world.clock.speed == 1


def test_moving_off_the_bed_stops_the_skip_and_restores_the_clock() -> None:
    sleeper = Sleeper(2.75, speed=2)
    sleeper.health.rest(True)
    sleeper.real(1)
    skipping = sleeper.world.clock.skipping

    sleeper.movement.track(PLAYER_ID, OFF_THE_BED)
    sleeper.world.loop.tick()

    assert skipping
    assert not sleeper.world.clock.skipping
    assert sleeper.world.clock.speed == 2
    assert sleeper.world.clock.time_of_day < 7


def test_the_client_leaving_stops_the_skip() -> None:
    sleeper = Sleeper(2.75)
    playing = [True]
    sleeper.sleep.playing = lambda: playing[0]
    sleeper.health.rest(True)
    sleeper.real(1)
    skipping = sleeper.world.clock.skipping

    playing[0] = False
    sleeper.world.loop.tick()

    assert skipping
    assert not sleeper.world.clock.skipping
    assert sleeper.world.clock.speed == 1


def test_getting_up_stops_the_skip() -> None:
    sleeper = Sleeper(2.75)
    sleeper.health.rest(True)
    sleeper.real(1)

    sleeper.health.rest(False)
    sleeper.world.loop.tick()

    assert not sleeper.world.clock.skipping
    assert sleeper.world.clock.speed == 1


def test_collapsing_stops_the_skip() -> None:
    sleeper = Sleeper(2.75, Player(health=0.5))
    sleeper.health.rest(True)
    sleeper.real(1)

    sleeper.health.hurt(1)
    sleeper.world.loop.tick()

    assert not sleeper.world.clock.skipping


def test_the_clock_waits_for_them_to_lie_down() -> None:
    sleeper = Sleeper(2.75)
    sleeper.health.rest(True)
    sleeper.world.loop.tick()

    assert sleeper.health.sleeping()
    assert not sleeper.world.clock.skipping


@pytest.mark.parametrize("hours", [21.0, 23.5, 0.0, 5.9])
def test_night_is_from_the_earliest_bedtime_until_six(hours: float) -> None:
    sleeper = Sleeper(hours)

    assert sleeper.sleep.night()
    assert sleeper.health.rest(True)


@pytest.mark.parametrize("hours", [6.0, 6.5, 14.0, 20.9])
def test_in_the_daytime_a_rest_at_full_health_or_infected_is_ignored(hours: float) -> None:
    well = Sleeper(hours)
    infected = Sleeper(hours, Player(health=0.5, effects=[infection()]))

    assert not well.health.rest(True)
    assert not infected.health.rest(True)


def test_night_starts_at_the_earliest_bedtime_any_resident_can_have() -> None:
    assert NIGHT_STARTS == DEFAULT_BEHAVIOUR.bedtime_range[0] == 21.0


def test_a_daytime_rest_heals_and_ends_at_full_health_without_a_skip() -> None:
    sleeper = Sleeper(14, Player(health=0.5))

    assert sleeper.health.rest(True)
    sleeper.real(5)

    assert not sleeper.health.resting()
    assert sleeper.player.health == 1
    assert not sleeper.world.clock.skipping
    assert sleeper.world.clock.time_of_day < 14.01


def test_waking_in_bed_after_a_collapse_at_night_rests_without_a_skip() -> None:
    sleeper = Sleeper(2.75, Player(health=0.25))

    assert sleeper.health.rest(True, woken=True)
    sleeper.real(1)

    assert not sleeper.health.sleeping()
    assert not sleeper.world.clock.skipping


class Counting:
    """The canned fake LLM, noting the sim time of each call."""

    name = "counting"

    def __init__(self, world: World) -> None:
        from simile.loop.playthrough import Canned

        self.world = world
        self.canned = Canned()
        self.calls: list[datetime] = []

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        self.calls.append(self.world.clock.now)
        return self.canned.stream(request)


@dataclass
class Slept:
    skipping: bool
    """Whether the clock skipped once they'd lain down."""
    real: float
    """Real seconds from the rest until they were up."""
    speed: float
    resting: bool
    health: float
    vitals: tuple[float, float]
    """Hunger and power as they lay down, and once up."""
    after: tuple[float, float]
    started: list[ConversationStarted]
    calls: list[datetime]
    first_up: datetime
    asleep: dict[str, float]
    """Each resident still asleep, by the hour they wake."""


async def sleep_in_the_village(start: datetime, health: float = 0.4, morning: bool = True) -> Slept:
    from simile.app import create_app
    from simile.behaviour.mind import create_behaviour
    from simile.conversation import create_engine
    from simile.loop.player import LoopPlayer
    from simile.memory import MemoryStore
    from simile.persistence import player_of
    from simile.protocol import RestMessage
    from simile.story.begin import begin

    world = World(Clock(start), FakeWallClock())
    app = create_app()
    app.state.world, app.state.headless = world, True
    app.state.memory = MemoryStore(":memory:")
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.conversation = create_engine(app, seed=0)
    await begin(app, rng=random.Random("story/0"))
    started: list[ConversationStarted] = []
    world.bus.subscribe(ConversationStarted, started.append)
    async with app.router.lifespan_context(app):
        counting = Counting(world)
        app.state.llm = LLMClient(counting)
        player = LoopPlayer(app, [])
        player.join(app.state.health.home_bed())
        await player.wait(1)
        me = player_of(app)
        me.health = health
        vitals = (me.hunger, me.power)
        player.send(RestMessage(on=True))
        wall = world.loop.wall.now()
        while world.loop.wall.now() - wall < DEFAULT_HEALTH.lie_down + 0.1:
            await world.loop.run(timedelta(seconds=world.loop.dt()))
        skipping = world.clock.skipping
        while morning and (world.clock.time_of_day < 7 or world.clock.skipping):
            await world.loop.run(timedelta(seconds=world.loop.dt()))
        minds = app.state.behaviour.minds
        return Slept(
            skipping=skipping,
            real=world.loop.wall.now() - wall,
            speed=world.clock.speed,
            resting=app.state.health.resting(),
            health=me.health,
            vitals=vitals,
            after=(me.hunger, me.power),
            started=started,
            calls=counting.calls,
            first_up=DAY + timedelta(hours=min(mind.wake for mind in minds.values())),
            asleep={id: mind.wake for id, mind in minds.items() if mind.goal.activity is SLEEP},
        )


def test_a_headless_rest_at_the_camp_bed_at_a_quarter_to_three_sleeps_until_seven() -> None:
    with pytest.MonkeyPatch.context() as env:
        env.setenv("SIMILE_LLM", "fake")
        env.setenv("SIMILE_NEWS", "0")
        env.setenv("SIMILE_DB", ":memory:")
        slept = asyncio.run(sleep_in_the_village(at(2.75)))

    assert slept.real == pytest.approx(DEFAULT_HEALTH.lie_down + 4.25 * 3600 / SPEED, abs=0.05)
    assert slept.speed == 1
    assert not slept.resting
    assert slept.health == 1
    assert slept.after == slept.vitals
    assert slept.started == []
    assert [call for call in slept.calls if call < slept.first_up] == []
    assert all(wake > 6.9 for wake in slept.asleep.values())


def test_a_headless_rest_at_full_health_at_nine_sharp_skips() -> None:
    with pytest.MonkeyPatch.context() as env:
        env.setenv("SIMILE_LLM", "fake")
        env.setenv("SIMILE_NEWS", "0")
        env.setenv("SIMILE_DB", ":memory:")
        slept = asyncio.run(sleep_in_the_village(at(NIGHT_STARTS), health=1, morning=False))

    assert slept.skipping
    assert slept.resting
    assert slept.speed == SPEED
