import asyncio
from datetime import timedelta

import pytest

from simile.conversation import ConversationConfig
from simile.conversation.telling import KEEP, SUBJECT, UNASKED, Stance, asked
from simile.llm import FakeProvider
from simile.reflection import Extraction, Reflection, Reflector
from simile.schema import (
    PLAYER_ID,
    Fact,
    HowKnown,
    Incident,
    Knower,
    Memory,
    MemoryKind,
)
from simile.sim import ConversationEnded, ConversationStarted

from .test_player import ANA, BEN, START, Village, feeling

pytestmark = pytest.mark.anyio

NIGHT = START - timedelta(days=8)
SAW = "I saw someone in a red top hurry out of the lane behind the maker space."
HEARD = "I heard shouting and breaking glass from the maker space."
MET = "I saw Ben and Cal with their heads together at the noodle bar."
DID = "I went round with Cal to make Aris back down, and it got out of hand."
WHERE = "I was in the lane behind the maker space that night."
GONE = "Aris was attacked, and a week later she was gone."
ALIBI = "I was at home all night."
DEFLECTION = "No idea, I'm afraid."
SECRETS = (SAW, HEARD, MET, DID, WHERE)
LONG_AGO = ConversationConfig(leave_below=0.0)


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


def did(cover: str) -> Knower:
    return Knower(id="ben", how=HowKnown.DID, tells_from=None, cover=cover)


INCIDENT = Incident(
    attackers=["ben"],
    motive="Ben blamed Aris for a deal that fell through.",
    night=NIGHT,
    facts=[
        fact("gone", knower("ana", 0.0), knower("ben", 0.0)),
        fact("seen", knower("ana", 0.3)),
        fact("shouting", knower("ana", 0.9)),
        fact("meeting", knower("ana", 0.9)),
        fact("attack", did(DEFLECTION)),
        fact("there_ben", did(ALIBI)),
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
        ("ana", "meeting", MET),
        ("ben", "attack", DID),
        ("ben", "there_ben", WHERE),
    ]
]


def investigating(*, incident: Incident | None = INCIDENT, **kwargs: object) -> Village:
    village = Village(["Hmm. [values: honesty]"], **kwargs)  # type: ignore[arg-type]
    village.store.add(*MEMORIES)
    village.engine.incident = lambda: incident
    return village


def started(village: Village) -> str:
    return village.of(ConversationStarted)[0].conversation.id


def test_the_incident_is_touched_by_a_mention_of_aris_or_that_night() -> None:
    for said in (
        "Did you know Aris?",
        "Where were you that night?",
        "Who smashed up her workshop?",
        "What happened to her?",
        "Have you seen the mechanic lately?",
        "Tell me about the attack.",
    ):
        assert asked(said), said
    for said in (
        "Lovely morning, isn't it?",
        "My uncle had a heart attack last year.",
        "Where were you yesterday?",
        "I'm off to the workshop.",
    ):
        assert not asked(said), said


async def test_a_witness_tells_what_they_trust_the_player_with_and_keeps_back_the_rest() -> None:
    village = investigating()

    village.players.say("Did you see anything the night Aris was attacked?", "ana")
    await village.run()

    prompt = village.script.prompts[-1]
    assert f'trust Visitor enough to tell them if they ask: "{SAW}"' in prompt
    assert f'"{GONE}"' in prompt
    assert prompt.count(KEEP.format(other="Visitor")) == 1
    assert HEARD not in prompt and MET not in prompt
    talk = village.players.talk()
    assert talk is not None
    stances = {id: telling.stance for id, telling in talk.tellings.items()}
    assert stances == {
        "gone": Stance.TELL,
        "seen": Stance.TELL,
        "shouting": Stance.KEEP,
        "meeting": Stance.KEEP,
    }
    assert talk.lies == {} and UNASKED not in prompt
    assert village.engine.lies(started(village)) == []


