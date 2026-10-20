from datetime import UTC, datetime, timedelta

import pytest

from simile.ambient import AmbientConfig, Director, Nudged
from simile.behaviour import Activity, Behaviour, Goal
from simile.conversation import DEFAULT_CONFIG, ConversationEngine
from simile.llm import FakeProvider, LLMClient
from simile.llm.fake import scene
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, CoreValue, MapTile, Npc
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    Event,
    FakeWallClock,
    World,
)
from simile.social import meet
from simile.world import Movement, Point
from simile.world.map import STREET_DIR, load_maps

STREETS = load_maps(STREET_DIR)
START = datetime(2026, 1, 1, 11, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
ALWAYS = DEFAULT_CONFIG.model_copy(update={"accept_temperature": 0})
LANE = "lychee_lane"
LOOKOUT = 12
"""The row of the park's lookout, up a ladder above Lychee Lane's row 15."""

type Place = tuple[str, float, float]


def resident(id: str, home: str) -> Npc:
    return TEMPLATE.model_copy(
        update={
            "id": id,
            "name": f"{id.title()} Test",
            "home": home,
            "values": {value: 0.5 for value in CoreValue},
            "workplace": None,
            "shifts": [],
            "pay": None,
        }
    )


ANA, BEN = resident("ana", "house_1"), resident("ben", "house_2")


class Street:
    """Ana and Ben, who are friends, out on the side-view maps with the player, a conversation
    engine and the director, on a fake wall clock. Nobody decides until a test runs the loop."""

    def __init__(self, ana: Place, ben: Place, player: Place) -> None:
        self.world = World(Clock(START), FakeWallClock())
        store = MemoryStore(":memory:")
        for owner, other in ((ANA, BEN), (BEN, ANA)):
            store.add(meet(owner, other.id).model_copy(update={"like": 0.9, "trust": 0.9}))
        self.movement = Movement(STREETS, self.world.bus)
        for npc, (map, x, y) in (("ana", ana), ("ben", ben)):
            self.movement.place(npc, MapTile(map=map, x=int(x), y=int(y)))
        self.move_player(*player)
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, [ANA, BEN], store, seed=0
        )
        self.behaviour.start()
        for npc, mind in self.behaviour.minds.items():
            needs = {need: 0.5 for need in mind.needs}
            later = START + timedelta(hours=1)
            self.behaviour.restore(npc, Goal(Activity.SQUARE, "square"), needs, START, later, {})
        llm = LLMClient(
            FakeProvider(default=lambda request: scene(request, ["Lovely morning."]) or "Morning.")
        )
        self.engine = ConversationEngine(
            self.world.clock, self.world.bus, self.behaviour, store, lambda: llm, config=ALWAYS
        )
        self.behaviour.hooks.set(request_conversation=self.engine.request)
        self.director = Director(
            self.behaviour, self.engine, config=AmbientConfig(quiet=60, retry=30)
        )
        self.world.bus.subscribe(ConversationStarted, self.director.earshot.on_started)
        self.world.bus.subscribe(ConversationEnded, self.director.earshot.on_ended)
        self.events: list[Event] = []
        self.world.bus.subscribe(Event, self.events.append)

    def move_player(self, map: str, x: float, y: float) -> None:
        self.movement.track(PLAYER_ID, Point(x, y, map))

    def hears(self, map: str, x: float, y: float) -> bool:
        self.move_player(map, x, y)
        return bool(self.director.earshot.update())

    async def run(self, minutes: float) -> None:
        for system in (self.behaviour, self.movement, self.engine, self.director):
            self.world.loop.register(system)
        await self.world.loop.run(timedelta(minutes=minutes))

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]


def test_hears_a_conversation_up_the_lookout_by_how_far_along_the_street_it_is() -> None:
    street = Street((LANE, 46, LOOKOUT), (LANE, 48, LOOKOUT), (LANE, 40, 15))
    street.engine.start("ana", "ben")

    places = [40, 41, 46 - AmbientConfig().out_of_earshot, 39.4]
    assert [street.hears(LANE, x, 15) for x in places] == [False, True, True, False]


def test_hears_nothing_on_another_floor_or_from_the_street_outside() -> None:
    upstairs = "coffee_shop_floor_1"
    street = Street((upstairs, 5, 2), (upstairs, 7, 2), ("coffee_shop_floor_0", 5, 2))
    street.engine.start("ana", "ben")

    assert not street.hears("coffee_shop_floor_0", 5, 2)
    assert not street.hears("high_street", 30, 15)
    assert street.hears(upstairs, 3, 2)


@pytest.mark.parametrize(("x", "pair"), [(41, ("ben", "ana")), (40, None)])
def test_the_target_is_in_earshot_along_the_street(x: float, pair: tuple[str, str] | None) -> None:
    street = Street((LANE, 46, LOOKOUT), (LANE, 48, LOOKOUT), (LANE, x, 15))

    assert street.director.choose() == pair


def test_only_residents_on_the_players_floor_are_nudged() -> None:
    downstairs = "coffee_shop_floor_0"
    street = Street((downstairs, 5, 2), (downstairs, 7, 2), ("coffee_shop_floor_1", 5, 2))
    assert street.director.choose() is None

    street.move_player(downstairs, 6, 2)
    assert set(street.director.choose() or ()) == {"ana", "ben"}


@pytest.mark.anyio
async def test_a_nudged_resident_walks_along_the_square_to_talk() -> None:
    square = "high_street"
    street = Street((square, 52, 15), (square, 62, 15), (square, 54, 15))

    await street.run(minutes=1.5)

    assert [(e.seeker, e.target) for e in street.of(Nudged)] == [("ben", "ana")]
    started = street.of(ConversationStarted)
    assert [e.conversation.participants for e in started] == [["ben", "ana"]]
    assert street.director.earshot.heard
