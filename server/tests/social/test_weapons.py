from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.conversation import conversations_of
from simile.conversation.player import DEFAULT_PLAYER_CONFIG
from simile.conversation.prompt import BLUNT, CUES, POLITE, Cue
from simile.memory import MemoryStore, memory_of
from simile.npc import load_npcs
from simile.persistence import player_of
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Bionic,
    Body,
    CoreValue,
    Item,
    ItemKind,
    Material,
    Npc,
    Stash,
    Traits,
    lamp,
)
from simile.sim import Clock, World
from simile.social import apply_events, meet, relationship, tolerance
from simile.social.bionics import level
from simile.social.config import DEFAULT_BIONICS
from simile.social.relationship import as_of
from simile.social.sightings import Sightings, sightings_of
from simile.social.weapons import FEELS, carrying, dented, noticed, wariness, wary
from simile.world.movement import Point

from ..conversation.test_player import BEN, Village, make_npc
from .test_sightings import ANA, Street
from .test_sightings import BEN as BOLD

MakePackage = Callable[[dict[str, str]], str]

NOW = datetime(2026, 1, 1, 10, tzinfo=UTC)
PISTOL = Item(
    id="plastic_pistol",
    kind=ItemKind.WEAPON,
    name="Plastic pistol",
    weight=0.5,
    material=Material.PLASTIC,
    rounds=4,
    capacity=6,
    condition=1.0,
)
ROUNDS = Item(
    id="plastic_rounds",
    kind=ItemKind.ROUNDS,
    name="Plastic rounds",
    weight=0.01,
    amount=6,
    material=Material.PLASTIC,
)
WARY = make_npc("ana", "house_1", tradition=1.0, security=1.0)
UNEASY = make_npc("ana", "house_1", tradition=0.7, security=0.7, connection=0.0)
CALM = make_npc("ana", "house_1", tradition=0.5, security=0.5, connection=1.0)
REFUSE = CUES[Cue.REFUSE].format(other="Visitor")
OPENING = "You're with Visitor (a newcomer to the village)."


def scores(**values: float) -> dict[CoreValue, float]:
    return {value: values.get(value.value, 0.5) for value in CoreValue}


def test_security_and_tradition_distrust_it_and_nothing_else_moves_them() -> None:
    assert wariness(scores()) == 0
    assert wariness(scores(security=0.9)) == pytest.approx(0.4)
    assert wariness(scores(tradition=0.9)) == pytest.approx(0.4)
    assert wariness(scores(tradition=0.9, security=0.9)) == pytest.approx(0.8)
    assert wariness(scores(tradition=1.0, security=1.0)) == 1
    others = {value.value: 1.0 for value in CoreValue} | {"tradition": 0.5, "security": 0.5}
    assert wariness(scores(**others)) == 0


def test_a_low_score_excuses_nothing_and_nobody_warms_to_it() -> None:
    assert wariness(scores(security=0.9, tradition=0.0)) == pytest.approx(0.4)
    assert wariness(scores(security=0.0, tradition=0.0)) == 0


def test_someone_taken_with_bionics_can_still_distrust_a_gun() -> None:
    values = scores(security=1.0, tradition=0.0, adventure=1.0, ambition=1.0, open_mindedness=1.0)

    assert level(tolerance(values)) == 2
    assert level(-wariness(values)) == -2


def test_who_in_todays_village_distrusts_it() -> None:
    by_level: dict[int, set[str]] = {-2: set(), -1: set(), 0: set()}
    for npc in load_npcs():
        by_level[level(-wariness(npc.values))].add(npc.id)

    assert by_level[-2] == {"tobias", "raymond"}
    assert by_level[-1] == {"mirela", "henrietta", "lachlan"}
    assert by_level[0] >= {"ingrid", "kofi", "desmond", "odalys"}


def test_what_they_see_says_how_they_take_it() -> None:
    assert carrying("Visitor", WARY) == f"Visitor is carrying a pistol. {FEELS[-2]}"
    assert carrying("Visitor", UNEASY) == f"Visitor is carrying a pistol. {FEELS[-1]}"
    assert carrying("Visitor", CALM) == f"Visitor is carrying a pistol. {FEELS[0]}"


