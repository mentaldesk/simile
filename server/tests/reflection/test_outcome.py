from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.reflection import DEFAULT_CONFIG, Deed, Extraction, NewFlag, Reflection, gather, outcome
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Conversation,
    CoreValue,
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


def flagged(who: str, kind: FlagKind, whom: str, description: str = "the fence") -> NewFlag:
    return NewFlag(kind=kind, who=who, whom=whom, description=description)


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


def test_a_promise_becomes_a_flag_held_by_whoever_was_promised(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    context = gather(talk(("ana", "I'll fix it.")), npcs, store)
    opened = flagged("Ana", FlagKind.PROMISE, "ben", " fixing Ben's fence ")

    result = outcome(context, Extraction(reflections=[], flags_opened=[opened]), store)

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
    extraction = Extraction(reflections=[], flags_resolved=["f1", "F9"])

    result = outcome(context, extraction, store)

    [flag] = result.after[("ben", "ana")].flags
    assert flag.id == "fence"
    assert flag.resolved == END


def test_a_broken_promise_is_resolved_and_opened_again(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "I never got round to your fence.")), npcs, store)
    broken = flagged("ana", FlagKind.BROKEN_PROMISE, "ben")
    extraction = Extraction(reflections=[], flags_resolved=["F1"], flags_opened=[broken])

    result = outcome(context, extraction, store)

    flags = result.after[("ben", "ana")].flags
    assert [(f.kind, f.resolved) for f in flags] == [
        (FlagKind.PROMISE, END),
        (FlagKind.BROKEN_PROMISE, None),
    ]


SAMPLES = "bringing Kofi paint samples from the old lock gate by Wednesday"
FORGOT = deed(
    "tobias", action="forgot Kofi's samples", aspects=["trust"], valence=-0.3, magnitude=0.3
)
SORRY = deed("tobias", action="apologised to Kofi", aspects=["like"], valence=0.3, magnitude=0.3)
# The second is how Haiku replied in all three of three tries, apology promise and all.
ADMISSIONS = {
    "as Haiku replies": Extraction(
        reflections=[reflection("kofi", events=[SORRY, FORGOT])],
        flags_resolved=["F1"],
        flags_opened=[
            flagged("tobias", FlagKind.BROKEN_PROMISE, "kofi", SAMPLES),
            flagged("tobias", FlagKind.PROMISE, "kofi", "warning Kofi before Wednesday next time"),
        ],
    ),
    "without resolving the promise": Extraction(
        reflections=[reflection("kofi", events=[SORRY, FORGOT])],
        flags_opened=[flagged("tobias", FlagKind.BROKEN_PROMISE, "kofi", SAMPLES)],
    ),
    "without a trust event": Extraction(
        reflections=[reflection("kofi", events=[SORRY])],
        flags_resolved=["F1"],
        flags_opened=[flagged("tobias", FlagKind.BROKEN_PROMISE, "kofi", SAMPLES)],
    ),
}


@pytest.mark.parametrize("admission", ADMISSIONS.values(), ids=ADMISSIONS.keys())
def test_a_promise_tobias_admits_he_broke_costs_him_kofis_trust(
    admission: Extraction, store: MemoryStore, talk: Talk
) -> None:
    residents = {npc.id: npc for npc in load_npcs() if npc.id in ("tobias", "kofi")}
    promised = Extraction(
        reflections=[], flags_opened=[flagged("tobias", FlagKind.PROMISE, "kofi", SAMPLES)]
    )
    first = talk(("tobias", "I'll bring you samples."), participants=["tobias", "kofi"])
    store.add(*outcome(gather(first, residents, store), promised, store).records)
    later = START + timedelta(days=2)
    second = talk(
        ("tobias", "I never fetched your samples."),
        participants=["tobias", "kofi"],
        id="talk_2",
        started=later,
    )

    result = outcome(gather(second, residents, store), admission, store)

    kofi = result.after[("kofi", "tobias")]
    [kept] = [f for f in kofi.flags if f.description == SAMPLES and f.kind == FlagKind.PROMISE]
    [broken] = [f for f in kofi.flags if f.kind == FlagKind.BROKEN_PROMISE]
    assert kept.resolved == later + timedelta(minutes=2)
    assert (broken.description, broken.resolved) == (SAMPLES, None)
    assert kofi.trust < result.before[("kofi", "tobias")].trust


