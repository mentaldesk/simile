from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from simile.memory import MemoryStore
from simile.reflection import DEFAULT_CONFIG, Deed, Extraction, NewFlag, Reflection, gather, outcome
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Conversation,
    Flag,
    FlagKind,
    InteractionEvent,
    MemoryKind,
    Npc,
)
from simile.social import DEFAULT_CONFIG as RELATIONSHIPS
from simile.social import meet

Talk = Callable[..., Conversation]

START = datetime(2026, 1, 1, 9, tzinfo=UTC)
END = START + timedelta(minutes=2)


def reflection(npc: str, **changes: Any) -> Reflection:
    return Reflection.model_validate(
        {"npc": npc, "summary": f"{npc} chatted.", "valence": 0.1, "salience": 0.2} | changes
    )


def deed(by: str, **changes: Any) -> Deed:
    return Deed.model_validate(
        {"by": by, "action": "was kind", "aspects": ["like"], "valence": 0.5, "magnitude": 0.5}
        | changes
    )


def promise(owner: str, about: str, id: str = "fence") -> Flag:
    return Flag(
        id=id,
        kind=FlagKind.PROMISE,
        owner=owner,
        about=about,
        description="fixing the fence",
        created=START - timedelta(days=1),
    )


def test_events_change_how_their_target_feels_about_the_actor(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)
    extraction = Extraction(
        reflections=[
            reflection("ana", events=[deed("ben", action="admired Ana's garden")]),
            reflection("ben", events=[deed("ana", aspects=["trust", "trust"], valence=-0.4)]),
        ]
    )

    result = outcome(context, extraction, store)

    assert result.events == [
        InteractionEvent(
            actor="ben",
            target="ana",
            action="admired Ana's garden",
            aspects=[Aspect.LIKE],
            valence=0.5,
            magnitude=0.5,
            timestamp=END,
            conversation_id="talk_1",
        ),
        InteractionEvent(
            actor="ana",
            target="ben",
            action="was kind",
            aspects=[Aspect.TRUST],
            valence=-0.4,
            magnitude=0.5,
            timestamp=END,
            conversation_id="talk_1",
        ),
    ]
    ana, ben = result.after[("ana", "ben")], result.after[("ben", "ana")]
    assert ana.like > result.before[("ana", "ben")].like
    assert ana.trust == result.before[("ana", "ben")].trust
    assert ben.trust < result.before[("ben", "ana")].trust
    assert ana.last_interaction == ben.last_interaction == END


def test_a_conversation_with_nothing_of_note_still_builds_familiarity(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)

    result = outcome(context, Extraction(reflections=[reflection("ana")]), store)

    assert result.events == []
    for key, before in result.before.items():
        after = result.after[key]
        assert after.familiarity == RELATIONSHIPS.familiarity_gain
        assert (after.like, after.trust, after.respect) == (
            before.like,
            before.trust,
            before.respect,
        )
    assert [m.owner for m in result.memories] == ["ana"]


def test_old_feelings_decay_before_the_conversation_counts(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(
        meet(npcs["ana"], "ben").model_copy(
            update={"like": 0.95, "familiarity": 0.5, "last_interaction": START - timedelta(days=4)}
        )
    )
    context = gather(talk(("ana", "Hi.")), npcs, store)

    result = outcome(context, Extraction(reflections=[]), store)

    assert result.before[("ana", "ben")].like < 0.8
    assert result.after[("ana", "ben")].like == result.before[("ana", "ben")].like


def test_reads_relationships_again_after_the_llm(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)
    meanwhile = meet(npcs["ana"], "ben").model_copy(
        update={"like": 0.2, "familiarity": 0.3, "last_interaction": END}
    )
    store.add(meanwhile)

    result = outcome(context, Extraction(reflections=[]), store)

    assert result.before[("ana", "ben")] == meanwhile
    assert result.after[("ana", "ben")].like == 0.2


def test_a_promise_becomes_a_flag_on_its_owners_relationship(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "I'll fix it.")), npcs, store)
    opened = NewFlag(kind=FlagKind.PROMISE, about="ana", description=" fixing Ben's fence ")

    result = outcome(
        context, Extraction(reflections=[reflection("ben", flags_opened=[opened])]), store
    )

    assert result.after[("ben", "ana")].flags == [
        Flag(
            id="talk_1/1",
            kind=FlagKind.PROMISE,
            owner="ben",
            about="ana",
            description="fixing Ben's fence",
            created=END,
        )
    ]
    assert result.after[("ana", "ben")].flags == []


def test_resolves_open_flags_by_ref(npcs: dict[str, Npc], store: MemoryStore, talk: Talk) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "Fixed your fence!")), npcs, store)
    extraction = Extraction(reflections=[reflection("ben", flags_resolved=["f1", "F9"])])

    result = outcome(context, extraction, store)

    [flag] = result.after[("ben", "ana")].flags
    assert flag.id == "fence"
    assert flag.resolved == END


def test_a_broken_promise_is_resolved_and_opened_again(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "I never got round to your fence.")), npcs, store)
    broken = NewFlag(kind=FlagKind.BROKEN_PROMISE, about="ana", description="the fence")
    extraction = Extraction(
        reflections=[reflection("ben", flags_resolved=["F1"], flags_opened=[broken])]
    )

    result = outcome(context, extraction, store)

    flags = result.after[("ben", "ana")].flags
    assert [(f.kind, f.resolved) for f in flags] == [
        (FlagKind.PROMISE, END),
        (FlagKind.BROKEN_PROMISE, None),
    ]