def test_the_event_is_on_trust_alone_and_as_bad_as_they_are_wary() -> None:
    event = noticed(WARY, NOW)

    assert event.aspects == [Aspect.TRUST]
    assert (event.actor, event.target, event.valence) == (PLAYER_ID, "ana", -1)
    assert wary(WARY) and wary(UNEASY) and not wary(CALM)


def test_how_bad_the_event_is_varies_by_resident_at_the_same_magnitude() -> None:
    event = noticed(UNEASY, NOW)

    assert event.valence == pytest.approx(-0.4)
    assert event.magnitude == DEFAULT_BIONICS.sighting == 0.3
    assert noticed(WARY, NOW).magnitude == 0.3


def test_one_dent_moves_trust_by_the_event_at_its_full_magnitude() -> None:
    rel = meet(UNEASY, PLAYER_ID)
    weak = noticed(UNEASY, NOW).model_copy(update={"magnitude": 0.001})

    assert dented(rel, UNEASY, NOW).trust == apply_events(rel, [noticed(UNEASY, NOW)], NOW).trust
    assert dented(rel, UNEASY, NOW).trust < apply_events(rel, [weak], NOW).trust


def test_it_leaves_familiarity_as_it_was() -> None:
    rel = meet(UNEASY, PLAYER_ID)
    known = rel.model_copy(update={"familiarity": 0.4, "last_interaction": NOW})

    assert dented(rel, UNEASY, NOW).familiarity == 0
    assert dented(known, UNEASY, NOW).familiarity == 0.4


def test_it_never_takes_trust_past_one_dent_below_the_baseline() -> None:
    rel = meet(UNEASY, PLAYER_ID)
    floor = dented(rel, UNEASY, NOW).trust
    assert floor < rel.baseline.trust

    assert dented(dented(rel, UNEASY, NOW), UNEASY, NOW).trust == floor
    almost = rel.model_copy(update={"trust": floor + 0.001, "familiarity": 0.4})
    assert dented(almost, UNEASY, NOW).trust == floor
    below = rel.model_copy(update={"trust": floor - 0.1})
    assert dented(below, UNEASY, NOW).trust == floor - 0.1


@pytest.mark.parametrize("first_impressions", [0.0, 1.0])
def test_the_floor_is_the_same_however_well_they_know_the_player(
    monkeypatch: pytest.MonkeyPatch, first_impressions: float
) -> None:
    traits = Traits(first_impressions=first_impressions)
    monkeypatch.setattr(relationship, "traits_of", lambda npc: traits)
    stranger = meet(UNEASY, PLAYER_ID)
    known = stranger.model_copy(update={"familiarity": 0.4})

    for _ in range(30):
        known = dented(known, UNEASY, NOW)

    assert known.trust == dented(stranger, UNEASY, NOW).trust


def test_it_dents_trust_built_up_above_the_baseline_down_to_the_floor_at_most() -> None:
    rel = meet(UNEASY, PLAYER_ID)
    friend = rel.model_copy(update={"trust": 0.9, "familiarity": 0.6})
    floor = dented(rel, UNEASY, NOW).trust

    trust = friend.trust
    for _ in range(100):
        friend = dented(friend, UNEASY, NOW)
        assert floor <= friend.trust <= trust
        trust = friend.trust
    assert trust == pytest.approx(floor)


@pytest.mark.parametrize(
    ("id", "settled"),
    [
        ("tobias", 0.30),
        ("raymond", 0.38),
        ("mirela", 0.43),
        ("henrietta", 0.33),
        ("lachlan", 0.53),
    ],
)
def test_where_trust_settles_for_the_wary_of_todays_village(id: str, settled: float) -> None:
    npc = next(npc for npc in load_npcs() if npc.id == id)
    rel = meet(npc, PLAYER_ID)

    for day in range(30):
        rel = dented(rel, npc, NOW + timedelta(days=day))

    assert rel.trust == pytest.approx(settled, abs=0.005)


@pytest.mark.parametrize(
    ("id", "uneasy"),
    [
        ("tobias", 0.84),
        ("raymond", 0.46),
        ("mirela", 0.2),
        ("henrietta", 0.16),
        ("lachlan", 0.02),
        ("kofi", 0.0),
    ],
)
def test_how_uneasy_it_makes_todays_village(id: str, uneasy: float) -> None:
    cast = next(npc for npc in load_npcs() if npc.id == id)
    npc = cast.model_copy(update={"id": ANA.id})
    street = armed_street()
    street.sightings.npcs = {npc.id: npc}

    assert street.sightings.unease(npc) == pytest.approx(uneasy, abs=0.005)