def test_a_kept_promise_is_resolved_and_opens_nothing(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "Your fence is fixed.")), npcs, store)
    thanks = deed("ana", action="fixed Ben's fence", aspects=["trust"], valence=0.7)
    extraction = Extraction(reflections=[reflection("ben", events=[thanks])], flags_resolved=["F1"])

    result = outcome(context, extraction, store)

    ben = result.after[("ben", "ana")]
    assert [(f.kind, f.resolved) for f in ben.flags] == [(FlagKind.PROMISE, END)]
    assert ben.trust > result.before[("ben", "ana")].trust


@pytest.mark.parametrize("resolved", [["F1"], []], ids=["resolved", "not resolved"])
def test_a_promise_kept_and_a_new_one_made_leave_only_the_new_one_open(
    resolved: list[str], npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "Fence done. I'll paint it Sunday.")), npcs, store)
    sunday = flagged("ana", FlagKind.PROMISE, "ben", "painting the fence on Sunday")
    extraction = Extraction(reflections=[], flags_resolved=resolved, flags_opened=[sunday])

    result = outcome(context, extraction, store)

    flags = result.after[("ben", "ana")].flags
    resolved_at = END if resolved else None
    assert [(f.description, f.resolved) for f in flags] == [
        ("fixing the fence", resolved_at),
        ("painting the fence on Sunday", None),
    ]


def test_a_broken_promise_leaves_alone_promises_it_cant_tell_apart(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"), promise("ben", "ana", id="gate"))
    context = gather(talk(("ana", "I never got round to it.")), npcs, store)
    broken = flagged("ana", FlagKind.BROKEN_PROMISE, "ben")

    result = outcome(context, Extraction(reflections=[], flags_opened=[broken]), store)

    flags = result.after[("ben", "ana")].flags
    assert [(f.id, f.resolved) for f in flags] == [
        ("fence", None),
        ("gate", None),
        ("talk_1/1", None),
    ]


def test_ignores_a_flag_resolved_while_the_llm_was_busy(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    store.add(meet(npcs["ben"], "ana"), promise("ben", "ana"))
    context = gather(talk(("ana", "Hi.")), npcs, store)
    earlier = START + timedelta(minutes=1)
    store.add(promise("ben", "ana").model_copy(update={"resolved": earlier}))

    result = outcome(context, Extraction(reflections=[], flags_resolved=["F1"]), store)

    assert result.after[("ben", "ana")].flags[0].resolved == earlier


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
            ),
            reflection("ana", summary="A second take."),
        ],
        flags_opened=[
            flagged("ana", FlagKind.DEBT, "Ana Ferreira", "a coffee"),
            flagged("ben", FlagKind.DEBT, "ana", " "),
            flagged("cal", FlagKind.DEBT, "ana", "a coffee"),
            flagged("ben", FlagKind.DEBT, "cal", "a coffee"),
        ],
    )

    result = outcome(context, extraction, store)

    assert [(e.actor, e.target) for e in result.events] == [("ben", "ana")]
    assert all(rel.flags == [] for rel in result.after.values())
    assert [m.content for m in result.memories] == ["Ana Ferreira chatted."]


