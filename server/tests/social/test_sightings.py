from datetime import UTC, datetime, timedelta
from pathlib import Path

from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Bionic, Body, CoreValue, Id, MemoryKind, Npc
from simile.sim import Clock, EventBus
from simile.social import tolerance
from simile.social.sightings import Sightings
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
START = datetime(2026, 1, 1, 10, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
EYE, LEGS = Bionic.INFRARED_EYE, Bionic.HYDRAULIC_LEGS


def resident(id: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(update={"id": id, "name": f"{id.title()} Test", "values": scores})


ANA = resident("ana", tradition=1.0, security=1.0)
BEN = resident("ben", adventure=1.0, ambition=1.0, open_mindedness=1.0)


class Street:
    """Ana and Ben in the coffee shop, the player beside Ana, everyone awake."""

    def __init__(
        self, store: MemoryStore | None = None, *, body: Body | None = None, player: bool = True
    ) -> None:
        self.clock = Clock(START)
        self.store = store or MemoryStore(":memory:")
        self.movement = Movement(MAPS, EventBus())
        for npc in (ANA, BEN):
            self.movement.place(npc.id, "coffee_shop")
        if player:
            self.player_at(ANA.id, 1)
        self.body = body or Body(legs=LEGS)
        self.asleep: set[Id] = set()
        self.sightings = Sightings(
            self.store,
            self.clock,
            {npc.id: npc for npc in (ANA, BEN)},
            self.movement,
            lambda: self.body,
            lambda npc: npc not in self.asleep,
        )

    def player_at(self, npc: Id, tiles: float, map: str | None = None) -> None:
        here = self.movement.position(npc)
        self.movement.track(PLAYER_ID, Point(here.x + tiles, here.y, map or here.map))

    def look(self) -> None:
        self.sightings.tick(self.sightings.config.look_every)

    def sightings_of(self, npc: Id) -> list[str]:
        memories = self.store.recall(npc, self.clock.now, about=PLAYER_ID, k=100)
        return [m.content for m in memories if m.kind is MemoryKind.OBSERVATION]


def test_a_resident_in_sight_sees_each_bionic_once() -> None:
    street = Street()

    street.look()
    street.look()

    assert len(street.sightings_of("ana")) == 1
    assert set(street.sightings.seen("ana")) == {LEGS}
    rel = street.store.relationship("ana", PLAYER_ID)
    assert rel is not None and rel.like < 0.5
    assert street.store.shared_history("ana", PLAYER_ID, START).events == []


def test_a_new_bionic_is_seen_on_its_own() -> None:
    street = Street()
    street.look()

    street.body = Body(legs=LEGS, left_eye=EYE)
    street.clock.now += timedelta(hours=1)
    street.look()

    assert len(street.sightings_of("ana")) == 2
    assert street.sightings.seen("ana") == {LEGS: START, EYE: START + timedelta(hours=1)}


def test_nobody_sees_the_player_asleep_out_of_sight_or_through_a_wall() -> None:
    street = Street()
    street.asleep.add("ana")
    street.look()
    assert not street.sightings_of("ana")

    street.asleep.clear()
    street.player_at("ana", street.sightings.config.sight + 1)
    street.look()
    assert not street.sightings_of("ana")

    street.player_at("ana", 1, map="high_street")
    street.look()
    assert not street.sightings_of("ana")


def test_a_whole_player_or_one_not_in_the_world_changes_nothing() -> None:
    street = Street(body=Body())
    street.look()
    assert street.store.relationship("ana", PLAYER_ID) is None

    away = Street(player=False)
    away.look()
    assert away.store.relationship("ana", PLAYER_ID) is None


def test_what_they_have_seen_outlasts_a_restart(tmp_path: Path) -> None:
    with MemoryStore(tmp_path / "simile.db") as store:
        Street(store).look()
    with MemoryStore(tmp_path / "simile.db") as store:
        street = Street(store)
        street.clock.now += timedelta(days=1)
        street.look()

        assert len(street.sightings_of("ana")) == 1
        assert street.sightings.seen("ana") == {LEGS: START}


def test_unease_is_what_an_intolerant_resident_has_seen_or_sees_now() -> None:
    street = Street(body=Body(legs=LEGS, left_eye=EYE))
    street.player_at("ana", street.sightings.config.sight + 1)
    assert street.sightings.unease(ANA) == 0

    street.player_at("ana", 1)
    assert street.sightings.unease(ANA) == -tolerance(ANA.values) == 1
    assert street.sightings.seen("ana") == {}

    street.look()
    street.player_at("ana", street.sightings.config.sight + 1)
    assert street.sightings.unease(ANA) == 1
    assert street.sightings.unease(BEN) == 0
    street.body = Body()
    assert street.sightings.unease(ANA) == 0


def test_what_they_see_calls_a_bionic_new_for_an_hour() -> None:
    street = Street()
    assert "new since" in (street.sightings.looks("ana") or "")

    street.look()
    street.clock.now += timedelta(minutes=30)
    assert "new since" in (street.sightings.looks("ana") or "")
    street.clock.now += timedelta(minutes=31)
    looks = street.sightings.looks("ana") or ""

    assert looks.startswith("Visitor has hydraulic legs") and "new since" not in looks
    assert street.sightings.looks("ben") == (
        "Visitor has hydraulic legs where their own legs were. Bionics fascinate you."
    )
    street.body = Body()
    assert street.sightings.looks("ana") is None