def armed_street(*items: Item, body: Body | None = None) -> Street:
    street = Street(body=body or Body())
    street.sightings.carried = lambda: items or (PISTOL,)
    return street


def test_the_wary_trust_them_less_and_the_rest_feel_nothing() -> None:
    street = armed_street()
    before = meet(ANA, PLAYER_ID)

    street.look()

    after = street.store.relationship("ana", PLAYER_ID)
    assert after is not None
    assert after.trust < before.trust
    assert (after.like, after.respect) == (before.like, before.respect)
    assert street.store.relationship("ben", PLAYER_ID) is None


def test_it_leaves_no_memory_or_history_to_outlast_it() -> None:
    street = armed_street()

    street.look()

    assert street.store.recall("ana", NOW, about=PLAYER_ID, k=100) == []
    assert street.store.shared_history("ana", PLAYER_ID, NOW).events == []


def test_seeing_it_again_at_the_floor_changes_nothing() -> None:
    carried: list[Sequence[Item]] = [(PISTOL,)]
    street = Street(body=Body())
    street.sightings.carried = lambda: carried[0]

    street.look()
    first = street.store.relationship("ana", PLAYER_ID)
    street.look()
    assert street.store.relationship("ana", PLAYER_ID) == first

    carried[0] = ()
    street.look()
    assert street.store.relationship("ana", PLAYER_ID) == first

    carried[0] = (PISTOL,)
    street.look()
    again = street.store.relationship("ana", PLAYER_ID)
    assert again is not None and first is not None
    assert again.trust == first.trust and again.familiarity == 0


def test_repeated_outings_stop_at_the_floor_and_familiarity_never_grows() -> None:
    carried: list[Sequence[Item]] = [(PISTOL,)]
    street = Street(body=Body())
    street.sightings.carried = lambda: carried[0]
    street.look()
    first = street.store.relationship("ana", PLAYER_ID)
    assert first is not None

    for _ in range(60):
        carried[0] = ()
        street.look()
        carried[0] = (PISTOL,)
        street.look()

    after = street.store.relationship("ana", PLAYER_ID)
    assert after is not None
    assert after.trust == first.trust and after.familiarity == 0


def test_trust_recovers_and_a_later_outing_dents_it_only_back_to_the_floor() -> None:
    carried: list[Sequence[Item]] = [(PISTOL,)]
    street = Street(body=Body())
    street.sightings.carried = lambda: carried[0]
    street.look()
    first = street.store.relationship("ana", PLAYER_ID)
    assert first is not None

    carried[0] = ()
    street.look()
    street.clock.now += timedelta(days=30)
    carried[0] = (PISTOL,)
    assert as_of(first, street.clock.now).trust > first.trust
    street.look()

    later = street.store.relationship("ana", PLAYER_ID)
    assert later is not None and later.trust == pytest.approx(first.trust)
    assert as_of(later, street.clock.now).trust == pytest.approx(first.trust)


def test_a_dent_starts_from_what_trust_has_recovered_to() -> None:
    street = Street(body=Body())
    street.sightings.carried = lambda: (PISTOL,)
    trusting = meet(ANA, PLAYER_ID).model_copy(update={"trust": 0.95, "last_interaction": NOW})
    street.store.add(trusting)
    street.clock.now += timedelta(days=120)
    recovered = as_of(trusting, street.clock.now).trust

    street.look()

    after = street.store.relationship("ana", PLAYER_ID)
    assert after is not None and after.trust < recovered and after.trust < 0.6


def test_a_restart_while_armed_adds_no_dent(tmp_path: Path) -> None:
    for days in range(6):
        with MemoryStore(tmp_path / "simile.db") as store:
            street = Street(store, body=Body())
            street.sightings.carried = lambda: (PISTOL,)
            street.clock.now += timedelta(hours=days)
            street.look()
            rel = store.relationship("ana", PLAYER_ID)
            assert rel is not None
            if days == 0:
                floor = rel.trust
            assert rel.trust == pytest.approx(floor)
            assert rel.familiarity == 0


