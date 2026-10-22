from collections.abc import Callable
from datetime import timedelta

import pytest

from simile.conversation import DEFAULT_CONFIG
from simile.conversation.player import DEFAULT_PLAYER_CONFIG, PlayerConfig
from simile.conversation.prompt import CUES, Cue
from simile.schema import PLAYER_ID, Bionic, Body, Npc
from simile.sim import ConversationStarted
from simile.social.sightings import Sightings

from .test_player import ANA, BEN, Village, make_npc
from .test_telling import INCIDENT, MEMORIES

pytestmark = pytest.mark.anyio

LEGS = Body(legs=Bionic.HYDRAULIC_LEGS)
WARY = make_npc("ana", "house_1", tradition=1.0, security=1.0)
REFUSE = CUES[Cue.REFUSE].format(other="Visitor")
OPENING = "You're with Visitor (a newcomer to the village)."


def watched(
    village: Village,
    body: Body = LEGS,
    npcs: tuple[Npc, ...] = (WARY, BEN),
    awake: Callable[[str], bool] = lambda npc: True,
) -> Sightings:
    """S11 wired into the village as the server's lifespans wire it."""
    sightings = Sightings(
        village.store,
        village.clock,
        {npc.id: npc for npc in npcs},
        village.movement,
        lambda: body,
        awake,
    )
    village.engine.looks = sightings.looks
    village.behaviour.hooks.set(unease=sightings.unease)
    village.world.loop.register(sightings)
    return sightings


async def test_what_they_see_of_the_player_starts_the_prompt() -> None:
    village = Village(npcs=(BEN,))
    watched(village, npcs=(BEN,))

    village.players.say("Hello!", "ben")
    await village.run()

    first = village.script.prompts[-1].split("\n\n")[0]
    assert first.endswith(
        f"{OPENING} Visitor has hydraulic legs where their own legs were. The hydraulic legs are "
        "new since you last saw them. Bionics don't much bother you either way."
    )
    assert "I saw that Visitor has hydraulic legs" not in village.script.prompts[-1]


async def test_a_whole_player_looks_like_anyone_and_the_prompt_is_as_it_was() -> None:
    plain, whole = Village(npcs=(BEN,)), Village(npcs=(BEN,))
    watched(whole, Body(), npcs=(BEN,))

    for village in (plain, whole):
        village.players.say("Hello!", "ben")
        await village.run()

    assert whole.script.prompts == plain.script.prompts
    assert plain.script.prompts[-1].split("\n\n")[0].endswith(OPENING)


async def test_a_sighting_stays_on_their_mind_for_the_next_talk() -> None:
    village = Village(npcs=(BEN,))
    watched(village, npcs=(BEN,))
    await village.run()

    village.clock.now += timedelta(hours=2)
    village.players.say("Hello!", "ben")
    await village.run()

    prompt = village.script.prompts[-1]
    assert "Visitor has hydraulic legs where their own legs were. Bionics don't" in prompt
    assert "new since" not in prompt
    assert "On your mind:\n- I saw that Visitor has hydraulic legs" in prompt


async def test_someone_put_off_by_the_players_bionics_turns_them_down() -> None:
    village = Village(["No. Not today. [values: tradition]"], npcs=(WARY, BEN))
    watched(village)
    await village.run()

    village.players.say("Hello!", "ana")
    await village.run(5 + DEFAULT_PLAYER_CONFIG.farewell_wait)

    [prompt] = village.script.prompts
    assert prompt.endswith(REFUSE)
    assert "Bionics on a person repel you" in prompt
    [ended] = village.ended
    assert [line.speaker for line in ended.conversation.lines] == [PLAYER_ID, "ana", "ana"]


async def test_turning_the_player_down_sets_up_no_telling_or_lies() -> None:
    told = {}
    for body in (Body(), LEGS):
        village = Village(["No. [values: tradition]"], npcs=(WARY, BEN))
        village.store.add(*MEMORIES)
        village.engine.incident = lambda: INCIDENT
        watched(village, body)
        await village.run()

        village.players.say("Where were you the night Aris was attacked?", "ana")
        await village.run()

        talk = village.players.talk()
        assert talk is not None
        told[talk.refusing] = talk.tellings, talk.lies

    assert told[False][0] and told[True] == ({}, {})


async def test_the_tolerant_and_the_whole_player_get_a_conversation() -> None:
    for npc, body in (("ben", LEGS), ("ana", Body())):
        village = Village(npcs=(WARY, BEN))
        watched(village, body)
        village.walk_to(npc, 1)
        await village.run()

        village.players.say("Hello!", npc)
        await village.run()

        assert not village.script.prompts[-1].endswith(REFUSE)
        assert village.ended == []


async def test_nobody_turns_the_player_down_at_work(monkeypatch: pytest.MonkeyPatch) -> None:
    village = Village(npcs=(WARY, BEN))
    watched(village)
    await village.run()
    assert village.behaviour.unease("ana")

    monkeypatch.setattr(village.behaviour, "working", lambda npc: npc == "ana")
    village.players.say("A flat white, please.", "ana")
    await village.run()

    assert not village.script.prompts[-1].endswith(REFUSE)


async def test_someone_who_would_turn_the_player_down_doesnt_break_off_a_talk_for_them() -> None:
    village = Village(npcs=(WARY, BEN))
    watched(village)
    await village.run()
    village.engine.start("ana", "ben")

    assert village.players.say("Hello!", "ana") is None

    assert village.engine.talking("ana")
    assert [e.conversation.participants for e in village.of(ConversationStarted)] == [
        ["ana", "ben"]
    ]


async def test_unease_is_taken_off_the_accept_score_so_they_dont_greet() -> None:
    plain, uneasy = (Village(npcs=(ANA,), player=PlayerConfig(greet_cooldown=0)) for _ in "ab")
    before = uneasy.engine.accept_score(PLAYER_ID, "ana")

    uneasy.behaviour.hooks.set(unease=lambda npc: 0.5)

    lost = before - uneasy.engine.accept_score(PLAYER_ID, "ana")
    assert lost == pytest.approx(DEFAULT_CONFIG.accept_unease * 0.5)
    for village in (plain, uneasy):
        await village.run(DEFAULT_PLAYER_CONFIG.look_every * 3)
    assert len(plain.of(ConversationStarted)) == 1
    assert uneasy.of(ConversationStarted) == []


async def test_word_of_a_sighting_comes_up_with_someone_who_hasnt_seen_it() -> None:
    village = Village(npcs=(WARY, BEN))
    watched(village, awake=lambda npc: npc != "ben")
    await village.run()

    village.engine.start("ana", "ben")
    await village.run(1)

    ana, ben = village.script.prompts[-1].split("## Ben")
    mind = ana.split("On Ana's mind, which only Ana knows:\n")[1]
    assert mind.startswith(
        "- I saw that Visitor has hydraulic legs where their own legs were. It isn't natural, and "
        "it turned my stomach."
    )
    assert "hydraulic" not in ben.split("## Between them")[0]
