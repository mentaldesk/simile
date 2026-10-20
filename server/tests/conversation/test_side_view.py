import itertools

import pytest

from simile.behaviour import Behaviour
from simile.conversation import ConversationEngine, Facing
from simile.conversation.engine import facing
from simile.llm import FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.schema import MapTile
from simile.sim import Clock, Event, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import STREET_DIR, load_maps

from .test_engine import ANA, BEN, CHAT, START, friends

pytestmark = pytest.mark.anyio

STREETS = load_maps(STREET_DIR)


def test_in_side_view_people_face_left_or_right_or_else_the_camera() -> None:
    here = Point(5, 2, "coffee_shop_floor_1")

    assert facing(here, Point(9, 1, here.map), side_view=True) == "right"
    assert facing(here, Point(2, 8, here.map), side_view=True) == "left"
    assert facing(here, Point(5, 0, here.map), side_view=True) == "down"
    assert facing(here, Point(9, 1, here.map)) == "right"
    assert facing(here, Point(5, 9, here.map)) == "down"
    assert facing(here, Point(5, 0, here.map)) == "up"


async def test_a_conversation_on_a_street_turns_them_to_face_each_other_across_it() -> None:
    world = World(Clock(START), FakeWallClock())
    store = MemoryStore(":memory:")
    store.add(*friends(ANA, BEN))
    movement = Movement(STREETS, world.bus)
    movement.place("ana", MapTile(map="high_street", x=56, y=15))
    movement.place("ben", MapTile(map="high_street", x=54, y=15))
    behaviour = Behaviour(world.clock, world.bus, movement, (ANA, BEN), store, seed=0)
    behaviour.start()
    llm = LLMClient(FakeProvider(itertools.repeat(CHAT, 10)))
    engine = ConversationEngine(world.clock, world.bus, behaviour, store, lambda: llm, seed=0)
    events: list[Event] = []
    world.bus.subscribe(Event, events.append)

    assert engine.request("ana", "ben")

    turned = {event.entity: event.direction for event in events if isinstance(event, Facing)}
    assert turned == {"ana": "left", "ben": "right"}
