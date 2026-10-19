from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest

from simile.conversation.temptation import Lie
from simile.llm import FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.reflection import Deed, Extraction, Reflection, Reflector, gather, outcome, prompt
from simile.schema import PLAYER_ID, Aspect, Conversation, Memory, MemoryKind, Npc
from simile.social import meet

from .conftest import START

pytestmark = pytest.mark.anyio

Talk = Callable[..., Conversation]
END = START + timedelta(minutes=2)

SAID = "Ana is short of money this week. If it comes up, Ana says they're doing fine."


def short(known: bool = False, listener: str = "ben") -> Lie:
    return Lie(
        "ana",
        listener,
        SAID,
        "being short of money",
        "I lied to Ben about being short of money.",
        known,
    )


def reflection(npc: str, **changes: Any) -> Reflection:
    return Reflection.model_validate(
        {"npc": npc, "summary": f"{npc} chatted.", "valence": 0.1, "salience": 0.2} | changes
    )


def told(*refs: str, **changes: Any) -> Extraction:
    return Extraction(
        reflections=[reflection("ana"), reflection("ben", **changes)], lies=list(refs)
    )


def remembered(memories: list[Memory], topic: str) -> list[Memory]:
    return [memory for memory in memories if topic in memory.topics]


def test_the_prompt_lists_the_lies_and_whether_the_listener_knows_better(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ben", "Money all right?"), ("ana", "Never better."))

    context = gather(conversation, npcs, store, lies=[short(), short(known=True)])
    text = prompt(context)

    assert list(context.lies) == ["L1", "L2"]
    assert (
        "Lies they were set up to tell if it came up. List the refs of those told under lies:\n"
        f"- L1: {SAID} Ben didn't know, and believed it.\n"
        f"- L2: {SAID} Ben knows it isn't true."
    ) in text


def test_without_lies_the_prompt_says_nothing_of_them(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)

    assert context.lies == {}
    assert "Lies" not in prompt(context)


def test_lies_about_someone_outside_the_conversation_are_left_out(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store, lies=[short(listener="cal")])

    assert context.lies == {}


def test_the_liar_remembers_a_lie_they_told(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Never better.")), npcs, store, lies=[short()])

    result = outcome(context, told(" l1 "), store)

    [lie] = remembered(result.memories, "lie")
    assert lie == Memory(
        owner="ana",
        kind=MemoryKind.OBSERVATION,
        content="I lied to Ben about being short of money.",
        salience=0.5,
        valence=-0.2,
        timestamp=END,
        about=["ben"],
        topics=["lie"],
        conversation_id="talk_1",
    )
    assert remembered(result.memories, "lied to me") == []
    assert result.after[("ben", "ana")].trust == result.before[("ben", "ana")].trust


def test_a_lie_that_never_came_up_leaves_nothing(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store, lies=[short(known=True)])

    result = outcome(context, told(), store)

    assert remembered(result.memories, "lie") == []
    assert remembered(result.memories, "lied to me") == []


def test_a_listener_whose_own_memories_contradict_it_loses_trust(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Never better.")), npcs, store, lies=[short(known=True)])

    result = outcome(context, told("L1"), store)

    [caught] = remembered(result.memories, "lied to me")
    assert (caught.owner, caught.content, caught.about) == (
        "ben",
        "Ana lied to me about being short of money.",
        ["ana"],
    )
    [event] = [e for e in result.events if (e.actor, e.target) == ("ana", "ben")]
    assert (event.action, event.aspects, event.valence) == (
        "lied about being short of money",
        [Aspect.TRUST],
        -0.5,
    )
    assert result.after[("ben", "ana")].trust < result.before[("ben", "ana")].trust
    assert result.after[("ana", "ben")].trust == result.before[("ana", "ben")].trust


def test_a_listener_who_already_trusts_them_less_isnt_hit_twice(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Never better.")), npcs, store, lies=[short(known=True)])
    distrust = Deed(
        by="ana", action="dodged the question", aspects=["trust"], valence=-0.3, magnitude=0.3
    )

    result = outcome(context, told("L1", events=[distrust]), store)

    assert [e.action for e in result.events if e.target == "ben"] == ["dodged the question"]


def test_a_lie_to_the_player_is_remembered_by_the_liar_alone(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ana", "Never better."), participants=["ana", PLAYER_ID])
    lie = Lie(
        "ana", PLAYER_ID, SAID, "being short of money", "I lied to Visitor about money.", False
    )
    context = gather(conversation, npcs, store, lies=[lie])

    result = outcome(context, Extraction(reflections=[reflection("ana")], lies=["L1"]), store)

    assert [m.content for m in remembered(result.memories, "lie")] == [
        "I lied to Visitor about money."
    ]


async def test_the_reflector_takes_the_lies_once(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"))
    lies = {"talk_1": [short(known=True)]}
    llm = LLMClient(FakeProvider([told("L1").model_dump_json()]))
    reflector = Reflector(store, lambda: npcs, lambda: llm, lies=lambda id: lies.pop(id, []))

    await reflector.reflect(llm, talk(("ana", "Never better.")))

    assert lies == {}
    assert "Ana lied to me about being short of money." in [
        m.content for m in store.recall("ben", END, about="ana")
    ]
    assert store.relationship("ben", "ana").trust < meet(npcs["ben"], "ana").trust