async def test_trust_opens_up_what_they_kept_back() -> None:
    village = investigating(relationships=[feeling(ANA, PLAYER_ID, trust=0.95)])

    village.players.say("What happened to Aris?", "ana")
    await village.run()

    prompt = village.script.prompts[-1]
    assert f'"{HEARD}"' in prompt and f'"{MET}"' in prompt
    assert KEEP.format(other="Visitor") not in prompt


async def test_an_attacker_gives_each_cover_only_to_its_own_question() -> None:
    village = investigating()
    village.walk_to("ben", 1)

    village.players.say("Where were you the night Aris was attacked?", "ben")
    await village.run()

    prompt = village.script.prompts[-1]
    assert (
        "You won't say where you'd been the night Aris was attacked. Only if asked that, say "
        f'exactly: "{ALIBI}" Use that cover story and nothing else'
    ) in prompt
    assert (
        f'You won\'t say who attacked Aris. Only if asked that, say exactly: "{DEFLECTION}"'
    ) in prompt
    assert prompt.count(UNASKED) == 1
    assert not any(secret in prompt for secret in SECRETS)
    talk = village.players.talk()
    assert talk is not None and talk.tellings["attack"].stance is Stance.LIE
    assert talk.lies["fact/there_ben"].fact_id == "there_ben"
    lies = village.engine.lies(started(village))
    assert {(lie.liar, lie.listener, lie.subject) for lie in lies} == {("ben", PLAYER_ID, SUBJECT)}
    assert {lie.fact_id for lie in lies} == {"attack", "there_ben"}
    assert not any(secret in lie.said for lie in lies for secret in SECRETS)


async def test_nothing_is_set_up_until_the_player_asks_and_then_it_stays() -> None:
    village = investigating(config=LONG_AGO)
    village.walk_to("ben", 1)

    for said in ("Lovely morning, isn't it?", "Did you know Aris?", "What do you do for fun?"):
        village.players.say(said, "ben")
        await village.run()

    first, second, third = village.script.prompts
    assert ALIBI not in first and GONE not in first
    assert ALIBI in second and ALIBI in third
    assert len(village.engine.lies(started(village))) == 2


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
        for remembered in (*SECRETS, GONE, ALIBI):
            assert remembered not in prompt


async def test_b3_never_sees_the_truth_and_files_the_lie_under_its_fact() -> None:
    reflected = Extraction(
        reflections=[
            Reflection(
                npc="ben",
                summary="Visitor asked where I was that night, and I said I was home.",
                valence=-0.1,
                salience=0.4,
            )
        ],
        lies=["L1", "L2"],
    )
    provider = FakeProvider([f"{ALIBI} [values: honesty]", "Bye now!", reflected])
    village = investigating(provider=provider, config=LONG_AGO)
    village.walk_to("ben", 1)
    reflector = Reflector(
        village.store,
        lambda: village.behaviour.npcs,
        lambda: village.llm,
        lies=village.engine.lies,
    )
    village.world.bus.subscribe(ConversationEnded, reflector.on_ended)

    village.players.say("Where were you the night Aris was attacked?", "ben")
    await village.run(4)
    village.players.say("Bye!", "ben")
    await village.run(4)
    await asyncio.gather(*reflector.tasks)

    b3 = provider.requests[2].messages[-1].content
    assert ALIBI in b3 and not any(secret in b3 for secret in SECRETS)
    everyday = village.store.recall("ben", village.clock.now, k=100)
    assert everyday and all(m.fact_id is None for m in everyday)
    for memory in everyday:
        assert "lied" not in memory.content
        assert not any(secret in memory.content for secret in SECRETS)
    lied = [m for m in village.store.facts("ben") if "lie" in m.topics]
    assert {m.fact_id for m in lied} == {"attack", "there_ben"}
    assert {m.content for m in lied} == {"I lied to Visitor about what happened to Aris."}