def test_keeps_at_most_the_configured_events_and_flags_that_fit(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    config = DEFAULT_CONFIG.model_copy(update={"events": 2, "flags": 1})
    context = gather(talk(("ana", "Hi.")), npcs, store, config)
    flags = [
        flagged("cal", FlagKind.SECRET, "ana", "a stranger's secret"),
        *(flagged("ben", FlagKind.SECRET, "ana", f"Ben's secret {n}") for n in range(3)),
        flagged("ana", FlagKind.SECRET, "ben", "Ana's secret"),
    ]
    deeds = [deed("cal"), deed("ana"), *(deed("ben", action=f"deed {n}") for n in range(3))]
    extraction = Extraction(reflections=[reflection("ana", events=deeds)], flags_opened=flags)

    result = outcome(context, extraction, store, config)

    assert [e.action for e in result.events] == ["deed 0", "deed 1"]
    assert [f.description for f in result.after[("ana", "ben")].flags] == ["Ben's secret 0"]
    assert [f.description for f in result.after[("ben", "ana")].flags] == ["Ana's secret"]


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


# Like D2's warm soak conversations: magnitudes past B3's cap and the odd small negative.
GOOD_CONVERSATIONS = {
    "four deeds": [
        deed("ben", aspects=["like", "respect"], magnitude=0.8, valence=0.6),
        deed("ben", aspects=["respect", "like"], magnitude=0.6, valence=0.7),
        deed("ben", aspects=["trust", "like"], magnitude=0.4, valence=0.4),
        deed("ben", aspects=["like"], magnitude=0.2, valence=-0.2),
    ],
    "two deeds": [
        deed("ben", aspects=["like", "respect"], magnitude=0.9, valence=0.6),
        deed("ben", aspects=["like"], magnitude=0.6, valence=0.3),
    ],
}


@pytest.mark.parametrize("deeds", GOOD_CONVERSATIONS.values(), ids=GOOD_CONVERSATIONS.keys())
def test_1_11_and_111_good_conversations_take_like_to_0_65_0_8_and_0_95(
    deeds: list[Deed], npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    neutral = {
        id: npc.model_copy(update={"values": dict.fromkeys(CoreValue, 0.5)})
        for id, npc in npcs.items()
    }
    likes = []
    for n in range(111):
        context = gather(talk(("ben", "Lovely roses."), id=f"talk_{n}"), neutral, store)
        result = outcome(context, Extraction(reflections=[reflection("ana", events=deeds)]), store)
        store.add(*result.records)
        likes.append(result.after[("ana", "ben")].like)

    assert likes[0] == pytest.approx(0.65, abs=0.02)
    assert likes[10] == pytest.approx(0.8, abs=0.02)
    assert likes[110] == pytest.approx(0.95, abs=0.02)


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
            reflection("ana", events=[deed("Visitor", action="offered Ana seeds")]),
        ],
        flags_opened=[flagged("Visitor", FlagKind.PROMISE, "ana", "seeds")],
    )

    result = outcome(context, extraction, store)
    store.add(*result.records)

    assert list(result.after) == [("ana", PLAYER_ID)]
    assert [(e.actor, e.target) for e in result.events] == [(PLAYER_ID, "ana")]
    assert [m.owner for m in result.memories] == ["ana"]
    assert result.memories[0].about == [PLAYER_ID]
    assert store.relationship(PLAYER_ID, "ana") is None
    assert store.relationship("ana", PLAYER_ID).flags[0].description == "seeds"


def test_flags_the_player_would_hold_are_dropped(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ana", "I'll bring you seeds."), participants=[PLAYER_ID, "ana"])
    context = gather(conversation, npcs, store)
    extraction = Extraction(
        reflections=[],
        flags_opened=[
            flagged("ana", FlagKind.PROMISE, PLAYER_ID, "seeds"),
            flagged("ana", FlagKind.SECRET, "Visitor", "her debts"),
            flagged(PLAYER_ID, FlagKind.GRUDGE, "ana", "the seeds"),
            flagged("ana", FlagKind.GRUDGE, PLAYER_ID, "being pestered"),
        ],
    )

    result = outcome(context, extraction, store)

    [flag] = result.after[("ana", PLAYER_ID)].flags
    assert (flag.kind, flag.description) == (FlagKind.GRUDGE, "being pestered")
    assert list(result.after) == [("ana", PLAYER_ID)]
