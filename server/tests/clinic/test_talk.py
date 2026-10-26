import itertools
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.clinic.clinic import Clinic
from simile.clinic.config import DEFAULT_CONFIG
from simile.clinic.doctor import load_doctor
from simile.clinic.talk import DoctorTalk, sentences
from simile.economy import DEFAULT_CONFIG as ECONOMY
from simile.economy.economy import Economy
from simile.llm import FakeProvider, LLMClient, LLMError
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.schema import (
    PLAYER_ID,
    SOLD,
    Bionic,
    Body,
    Effect,
    EffectKind,
    Item,
    ItemKind,
    Line,
    Mind,
    Player,
    lamp,
)
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    Event,
    FakeWallClock,
    LineSpoken,
    World,
)
from simile.world import Movement, Point
from simile.world.map import load_maps

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 12, tzinfo=UTC)
MAPS = load_maps()
DOCTOR = load_doctor()
INSIDE = Point(4, 2, "clinic_floor_0")
OUTSIDE = Point(80, 15, "metro")
REPLY = "Kidney's a hundred. Legs are eighty."


class Depot:
    """The player and the doctor, on a fake wall clock, with the player outside the clinic."""

    def __init__(self, replies: Sequence[str | BaseException] = (), player: Player | None = None):
        self.world = World(Clock(START), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        behaviour = Behaviour(
            self.world.clock,
            self.world.bus,
            self.movement,
            load_npcs()[:1],
            MemoryStore(":memory:"),
            seed=0,
        )
        self.player = player or Player()
        economy = Economy(self.world.clock, behaviour, player=self.player)
        self.clinic = Clinic(self.player, self.movement, economy, self.world.clock)
        self.provider = FakeProvider(replies, default=REPLY)
        self.llm: LLMClient | None = LLMClient(self.provider)
        self.talk = DoctorTalk(
            DOCTOR,
            self.clinic,
            self.world.clock,
            self.world.bus,
            lambda: self.llm,
            itertools.count(1),
            ECONOMY.salvage,
        )
        self.events: list[Event] = []
        self.world.bus.subscribe(Event, self.events.append)
        self.world.loop.register(self.talk)
        self.stand(OUTSIDE)

    def stand(self, at: Point) -> None:
        self.movement.track(PLAYER_ID, at)

    async def run(self, seconds: float = 10) -> None:
        await self.world.loop.run(timedelta(seconds=seconds))

    def of[E: Event](self, kind: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, kind)]

    @property
    def spoken(self) -> list[Line]:
        return [event.line for event in self.of(LineSpoken)]


async def test_the_doctor_greets_the_player_as_they_walk_in() -> None:
    depot = Depot(["Sit down. What are you selling?"])

    await depot.run()
    depot.stand(INSIDE)
    await depot.run()

    [started] = depot.of(ConversationStarted)
    assert started.conversation.participants == [DOCTOR.id, PLAYER_ID]
    assert [line.text for line in depot.spoken] == ["Sit down.", "What are you selling?"]
    assert {line.speaker for line in depot.spoken} == {DOCTOR.id}
    first, second = depot.spoken
    assert second.timestamp >= first.timestamp + timedelta(seconds=first.duration)
    assert depot.talk.live()[0].lines == depot.spoken


async def test_the_doctor_greets_again_only_after_a_while() -> None:
    depot = Depot()
    depot.stand(INSIDE)
    await depot.run(70)
    depot.stand(OUTSIDE)
    await depot.run()
    depot.stand(INSIDE)
    await depot.run()

    assert len(depot.of(ConversationStarted)) == 1
    await depot.run(DEFAULT_CONFIG.greet_every * 3600)
    depot.stand(OUTSIDE)
    await depot.run()
    depot.stand(INSIDE)
    await depot.run()
    assert len(depot.of(ConversationStarted)) == 2


async def test_the_player_talks_and_the_doctor_replies_at_player_priority() -> None:
    depot = Depot()
    depot.stand(INSIDE)
    await depot.run()
    depot.provider.requests.clear()

    assert depot.talk.say("  How much   for the legs? ", DOCTOR.id)
    await depot.run()

    texts = [(line.speaker, line.text) for line in depot.spoken]
    assert (PLAYER_ID, "How much for the legs?") in texts
    assert texts[-2:] == [(DOCTOR.id, "Kidney's a hundred."), (DOCTOR.id, "Legs are eighty.")]
    [request] = depot.provider.requests
    assert request.system == depot.talk.system
    assert request.messages[-1].content.endswith(
        "Visitor: How much for the legs?\n\nReply to Visitor."
    )


