from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from simile.ambient.config import AmbientConfig
from simile.behaviour import DEFAULT_CONFIG, Activity, Behaviour, BehaviourConfig, GoalChosen
from simile.cafe.cafe import Cafe
from simile.cafe.config import DEFAULT_CONFIG as CAFE_CONFIG
from simile.cafe.config import CafeConfig
from simile.llm import CallRecord, FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Conversation, CoreValue, Line, MapTile, Npc
from simile.sim import Clock, Event, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import TownMap, load_maps
from simile.world.spots import purpose_of

MAPS = load_maps()
DAY = datetime(2026, 1, 1, tzinfo=UTC)
MORNING = DAY.replace(hour=8)
TEMPLATE = load_npcs()[0]
GROUND = "coffee_shop_floor_0"
TILL = MapTile(map=GROUND, x=3, y=2)
STAND = Point(6, 2, GROUND)
UPSTAIRS = Point(15, 2, GROUND)


def make_npc(id: str, home: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "values": scores,
            "craft": None,
            "workplace": None,
            "shifts": [],
            "pay": None,
        }
    )


BEA = make_npc("bea", "coffee_shop")
ANA = make_npc("ana", "house_1", connection=0.0, pleasure=0.0, peace_of_mind=0.0, ambition=1.0)
BEN = make_npc("ben", "house_2", connection=0.0, pleasure=0.0, peace_of_mind=0.0, ambition=1.0)
CAL = make_npc("cal", "house_3", connection=0.0, pleasure=0.0, peace_of_mind=0.0, ambition=1.0)


def keen(activity: Activity) -> BehaviourConfig:
    """Everyone always picks `activity` when awake."""
    return DEFAULT_CONFIG.model_copy(update={"base": {activity: 10.0}, "temperature": 0.0})


class Engine:
    """B2's engine as the café sees it: nobody's talking and everyone's keen."""

    def talking(self, npc: str) -> bool:
        return False

    def accept_score(self, a: str, b: str) -> float:
        return 1.0

    def as_voiced(self, line: Line) -> Line:
        return line

    def still_playing(self, conversation: Conversation) -> datetime | None:
        return None


def quiet_director(now: datetime) -> SimpleNamespace:
    """The ambient director when it's been quiet long enough to nudge."""
    long_ago = now - timedelta(minutes=10)
    return SimpleNamespace(
        config=AmbientConfig(),
        earshot=SimpleNamespace(heard=set(), live={}),
        heard_at=long_ago,
        nudged_at=long_ago,
    )


class Village:
    """The café with its barista and whoever else, on a fake wall clock."""

    def __init__(
        self,
        npcs: Sequence[Npc] = (BEA,),
        *,
        start: datetime = MORNING,
        behaviour: BehaviourConfig = DEFAULT_CONFIG,
        config: CafeConfig = CAFE_CONFIG,
        replies: Sequence[Any] = (),
        director: Any = None,
        players: Any = None,
        maps: Mapping[str, TownMap] = MAPS,
        purposes: bool = False,
    ) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(maps, self.world.bus)
        if purposes:
            self.world.bus.subscribe(
                GoalChosen, lambda e: self.movement.intend(e.npc, purpose_of(e.activity, e.target))
            )
        self.store = MemoryStore(":memory:")
        self.behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            npcs,
            self.store,
            config=behaviour,
            seed=0,
        )
        self.provider = FakeProvider(list(replies))
        self.calls: list[CallRecord] = []
        self.llm = LLMClient(self.provider, listeners=[self.calls.append])
        self.cafe = Cafe(
            self.world.clock,
            self.world.bus,
            self.behaviour,
            self.store,
            lambda: self.llm,
            engine=lambda: Engine() if director else None,
            players=lambda: players,
            director=lambda: director,
            connected=lambda: director is not None,
            config=config,
            seed=0,
        )
        self.events: list[Event] = []
        self.world.bus.subscribe(Event, self.events.append)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.world.loop.register(self.cafe)
        self.behaviour.start()

    @property
    def now(self) -> datetime:
        return self.world.clock.now

    async def run(self, *, minutes: float = 0, seconds: float = 0) -> None:
        await self.world.loop.run(timedelta(minutes=minutes, seconds=seconds))

    async def run_until(self, done: Any, *, minutes: float = 30) -> None:
        end = self.now + timedelta(minutes=minutes)
        while not done():
            assert self.now < end, "ran out of time"
            await self.run(seconds=1)

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    def at(self, npc: str) -> Point:
        return self.movement.position(npc)

    def player_at_counter(self) -> None:
        self.movement.track(PLAYER_ID, STAND)