def test_nobody_notices_it_asleep_or_out_of_sight() -> None:
    street = armed_street()
    street.asleep.add("ana")
    street.look()
    assert street.store.relationship("ana", PLAYER_ID) is None

    street.asleep.clear()
    street.player_at("ana", street.sightings.config.sight + 1)
    street.look()
    assert street.store.relationship("ana", PLAYER_ID) is None


def test_only_what_they_carry_counts() -> None:
    carried: list[Sequence[Item]] = [(lamp(), ROUNDS)]
    street = Street(body=Body())
    street.sightings.carried = lambda: carried[0]

    street.look()

    assert street.sightings.looks("ana") is None
    assert street.sightings.unease(ANA) == 0
    assert street.store.relationship("ana", PLAYER_ID) is None

    carried[0] = (lamp(), PISTOL)
    assert "carrying a pistol" in (street.sightings.looks("ana") or "")


def test_an_empty_worn_out_pistol_still_shows() -> None:
    spent = PISTOL.model_copy(update={"rounds": 0, "condition": 0.0})
    street = armed_street(spent)

    assert "carrying a pistol" in (street.sightings.looks("ben") or "")


def test_unease_follows_the_pistol() -> None:
    carried: list[Sequence[Item]] = [(PISTOL,)]
    street = Street(body=Body())
    street.sightings.carried = lambda: carried[0]
    street.player_at("ana", street.sightings.config.sight + 1)
    assert street.sightings.unease(ANA) == 0

    street.player_at("ana", 1)
    assert street.sightings.unease(ANA) == 1

    street.look()
    street.player_at("ana", street.sightings.config.sight + 1)
    assert street.sightings.unease(ANA) == 1
    assert street.sightings.unease(BOLD) == 0

    street.player_at("ana", 1)
    carried[0] = ()
    assert street.sightings.unease(ANA) == 0


def test_a_new_outing_causes_no_unease_until_they_see_it_again() -> None:
    carried: list[Sequence[Item]] = [(PISTOL,)]
    street = Street(body=Body())
    street.sightings.carried = lambda: carried[0]
    street.look()

    carried[0] = ()
    street.look()
    carried[0] = (PISTOL,)
    street.player_at("ana", street.sightings.config.sight + 1)

    assert street.sightings.unease(ANA) == 0


def test_unease_adds_to_what_the_bionics_cause_up_to_one() -> None:
    npc = make_npc("ana", "house_1", tradition=0.8, security=0.5, adventure=0.3)
    street = Street(body=Body(legs=Bionic.BIONIC_LEGS))
    street.sightings.npcs = {npc.id: npc}
    alone = street.sightings.unease(npc)

    street.sightings.carried = lambda: (PISTOL,)
    both = street.sightings.unease(npc)

    assert 0 < alone < both

    full = Street(body=Body(left_eye=Bionic.INFRARED_EYE))
    full.sightings.carried = lambda: (PISTOL,)
    assert full.sightings.unease(ANA) == 1


def test_it_follows_any_bionics_in_what_they_see() -> None:
    street = armed_street(body=Body(legs=Bionic.BIONIC_LEGS))
    street.look()
    street.clock.now += timedelta(hours=2)

    assert street.sightings.looks("ben") == (
        "Visitor has bionic legs where their own legs were. Bionics fascinate you. "
        f"Visitor is carrying a pistol. {FEELS[0]}"
    )


def watched(
    village: Village, carried: Callable[[], Sequence[Item]], npcs: tuple[Npc, ...]
) -> Sightings:
    """Sightings wired into the village as the server's lifespans wire it, for a whole player."""
    sightings = Sightings(
        village.store,
        village.clock,
        {npc.id: npc for npc in npcs},
        village.movement,
        Body,
        lambda npc: True,
        carried=carried,
    )
    village.engine.looks = sightings.looks
    village.behaviour.hooks.set(unease=sightings.unease)
    village.world.loop.register(sightings)
    return sightings


@pytest.mark.anyio
async def test_a_residents_prompt_mentions_it_while_they_carry_it() -> None:
    village = Village(npcs=(BEN,))
    watched(village, lambda: (lamp(), PISTOL), (BEN,))

    village.players.say("Hello!", "ben")
    await village.run()

    first = village.script.prompts[-1].split("\n\n")[0]
    assert first.endswith(f"{OPENING} Visitor is carrying a pistol. {FEELS[0]}")


