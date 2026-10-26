from datetime import UTC, datetime

import pytest

from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, CoreValue, Id, MapTile, MemoryKind, Npc, Player
from simile.sim import Clock, EventBus
from simile.social import meet
from simile.street.finds import STASHES
from simile.theft import DEFAULT_CONFIG, Theft, minds
from simile.world import Movement
from simile.world.map import load_maps

MAPS = load_maps()
START = datetime(2026, 1, 1, 22, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
KITCHEN, BED = STASHES["house_2_kitchen"], STASHES["house_2_bed"]


def resident(id: str, home: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(
        update={"id": id, "name": f"{id.title()} Test", "values": scores, "home": home}
    )


ANA = resident("ana", "house_2", security=1.0, tradition=1.0)
BEN = resident("ben", "house_5", security=0.0, tradition=0.0, compassion=1.0)


class House:
    """Ana at home in her living room, and Ben visiting, both awake."""

    def __init__(self, *, searched: list[Id] | None = None) -> None:
        self.clock = Clock(START)
        self.store = MemoryStore(":memory:")
        self.movement = Movement(MAPS, EventBus())
        for npc in (ANA, BEN):
            self.movement.place(npc.id, MapTile(map="house_2_floor_0", x=3, y=2))
        self.player = Player(searched=searched or [])
        self.asleep: set[Id] = set()
        self.theft = Theft(
            self.player,
            self.movement,
            self.store,
            self.clock,
            {npc.id: npc for npc in (ANA, BEN)},
            lambda npc: npc not in self.asleep,
        )

    def search(self, thing: Id) -> None:
        self.player.searched = [*self.player.searched, thing]
        self.theft.tick(0.1)

    def memories(self, npc: Id) -> list[str]:
        memories = self.store.recall(npc, self.clock.now, about=PLAYER_ID, k=100)
        return [m.content for m in memories if m.kind is MemoryKind.OBSERVATION]

    def trust(self, npc: Npc) -> float:
        rel = self.store.relationship(npc.id, PLAYER_ID)
        return (rel or meet(npc, PLAYER_ID)).trust


def test_a_search_is_seen_once_and_not_again_after_a_restart() -> None:
    house = House()

    house.search(KITCHEN.id)
    house.theft.tick(0.1)
    again = House(searched=[KITCHEN.id])
    again.theft.tick(0.1)
    again.search("maker_space_spares")

    assert len(house.memories("ana")) == 1
    assert again.memories("ana") == []


def test_the_resident_whose_house_it_is_minds_by_their_values_and_remembers() -> None:
    house = House()
    before = {npc.id: house.trust(npc) for npc in (ANA, BEN)}

    house.search(KITCHEN.id)

    drop = {npc.id: before[npc.id] - house.trust(npc) for npc in (ANA, BEN)}
    assert drop["ana"] > drop["ben"] > 0
    assert house.memories("ana") == ["I saw Visitor going through the tea tin in my house."]
    assert house.memories("ben") == ["I saw Visitor going through the tea tin in Ana Test's house."]
    [ben] = house.store.recall("ben", house.clock.now, about="ana", k=10)
    assert ben.topics == ["theft"]


def test_searching_with_nobody_in_the_room_costs_nothing() -> None:
    house = House()

    house.search(BED.id)

    assert house.memories("ana") == house.memories("ben") == []
    assert house.store.relationship("ana", PLAYER_ID) is None


def test_a_resident_asleep_in_the_room_sees_nothing() -> None:
    house = House()
    house.asleep = {"ana", "ben"}

    house.search(KITCHEN.id)

    assert house.memories("ana") == []
    assert house.store.relationship("ana", PLAYER_ID) is None


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, 0.5),
        ({"security": 1.0, "tradition": 1.0}, 1.0),
        ({"security": 0.0, "tradition": 0.0}, DEFAULT_CONFIG.least),
        ({"security": 0.75}, 0.75),
    ],
)
def test_security_and_tradition_mind_most(values: dict[str, float], expected: float) -> None:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}

    assert minds(scores) == pytest.approx(expected)