def test_ignores_a_flag_resolved_while_the_llm_was_busy(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "Hi.")), npcs, store)
    earlier = START + timedelta(minutes=1)
    store.add(promise("ben", "ana").model_copy(update={"resolved": earlier}))

    result = outcome(
        context, Extraction(reflections=[reflection("ben", flags_resolved=["F1"])]), store
    )

    assert result.after[("ben", "ana")].flags[0].resolved == earlier


def test_only_a_flags_owner_resolves_it(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "Your fence is done.")), npcs, store)
    extraction = Extraction(reflections=[reflection("ana", flags_resolved=["F1"])])

    result = outcome(context, extraction, store)

    assert result.after[("ben", "ana")].flags[0].resolved is None


def test_drops_what_doesnt_fit_the_conversation(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)
    extraction = Extraction(
        reflections=[
            reflection("cal"),
            reflection(
                "Ana Ferreira",
                events=[deed("ana"), deed("cal"), deed("ben", action="  "), deed("Ben")],
                flags_opened=[
                    NewFlag(kind=FlagKind.DEBT, about="ana", description="a coffee"),
                    NewFlag(kind=FlagKind.DEBT, about="ben", description=" "),
                    NewFlag(kind=FlagKind.DEBT, about="cal", description="a coffee"),
                ],
            ),
            reflection("ana", summary="A second take."),
        ]
    )

    result = outcome(context, extraction, store)

    assert [(e.actor, e.target) for e in result.events] == [("ben", "ana")]
    assert result.after[("ana", "ben")].flags == []
    assert [m.content for m in result.memories] == ["Ana Ferreira chatted."]


def test_keeps_at_most_the_configured_events_and_flags_that_fit(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    config = DEFAULT_CONFIG.model_copy(update={"events": 2, "flags": 1})
    context = gather(talk(("ana", "Hi.")), npcs, store, config)
    flags = [
        NewFlag(kind=FlagKind.SECRET, about="cal", description="a stranger's secret"),
        *(NewFlag(kind=FlagKind.SECRET, about="ben", description=f"secret {n}") for n in range(3)),
    ]
    deeds = [deed("cal"), deed("ana"), *(deed("ben", action=f"deed {n}") for n in range(3))]
    extraction = Extraction(reflections=[reflection("ana", events=deeds, flags_opened=flags)])

    result = outcome(context, extraction, store, config)

    assert [e.action for e in result.events] == ["deed 0", "deed 1"]
    assert [f.description for f in result.after[("ana", "ben")].flags] == ["secret 0"]


def test_several_deeds_move_like_no_further_than_one_full_strength_deed(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ben", "Out of my way.")), npcs, store)

    def snubbed(*deeds: Deed) -> tuple[float, list[InteractionEvent]]:
        result = outcome(context, Extraction(reflections=[reflection("ana", events=deeds)]), store)
        return result.after[("ana", "ben")].like, result.events

    full, _ = snubbed(deed("ben", valence=-1, magnitude=1))
    several, events = snubbed(*[deed("ben", valence=-1, magnitude=0.8)] * 4)

    assert several == pytest.approx(full)
    assert sum(event.magnitude for event in events) == pytest.approx(1)


def test_splitting_a_deed_in_two_changes_nothing(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ben", "Out of my way.")), npcs, store)

    def snubbed(*deeds: Deed) -> float:
        result = outcome(context, Extraction(reflections=[reflection("ana", events=deeds)]), store)
        return result.after[("ana", "ben")].like

    once = snubbed(deed("ben", valence=-0.6, magnitude=0.6))

    assert snubbed(*[deed("ben", valence=-0.6, magnitude=0.3)] * 2) == pytest.approx(once)
    assert once < meet(npcs["ana"], "ben").like


def test_familiarity_grows_once_per_conversation(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)
    extraction = Extraction(reflections=[reflection("ana", events=[deed("ben")] * 4)])

    result = outcome(context, extraction, store)

    assert result.after[("ana", "ben")].familiarity == RELATIONSHIPS.familiarity_gain


def test_each_npc_remembers_the_conversation_in_their_own_words(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "Hi.")), npcs, store)
    extraction = Extraction(
        reflections=[
            reflection(
                "ben",
                summary=" Ana told me about her garden. ",
                valence=0.3,
                salience=0.4,
                topics=["Gardening ", "roses", "gardening", "", "weather", "tea"],
            ),
            reflection("ana", summary=""),
        ]
    )

    [memory] = outcome(context, extraction, store).memories

    assert memory.owner == "ben"
    assert memory.kind == MemoryKind.CONVERSATION
    assert memory.content == "Ana told me about her garden."
    assert (memory.valence, memory.salience) == (0.3, 0.4)
    assert memory.timestamp == END
    assert memory.about == ["ana"]
    assert memory.topics == ["gardening", "roses", "weather"]
    assert memory.conversation_id == "talk_1"


def test_npcs_remember_the_player_who_has_no_feelings_of_their_own(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(
        ("player", "I'll bring you seeds tomorrow."), participants=[PLAYER_ID, "ana"]
    )
    context = gather(conversation, npcs, store)
    extraction = Extraction(
        reflections=[
            reflection(PLAYER_ID),
            reflection(
                "ana",
                events=[deed("Visitor", action="offered Ana seeds")],
                flags_opened=[NewFlag(kind=FlagKind.PROMISE, about="player", description="seeds")],
            ),
        ]
    )

    result = outcome(context, extraction, store)
    store.add(*result.records)

    assert list(result.after) == [("ana", PLAYER_ID)]
    assert [(e.actor, e.target) for e in result.events] == [(PLAYER_ID, "ana")]
    assert [m.owner for m in result.memories] == ["ana"]
    assert result.memories[0].about == [PLAYER_ID]
    assert store.relationship(PLAYER_ID, "ana") is None
    assert store.relationship("ana", PLAYER_ID).flags[0].description == "seeds"