@pytest.mark.anyio
async def test_without_it_the_prompt_is_as_it_was() -> None:
    plain, unarmed = Village(npcs=(BEN,)), Village(npcs=(BEN,))
    watched(unarmed, lambda: (lamp(), ROUNDS), (BEN,))

    for village in (plain, unarmed):
        village.players.say("Hello!", "ben")
        await village.run()

    assert unarmed.script.prompts == plain.script.prompts


@pytest.mark.anyio
async def test_once_it_is_put_away_no_prompt_mentions_it_but_the_trust_stays_dented() -> None:
    npc = make_npc("ben", "house_2", tradition=0.7, security=0.5, connection=0.0)
    carried: list[Sequence[Item]] = [(PISTOL,)]
    village = Village(npcs=(npc,))
    watched(village, lambda: carried[0], (npc,))
    await village.run()
    dented = village.store.relationship("ben", PLAYER_ID)
    assert dented is not None and dented.trust < meet(npc, PLAYER_ID).trust
    assert not village.script.prompts

    carried[0] = ()
    village.clock.now += timedelta(hours=2)
    village.players.say("Hello!", "ben")
    await village.run()

    [prompt, *_] = village.script.prompts
    assert "pistol" not in prompt.lower() and " gun" not in prompt.lower()
    later = village.store.relationship("ben", PLAYER_ID)
    assert later is not None and later.trust < meet(npc, PLAYER_ID).trust


@pytest.mark.anyio
async def test_someone_strongly_against_turns_an_armed_player_down_and_says_why() -> None:
    village = Village(["No. Not today. [values: security]"], npcs=(WARY, BEN))
    watched(village, lambda: (PISTOL,), (WARY, BEN))
    await village.run()

    village.players.say("Hello!", "ana")
    await village.run(5 + DEFAULT_PLAYER_CONFIG.farewell_wait)

    [prompt] = village.script.prompts
    assert prompt.endswith(f"{REFUSE} {BLUNT}")
    assert FEELS[-2] in prompt
    assert "bionic" not in prompt.lower()


@pytest.mark.anyio
async def test_someone_wary_turns_them_down_politely() -> None:
    village = Village(npcs=(UNEASY, BEN))
    watched(village, lambda: (PISTOL,), (UNEASY, BEN))
    await village.run()

    village.players.say("Hello!", "ana")
    await village.run()

    talk = village.players.talk()
    assert talk is not None and talk.refusing
    assert village.script.prompts[-1].endswith(f"{REFUSE} {POLITE}")
    assert FEELS[-1] in village.script.prompts[-1]


@pytest.mark.anyio
async def test_those_who_barely_mind_and_the_unarmed_get_a_conversation() -> None:
    for npc, carried in (("ben", (PISTOL,)), ("ana", ())):
        village = Village(npcs=(WARY, BEN))
        watched(village, lambda items=carried: items, (WARY, BEN))
        village.walk_to(npc, 1)
        await village.run()

        village.players.say("Hello!", npc)
        await village.run()

        assert REFUSE not in village.script.prompts[-1]
        assert village.ended == []


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    modules = ("behaviour", "conversation", "llm", "memory", "protocol", "social", "world")
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in modules
        }
    )
    app = create_app(package)
    app.state.world = World(Clock(NOW))
    return app


def test_the_server_reads_what_the_player_carries(app: Starlette) -> None:
    with TestClient(app) as client:
        behaviour, sightings = behaviour_of(app), sightings_of(app)
        here = behaviour.movement.position("tobias")
        behaviour.movement.track(PLAYER_ID, Point(here.x + 1, here.y, here.map))
        player = player_of(app)
        player.stash = Stash(items=[PISTOL])
        assert conversations_of(app).looks("tobias") is None
        assert behaviour.unease("tobias") == 0

        player.items = [*player.items, PISTOL]
        client.portal.call(sightings.look)

        assert conversations_of(app).looks("tobias") == (
            f"Visitor is carrying a pistol. {FEELS[-2]}"
        )
        assert behaviour.unease("tobias") > 0.8
        rel = memory_of(app).relationship("tobias", PLAYER_ID)
        assert rel is not None and rel.trust < rel.baseline.trust and rel.familiarity == 0

        player.items = [item for item in player.items if item.kind is not ItemKind.WEAPON]
        assert conversations_of(app).looks("tobias") is None
        assert behaviour.unease("tobias") == 0
