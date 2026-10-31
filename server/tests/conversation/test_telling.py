import asyncio
from datetime import timedelta

import pytest

from simile.conversation import ConversationConfig
from simile.conversation.telling import KEEP, SUBJECT, UNASKED, Stance, asked
from simile.llm import FakeProvider
from simile.reflection import Extraction, Reflection, Reflector
from simile.schema import (
    PLAYER_ID,
    Disappearance,
    Fact,
    HowKnown,
    Knower,
    Memory,
    MemoryKind,
)
from simile.sim import ConversationEnded, ConversationStarted

from .test_player import ANA, BEN, START, Village, feeling

pytestmark = pytest.mark.anyio

NIGHT = START - timedelta(days=2)
SAW = "I saw Aris heading down Banyan Row's steps towards the old metro."
HEARD = "I heard Ben say Aris wasn't one of us any more."
OVERHEARD = "I heard Cal say Aris's machinery gave him the creeps."
DID = "I never trusted what Aris did to herself, and I said so."
PASSED = "I passed Aris on Banyan Row's steps that evening and said nothing."
GONE = "Aris's workshop was found standing open, and she was gone."
NOT_SEEN = "I didn't see her that evening."
DENIAL = "Aris and I always got on fine."
SECRETS = (SAW, HEARD, OVERHEARD, DID, PASSED)
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


def distruster(how: HowKnown, cover: str) -> Knower:
    return Knower(id="ben", how=how, tells_from=0.75, cover=cover)


DISAPPEARANCE = Disappearance(
    distrusted_by=["ben"],
    facts=[
        fact("gone", knower("ana", 0.0), knower("ben", 0.0)),
        fact("last_seen", knower("ana", 0.3)),
        fact("distrust_ben", distruster(HowKnown.DID, DENIAL), knower("ana", 0.9)),
        fact("distrust_cal", knower("ana", 0.9)),
        fact("passed", distruster(HowKnown.WITNESSED, NOT_SEEN)),
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
        ("ana", "last_seen", SAW),
        ("ana", "distrust_ben", HEARD),
        ("ana", "distrust_cal", OVERHEARD),
        ("ben", "distrust_ben", DID),
        ("ben", "passed", PASSED),
    ]
]


def investigating(
    *, disappearance: Disappearance | None = DISAPPEARANCE, **kwargs: object
) -> Village:
    village = Village(["Hmm. [values: honesty]"], **kwargs)  # type: ignore[arg-type]
    village.store.add(*MEMORIES)
    village.engine.disappearance = lambda: disappearance
    return village


def started(village: Village) -> str:
    return village.of(ConversationStarted)[0].conversation.id


def test_the_story_is_touched_by_a_mention_of_aris_or_her_going_missing() -> None:
    for said in (
        "Did you know Aris?",
        "What happened at the workshop?",
        "What happened to her?",
        "Have you seen the mechanic lately?",
        "Do you know where she went?",
        "When did you last see her? When you last saw her, I mean.",
        "Has anyone seen her since?",
        "How did you get on with her?",
        "They say she went missing a few days ago.",
        "Did you hear that she disappeared?",
    ):
        assert asked(said), said
    for said in (
        "Hello there! Lovely day for it.",
        "Lovely morning, isn't it?",
        "Where were you yesterday?",
        "Where were you that night?",
        "Have you seen the news?",
        "My keys are gone again.",
        "I saw her at the café.",
        "I'm off to the workshop.",
        "Ingrid's at the maker space all day.",
    ):
        assert not asked(said), said


async def test_a_witness_tells_what_they_trust_the_player_with_and_keeps_back_the_rest() -> None:
    village = investigating()

    village.players.say("Did you see Aris the evening before she went missing?", "ana")
    await village.run()

    prompt = village.script.prompts[-1]
    assert f'trust Visitor enough to tell them if they ask: "{SAW}"' in prompt
    assert f'"{GONE}"' in prompt
    assert prompt.count(KEEP.format(other="Visitor")) == 1
    assert HEARD not in prompt and OVERHEARD not in prompt
    talk = village.players.talk()
    assert talk is not None
    stances = {id: telling.stance for id, telling in talk.tellings.items()}
    assert stances == {
        "gone": Stance.TELL,
        "last_seen": Stance.TELL,
        "distrust_ben": Stance.KEEP,
        "distrust_cal": Stance.KEEP,
    }
    assert talk.lies == {} and UNASKED not in prompt
    assert village.engine.lies(started(village)) == []


async def test_trust_opens_up_what_they_kept_back() -> None:
    village = investigating(relationships=[feeling(ANA, PLAYER_ID, trust=0.95)])

    village.players.say("What happened to Aris?", "ana")
    await village.run()

    prompt = village.script.prompts[-1]
    assert f'"{HEARD}"' in prompt and f'"{OVERHEARD}"' in prompt
    assert KEEP.format(other="Visitor") not in prompt


