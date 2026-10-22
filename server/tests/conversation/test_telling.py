from datetime import timedelta

import pytest

from simile.conversation import ConversationConfig
from simile.conversation.telling import KEEP, SUBJECT, Stance, asked
from simile.schema import (
    PLAYER_ID,
    Fact,
    HowKnown,
    Incident,
    Knower,
    Memory,
    MemoryKind,
)
from simile.sim import ConversationStarted

from .test_player import ANA, BEN, START, Village, feeling

pytestmark = pytest.mark.anyio

NIGHT = START - timedelta(days=8)
SAW = "I saw someone in a red top hurry out of the lane behind the maker space."
HEARD = "I heard shouting and breaking glass from the maker space."
DID = "I went round to make Aris back down, and it got out of hand."
GONE = "Aris was attacked, and a week later she was gone."
ALIBI = "I was at home all night."


def fact(id: str, *known_by: Knower) -> Fact:
    return Fact(
        id=id,
        what=f"What happened: {id}.",
        when=NIGHT,
        where="maker_space",
        about=["aris", "ben"],
        known_by=list(known_by),
    )


def knower(id: str, tells_from: float | None, cover: str | None = None) -> Knower:
    return Knower(id=id, how=HowKnown.WITNESSED, tells_from=tells_from, cover=cover)


INCIDENT = Incident(
    attackers=["ben"],
    motive="Ben blamed Aris for a deal that fell through.",
    night=NIGHT,
    facts=[
        fact("gone", knower("ana", 0.0), knower("ben", 0.0)),
        fact("seen", knower("ana", 0.3)),
        fact("shouting", knower("ana", 0.9)),
        fact("attack", Knower(id="ben", how=HowKnown.DID, tells_from=None, cover=ALIBI)),
    ],
)
MEMORIES = [
    Memory(
        owner=owner,
        kind=MemoryKind.OBSERVATION,
        content=content,
        salience=0.9,
        valence=-0.5,
        timestamp=NIGHT,
        about=["aris"],
        fact_id=fact_id,
    )
    for owner, fact_id, content in [
        ("ana", "gone", GONE),
        ("ben", "gone", GONE),
        ("ana", "seen", SAW),
        ("ana", "shouting", HEARD),
        ("ben", "attack", DID),
    ]
]


def investigating(*, incident: Incident | None = INCIDENT, **kwargs: object) -> Village:
    village = Village(["Hmm. [values: honesty]"], **kwargs)  # type: ignore[arg-type]
    village.store.add(*MEMORIES)
    village.engine.incident = lambda: incident
    return village


def started(village: Village) -> str:
    return village.of(ConversationStarted)[0].conversation.id


def test_the_incident_is_touched_by_aris_the_workshop_and_that_night() -> None:
    assert asked("Did you know Aris?")
    assert asked("Where were you that night?")
    assert asked("Who smashed up the workshop?")
    assert not asked("Lovely morning, isn't it?")
    assert not asked("I'm thinking of going to the market.")


async def test_a_witness_tells_what_they_trust_the_player_with_and_keeps_back_the_rest() -> None:
    village = investigating()

    village.players.say("Did you see anything the night Aris was attacked?", "ana")
    await village.run()

    prompt = village.script.prompts[-1]
    assert f'trust Visitor enough to tell them if they ask: "{SAW}"' in prompt
    assert f'"{GONE}"' in prompt
    assert KEEP.format(other="Visitor") in prompt
    assert HEARD not in prompt
    talk = village.players.talk()
    assert talk is not None
    stances = {id: telling.stance for id, telling in talk.tellings.items()}
    assert stances == {"gone": Stance.TELL, "seen": Stance.TELL, "shouting": Stance.KEEP}
    assert talk.lies == {} and village.engine.lies(started(village)) == []


async def test_trust_opens_up_what_they_kept_back() -> None:
    village = investigating(relationships=[feeling(ANA, PLAYER_ID, trust=0.95)])

    village.players.say("What happened to Aris?", "ana")
    await village.run()

    assert f'"{HEARD}"' in village.script.prompts[-1]
    assert KEEP.format(other="Visitor") not in village.script.prompts[-1]


async def test_an_attacker_lies_with_their_cover_story_for_b3_and_the_eye() -> None:
    village = investigating()
    village.walk_to("ben", 1)

    village.players.say("Where were you the night Aris was attacked?", "ben")
    await village.run()

    prompt = village.script.prompts[-1]
    assert f'You remember this, but won\'t own up to it: "{DID}"' in prompt
    assert f'If it comes up, say "{ALIBI}" Use that cover story and nothing else' in prompt
    talk = village.players.talk()
    assert talk is not None and talk.tellings["attack"].stance is Stance.LIE
    assert talk.lies["fact/attack"].fact_id == "attack"
    [told] = village.engine.lies(started(village))
    assert (told.liar, told.listener, told.subject) == ("ben", PLAYER_ID, SUBJECT)
    assert told.admits == "I lied to Visitor about what happened to Aris."


async def test_nothing_is_set_up_until_the_player_asks_and_then_it_stays() -> None:
    village = investigating(config=ConversationConfig(leave_below=0.0))
    village.walk_to("ben", 1)

    for said in ("Lovely morning, isn't it?", "Did you know Aris?", "What do you do for fun?"):
        village.players.say(said, "ben")
        await village.run()

    first, second, third = village.script.prompts
    assert ALIBI not in first and GONE not in first
    assert ALIBI in second and ALIBI in third
    assert len(village.engine.lies(started(village))) == 1


async def test_without_an_incident_nobody_knows_anything() -> None:
    village = investigating(incident=None)

    village.players.say("What happened to Aris?", "ana")
    await village.run()

    talk = village.players.talk()
    assert talk is not None and talk.tellings == {}
    assert SAW not in village.script.prompts[-1]


async def test_what_they_know_never_comes_up_in_a_scene_or_on_their_mind() -> None:
    village = investigating(npcs=(ANA, BEN))

    village.engine.start("ana", "ben")
    await village.run(60)
    village.players.say("Nice weather.", "ana")
    await village.run()

    assert "Ana has just walked up to Ben" in village.script.prompts[0]
    assert "Say your next line to Visitor" in village.script.prompts[-1]
    for prompt in village.script.prompts:
        for remembered in (SAW, HEARD, DID, GONE, ALIBI):
            assert remembered not in prompt
