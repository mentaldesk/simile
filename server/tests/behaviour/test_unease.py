import asyncio
from collections import Counter
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

from starlette.applications import Starlette

from simile.behaviour import DEFAULT_CONFIG, Activity, Goal, scores
from simile.behaviour.mind import create_behaviour, no_conversations
from simile.memory import MemoryStore
from simile.schema import PLAYER_ID, Bionic, Body, MapTile, MemoryKind, Npc
from simile.sim import Clock, FakeWallClock, World
from simile.voicing.distance import apart

from .test_mind import ANA, BEN, Village, at

A = Activity
CAFE = MapTile(map="coffee_shop_floor_0", x=12, y=2)
WHOLE = Body()
BIONIC = Body(legs=Bionic.BIONIC_LEGS, vertebra=Bionic.DATAJACK, left_eye=Bionic.INFRARED_EYE)


def uneasy(level: float, who: str = "ana"):  # type: ignore[no-untyped-def]
    return lambda npc: level if npc.id == who else 0.0


def options(village: Village, npc: str = "ana") -> dict[Goal, float]:
    behaviour = village.behaviour
    return scores(behaviour._situation(behaviour.minds[npc]), behaviour.places, behaviour.config)


def at_the_cafe(*npcs: Npc) -> Village:
    """Everyone heading for the coffee shop, and the player in it."""
    village = Village(list(npcs), start=at(11), placed={PLAYER_ID: CAFE})
    for npc in npcs:
        village.behaviour.minds[npc.id].goal = Goal(A.COFFEE_SHOP, "coffee_shop")
    return village


def test_unease_takes_from_the_players_affinity_alone() -> None:
    village = at_the_cafe(ANA, BEN)
    before = {o.id: o for o in village.behaviour._situation(village.behaviour.minds["ana"]).others}

    village.behaviour.hooks.set(unease=uneasy(0.5))
    after = {o.id: o for o in village.behaviour._situation(village.behaviour.minds["ana"]).others}

    assert after["ben"] == before["ben"]
    lost = before[PLAYER_ID].affinity - after[PLAYER_ID].affinity
    assert lost == DEFAULT_CONFIG.unease_weight * 0.5
    assert after[PLAYER_ID].shunned and not before[PLAYER_ID].shunned


def test_unease_is_zero_without_the_hook_and_clamped_with_it() -> None:
    village = at_the_cafe(ANA)
    assert village.behaviour.unease("ana") == 0

    village.behaviour.hooks.set(unease=uneasy(3.0))
    assert village.behaviour.unease("ana") == 1

    def broken(npc: Npc) -> float:
        raise RuntimeError

    village.behaviour.hooks.set(unease=broken)
    assert village.behaviour.unease("ana") == 0


def test_an_uneasy_resident_keeps_away_from_the_player_and_where_they_are() -> None:
    village = at_the_cafe(ANA, BEN)
    before = options(village)

    village.behaviour.hooks.set(unease=uneasy(1.0))
    after = options(village)

    cafe, seek_player, seek_ben = (
        Goal(A.COFFEE_SHOP, "coffee_shop"),
        Goal(A.SEEK, PLAYER_ID),
        Goal(A.SEEK, "ben"),
    )
    assert after[cafe] < before[cafe] - 0.9
    assert after[seek_player] < before[seek_player]
    assert after[seek_ben] < before[seek_ben] - 0.9
    assert after[Goal(A.SQUARE, "square")] == before[Goal(A.SQUARE, "square")]


def test_unease_changes_nobody_else() -> None:
    village = at_the_cafe(ANA, BEN)
    before = options(village, "ben")

    village.behaviour.hooks.set(unease=uneasy(1.0))

    assert options(village, "ben") == before


async def day(body: Body) -> tuple[Counter[str], set[str]]:
    """Minutes each resident spends near the player in the coffee shop, and who saw them."""
    from simile.behaviour.lifespan import lifespan as behaviour
    from simile.economy.lifespan import lifespan as economy
    from simile.memory.lifespan import lifespan as memory
    from simile.persistence import player_of
    from simile.social.lifespan import lifespan as social
    from simile.world.lifespan import lifespan as world_lifespan

    app = Starlette()
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    app.state.world, app.state.headless = world, True
    app.state.memory = store = MemoryStore(":memory:")
    app.state.behaviour = village = create_behaviour(app, seed=0)
    player_of(app).body = body
    near: Counter[str] = Counter()

    class Count:
        elapsed = 0.0

        def tick(self, dt: float) -> None:
            self.elapsed += dt
            if self.elapsed >= 60:
                self.elapsed = 0.0
                entities = village.movement.entities()
                near.update(
                    npc for npc in village.npcs if apart(entities[npc], entities[PLAYER_ID]) <= 6
                )

    async with AsyncExitStack() as stack:
        for hook in (behaviour, economy, memory, world_lifespan, social):
            await stack.enter_async_context(hook(app))
        village.movement.place(PLAYER_ID, CAFE)
        village.hooks.set(
            request_conversation=lambda a, b: False,
            news_interest=lambda npc: 0.6,
            conversations=no_conversations,
        )
        world.loop.register(Count())
        await world.loop.run(timedelta(hours=6))
        saw = {
            npc
            for npc in village.npcs
            if store.recall(npc, world.clock.now, about=PLAYER_ID, kind=MemoryKind.OBSERVATION)
        }
    return near, saw


def test_a_bionic_player_drives_the_intolerant_away_and_draws_the_curious() -> None:
    whole, nobody = asyncio.run(day(WHOLE))
    bionic, saw = asyncio.run(day(BIONIC))

    against, curious = ("tobias", "raymond"), ("kofi", "ingrid")
    assert not nobody and set(against) <= saw
    assert sum(bionic[npc] for npc in against) < sum(whole[npc] for npc in against) / 4
    assert sum(bionic[npc] for npc in curious) >= sum(whole[npc] for npc in curious) * 0.75
    assert bionic["mirela"] > 0.9 * whole["mirela"]