async def test_the_player_opens_the_talk_if_the_doctor_hasnt() -> None:
    depot = Depot()
    depot.llm = None
    depot.stand(INSIDE)
    await depot.run()
    depot.llm = LLMClient(depot.provider)

    assert depot.talk.say("Hello?", DOCTOR.id)
    await depot.run()

    [started] = depot.of(ConversationStarted)
    assert started.conversation.participants == [PLAYER_ID, DOCTOR.id]


async def test_the_doctor_hears_nobody_outside_the_clinic_or_said_to_someone_else() -> None:
    depot = Depot()

    assert not depot.talk.say("Hello?", DOCTOR.id)
    depot.stand(INSIDE)
    assert not depot.talk.say("Hello?", "mirela")
    assert not depot.talk.say("   ", DOCTOR.id)


async def test_walking_out_or_falling_silent_ends_the_talk() -> None:
    depot = Depot()
    depot.stand(INSIDE)
    await depot.run()
    depot.stand(OUTSIDE)
    await depot.run(1)

    [ended] = depot.of(ConversationEnded)
    assert ended.conversation.ended is not None and depot.talk.live() == []
    depot.stand(INSIDE)
    await depot.run(1)
    assert depot.talk.say("Well?", DOCTOR.id)
    await depot.run(DEFAULT_CONFIG.silence + 15)
    assert len(depot.of(ConversationEnded)) == 2
    assert depot.talk.live() == []


async def test_a_failed_reply_leaves_the_doctor_silent() -> None:
    depot = Depot([LLMError("down")])
    depot.stand(INSIDE)
    await depot.run()

    assert len(depot.of(ConversationStarted)) == 1
    assert depot.spoken == []


async def test_the_doctor_knows_the_fixed_prices_and_what_they_would_do_now() -> None:
    body = Body(legs=Bionic.BIONIC_LEGS, left_kidney=SOLD)
    depot = Depot(player=Player(body=body))
    depot.stand(INSIDE)
    await depot.run()

    [request] = depot.provider.requests
    system, prompt = request.system, request.messages[-1].content
    assert "You never haggle" in system
    assert f"kidney for {DEFAULT_CONFIG.kidney:g}" in system
    assert "copper wire 6" in system
    assert "a recipe the customer knows" in system
    assert "Nothing you build runs without a power cell in place of the stomach" in system
    for recipe in DEFAULT_CONFIG.recipes.values():
        assert recipe.name not in system, "no menu of every bionic"
    assert "bionic legs where their own legs were" in prompt
    assert "the scar where you took a kidney" in prompt
    assert "What you'd do for them now: nothing, until they know how to build something." in prompt
    assert "buy a kidney" not in prompt


async def test_what_she_says_follows_the_recipes_they_know() -> None:
    mind = Mind(recipes=[Bionic.POWER_CELL, Bionic.DATAJACK, Bionic.INFRARED_EYE])
    items = [lamp(), Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)]
    depot = Depot(player=Player(money=10, items=items, mind=mind))
    depot.stand(INSIDE)
    await depot.run()

    [request] = depot.provider.requests
    prompt = request.messages[-1].content
    assert (
        "build the power cell for 100, using up 3 lithium cell and 1 charge controller, though"
        in prompt
    )
    assert "buy their recipe for the datajack for a one-off 15" in prompt
    assert "buy their recipe for the power cell" not in prompt
    assert (
        "They know how to build the datajack and infrared eye, but not before a power cell"
        in prompt
    )
    hint = prompt.split("you might hint at")[1]
    assert "the bionic legs, in place of their own legs" in hint
    assert "the spring feet" in hint and "datajack" not in hint and "grade 2" not in hint


async def test_she_offers_to_patch_up_the_hurt_and_treat_their_ailments() -> None:
    bite = Effect(kind=EffectKind.RAT_BITE, strength=0.4, fades=0.25, since=START)
    depot = Depot(player=Player(health=0.5, effects=[bite], body=Body(left_kidney=SOLD)))
    depot.stand(INSIDE)
    await depot.run()

    [request] = depot.provider.requests
    system, prompt = request.system, request.messages[-1].content
    assert "patch up the hurt, for up to 30" in system
    assert "clean the bite for 5 and treat the infection for 25" in system
    assert "patch up for 15 and clean the bite for 5." in prompt


async def test_she_hints_at_the_cell_to_someone_who_knows_nothing() -> None:
    depot = Depot()
    depot.stand(INSIDE)
    await depot.run()

    [request] = depot.provider.requests
    hint = request.messages[-1].content.split("you might hint at")[1]
    assert "the power cell, in place of their stomach" in hint
    assert "grade" not in hint


def test_a_reply_is_spoken_a_sentence_at_a_time_without_a_name_label() -> None:
    assert sentences("Annelie: Sit. Shirt off!   It won't hurt… much.", DOCTOR.name) == [
        "Sit.",
        "Shirt off!",
        "It won't hurt… much.",
    ]