async def test_a_distruster_gives_each_cover_only_to_its_own_question() -> None:
    village = investigating()
    village.walk_to("ben", 1)

    village.players.say("How did you get on with Aris?", "ben")
    await village.run()

    prompt = village.script.prompts[-1]
    assert (
        "You won't say how you got on with Aris. Only if asked that, say exactly: "
        f'"{DENIAL}" Use that cover story and nothing else'
    ) in prompt
    assert (
        "You won't say whether you saw Aris the evening before she went missing. Only if asked "
        f'that, say exactly: "{NOT_SEEN}"'
    ) in prompt
    assert prompt.count(UNASKED) == 1
    assert not any(secret in prompt for secret in SECRETS)
    talk = village.players.talk()
    assert talk is not None and talk.tellings["passed"].stance is Stance.LIE
    assert talk.lies["fact/distrust_ben"].fact_id == "distrust_ben"
    lies = village.engine.lies(started(village))
    assert {(lie.liar, lie.listener, lie.subject) for lie in lies} == {("ben", PLAYER_ID, SUBJECT)}
    assert {lie.fact_id for lie in lies} == {"distrust_ben", "passed"}
    assert not any(secret in lie.said for lie in lies for secret in SECRETS)


async def test_nothing_is_set_up_until_the_player_asks_and_then_it_stays() -> None:
    village = investigating(config=LONG_AGO)
    village.walk_to("ben", 1)

    for said in ("Lovely morning, isn't it?", "Did you know Aris?", "What do you do for fun?"):
        village.players.say(said, "ben")
        await village.run()

    first, second, third = village.script.prompts
    assert DENIAL not in first and GONE not in first
    assert DENIAL in second and DENIAL in third
    assert len(village.engine.lies(started(village))) == 2


async def test_without_a_disappearance_nobody_knows_anything() -> None:
    village = investigating(disappearance=None)

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
        for remembered in (*SECRETS, GONE, DENIAL):
            assert remembered not in prompt


ADMITTED = "I told Visitor I never saw her that evening, though I did."
FINE = "We got on fine."
HOME = "I was home all evening."
GRUDGES = Disappearance(
    distrusted_by=["ben"],
    facts=[
        fact("distrust_ben", distruster(HowKnown.DID, FINE)),
        fact("last_seen", knower("ana", 0.9, HOME)),
    ],
)


def remembered(owner: str, fact_id: str, content: str) -> Memory:
    return Memory(
        owner=owner,
        kind=MemoryKind.OBSERVATION,
        content=content,
        salience=0.9,
        valence=-0.5,
        timestamp=NIGHT,
        about=["aris"],
        fact_id=fact_id,
    )


def reflecting(village: Village) -> Reflector:
    reflector = Reflector(
        village.store,
        lambda: village.behaviour.npcs,
        lambda: village.llm,
        lies=village.engine.lies,
    )
    village.world.bus.subscribe(ConversationEnded, reflector.on_ended)
    return reflector


async def ask_and_leave(village: Village, reflector: Reflector, npc: str, said: str) -> None:
    village.players.say(said, npc)
    await village.run(4)
    village.players.say("Bye!", npc)
    await village.run(4)
    await asyncio.gather(*reflector.tasks)


def admits(npc: str, summary: str) -> Extraction:
    return Extraction(
        reflections=[Reflection(npc=npc, summary=summary, valence=-0.1, salience=0.4)],
        lies=["L1", "L2"],
    )


async def test_b3_never_sees_the_truth_and_files_the_lie_and_its_summary_under_the_fact() -> None:
    provider = FakeProvider([f"{NOT_SEEN} [values: honesty]", "Bye now!", admits("ben", ADMITTED)])
    village = investigating(provider=provider, config=LONG_AGO)
    village.walk_to("ben", 1)
    reflector = reflecting(village)

    await ask_and_leave(village, reflector, "ben", "When did you last see her?")

    b3 = provider.requests[2].messages[-1].content
    assert NOT_SEEN in b3 and not any(secret in b3 for secret in SECRETS)
    assert village.store.recall("ben", village.clock.now, k=100) == []
    filed = {m.content: m.fact_id for m in village.store.facts("ben") if m.timestamp > NIGHT}
    assert filed[ADMITTED] in {"distrust_ben", "passed"}
    assert filed["I lied to Visitor about what happened to Aris."] in {"distrust_ben", "passed"}


@pytest.mark.parametrize(
    ("npc", "remembers", "cover"),
    [("ben", DID, FINE), ("ana", SAW, HOME)],
)
async def test_someone_who_lied_tells_what_they_remember_once_they_trust_the_player(
    npc: str, remembers: str, cover: str
) -> None:
    provider = FakeProvider(
        [f"{cover} [values: honesty]", "Bye now!", admits(npc, "I put Visitor off."), "Well."]
    )
    village = investigating(disappearance=GRUDGES, provider=provider, config=LONG_AGO)
    village.walk_to(npc, 1)
    reflector = reflecting(village)
    await ask_and_leave(village, reflector, npc, "Did Aris fall out with anyone?")
    assert f'say exactly: "{cover}"' in provider.requests[0].messages[-1].content
    village.store.add(feeling(ANA if npc == "ana" else BEN, PLAYER_ID, trust=0.95))

    village.players.say("What happened to Aris?", npc)
    await village.run()

    prompt = provider.requests[-1].messages[-1].content
    assert f'trust Visitor enough to tell them if they ask: "{remembers}"' in prompt
    assert "I lied to Visitor" not in prompt and "I put Visitor off." not in prompt
