import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from simile.llm import CallRecord, FakeProvider, LLMClient, LLMError, Request
from simile.memory import MemoryStore
from simile.reflection import SYSTEM, Deed, Extraction, NewFlag, Reflection, Reflector
from simile.schema import Conversation, FlagKind, MemoryKind, Npc
from simile.sim import ConversationEnded, EventBus

pytestmark = pytest.mark.anyio

Talk = Callable[..., Conversation]

END = datetime(2026, 1, 1, 9, 2, tzinfo=UTC)

FRIENDLY = (
    ("ana", "Ben! I saved you a slice of the lemon cake, I know it's your favourite."),
    ("ben", "That's very kind of you, Ana. Shall we walk to the square later?"),
    ("ana", "I'd love that."),
)
HOSTILE = (
    ("ben", "Your stall is blocking my door again, Ana. It's a disgrace."),
    ("ana", "Oh, give it a rest, Ben. Nobody cares about your door."),
    ("ben", "Move it by Friday and I'll say no more about it."),
    ("ana", "Fine. I promise it'll be gone by Friday."),
)


def warm(by: str, action: str) -> Deed:
    return Deed(by=by, action=action, aspects=["like"], valence=0.6, magnitude=0.5)


def cold(by: str, action: str) -> Deed:
    return Deed(by=by, action=action, aspects=["like"], valence=-0.6, magnitude=0.5)


def read(request: Request) -> str:
    """Stands in for the LLM, reading the transcript in the prompt."""
    transcript = request.messages[-1].content.split("The conversation:\n")[1]
    if "disgrace" in transcript:
        extraction = Extraction(
            reflections=[
                Reflection(
                    npc="ben",
                    summary="Ana brushed me off about her stall, but promised to move it.",
                    valence=-0.5,
                    salience=0.6,
                    topics=["the stall"],
                    events=[cold("ana", "told Ben nobody cares about his door")],
                    flags_opened=[
                        NewFlag(
                            kind=FlagKind.PROMISE,
                            about="ana",
                            description="moving her stall from Ben's door by Friday",
                        )
                    ],
                ),
                Reflection(
                    npc="ana",
                    summary="Ben called my stall a disgrace.",
                    valence=-0.5,
                    salience=0.5,
                    events=[cold("ben", "called Ana's stall a disgrace")],
                ),
            ]
        )
    else:
        extraction = Extraction(
            reflections=[
                Reflection(
                    npc="ana",
                    summary="Ben and I are going for a walk later.",
                    valence=0.6,
                    salience=0.4,
                    events=[warm("ben", "asked Ana for a walk")],
                ),
                Reflection(
                    npc="ben",
                    summary="Ana saved me some lemon cake.",
                    valence=0.6,
                    salience=0.4,
                    events=[warm("ana", "saved Ben some lemon cake")],
                ),
            ]
        )
    return extraction.model_dump_json()


def logged(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "simile.reflection.reflector"]


def reflector(store: MemoryStore, npcs: dict[str, Npc], llm: LLMClient | None) -> Reflector:
    return Reflector(store, lambda: npcs, lambda: llm)


async def test_a_friendly_conversation_raises_like(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    result = await reflector(store, npcs, None).reflect(
        LLMClient(FakeProvider([read])), talk(*FRIENDLY)
    )

    assert result is not None
    for key, before in result.before.items():
        assert store.relationship(*key).like > before.like
    [memory] = store.recall("ben", END, about="ana")
    assert memory.content == "Ana saved me some lemon cake."
    assert memory.kind == MemoryKind.CONVERSATION
    assert [e.action for e in store.shared_history("ana", "ben", END).events] == [
        "asked Ana for a walk",
        "saved Ben some lemon cake",
    ]


async def test_a_hostile_one_lowers_it_more(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    llm = LLMClient(FakeProvider([read, read]))
    with MemoryStore(":memory:") as other:
        friendly = await reflector(other, npcs, None).reflect(llm, talk(*FRIENDLY))
    hostile = await reflector(store, npcs, None).reflect(llm, talk(*HOSTILE))

    assert friendly is not None and hostile is not None
    for key in [("ana", "ben"), ("ben", "ana")]:
        gained = friendly.after[key].like - friendly.before[key].like
        lost = hostile.before[key].like - hostile.after[key].like
        assert lost > gained > 0


async def test_a_promise_becomes_a_flag(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    await reflector(store, npcs, None).reflect(LLMClient(FakeProvider([read])), talk(*HOSTILE))

    [flag] = store.relationship("ben", "ana").flags
    assert flag.kind == FlagKind.PROMISE
    assert (flag.owner, flag.about) == ("ben", "ana")
    assert flag.description == "moving her stall from Ben's door by Friday"
    assert flag.resolved is None
    assert store.shared_history("ana", "ben", END).flags == [flag]
    assert store.relationship("ana", "ben").flags == []


async def test_reflects_with_haiku_in_one_call(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    fake = FakeProvider([read])
    records: list[CallRecord] = []

    await reflector(store, npcs, None).reflect(
        LLMClient(fake, listeners=[records.append]), talk(*FRIENDLY)
    )

    [request] = fake.requests
    assert request.model == "claude-haiku-5-5"
    assert request.system.startswith(SYSTEM)
    assert [record.purpose for record in records] == ["reflection"]


async def test_runs_in_a_task_after_the_conversation_ends(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    resume = asyncio.Event()

    async def slow(request: Request) -> str:
        await resume.wait()
        return read(request)

    bus = EventBus()
    reflecting = reflector(store, npcs, LLMClient(FakeProvider([slow])))
    bus.subscribe(ConversationEnded, reflecting.on_ended)

    bus.publish(ConversationEnded(talk(*FRIENDLY)))
    await asyncio.sleep(0.01)

    assert len(reflecting.tasks) == 1
    assert store.relationship("ana", "ben") is None
    resume.set()
    await asyncio.gather(*reflecting.tasks)
    assert store.relationship("ana", "ben") is not None


async def test_skips_a_conversation_with_no_lines(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    fake = FakeProvider()
    reflecting = reflector(store, npcs, LLMClient(fake))

    reflecting.on_ended(ConversationEnded(talk()))

    assert reflecting.tasks == set()
    assert fake.requests == []


async def test_skips_a_conversation_without_npcs(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    fake = FakeProvider()

    result = await reflector(store, npcs, None).reflect(
        LLMClient(fake), talk(("cal", "Hi."), participants=["cal", "dot"])
    )

    assert result is None
    assert fake.requests == []


async def test_logs_one_line_and_skips_a_reply_it_cant_read(
    npcs: dict[str, Npc],
    store: MemoryStore,
    talk: Talk,
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = LLMClient(FakeProvider(["Lovely chat.", "Really lovely."]))

    with caplog.at_level(logging.WARNING, logger="simile.reflection"):
        result = await reflector(store, npcs, None).reflect(llm, talk(*FRIENDLY))

    assert result is None
    assert logged(caplog) == ["Couldn't make sense of talk_1, so skipped it"]
    assert all(record.exc_info is None for record in caplog.records)
    assert store.relationship("ana", "ben") is None
    assert store.recall("ana", END) == []


async def test_logs_an_llm_error_and_skips(
    npcs: dict[str, Npc],
    store: MemoryStore,
    talk: Talk,
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = LLMClient(FakeProvider([LLMError("usage limit reached")]))

    with caplog.at_level(logging.WARNING, logger="simile.reflection"):
        result = await reflector(store, npcs, None).reflect(llm, talk(*FRIENDLY))

    assert result is None
    assert logged(caplog) == ["Couldn't reflect on talk_1: usage limit reached"]
    assert store.relationship("ana", "ben") is None


async def test_logs_relationship_changes(
    npcs: dict[str, Npc],
    store: MemoryStore,
    talk: Talk,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="simile.reflection"):
        await reflector(store, npcs, None).reflect(LLMClient(FakeProvider([read])), talk(*HOSTILE))

    ana, ben = logged(caplog)
    assert ana.startswith("talk_1: ana about ben: like ")
    assert ben.startswith("talk_1: ben about ana: like ")
    assert ben.endswith(", +promise (moving her stall from Ben's door by Friday)")


async def test_stop_cancels_reflections_in_flight(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    reflecting = reflector(store, npcs, LLMClient(FakeProvider([[asyncio.Event()]])))
    reflecting.on_ended(ConversationEnded(talk(*FRIENDLY)))
    await asyncio.sleep(0.01)

    await asyncio.wait_for(reflecting.stop(), 1)

    assert reflecting.tasks == set()
    assert store.relationship("ana", "ben") is None


async def test_waits_for_an_llm(npcs: dict[str, Npc], store: MemoryStore, talk: Talk) -> None:
    reflecting = reflector(store, npcs, None)

    reflecting.on_ended(ConversationEnded(talk(*FRIENDLY)))

    assert reflecting.tasks == set()
