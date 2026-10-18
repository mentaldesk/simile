from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import IntentionBroken, IntentionKept, Options
from simile.llm import FakeProvider, LLMClient, Request
from simile.memory import MemoryStore
from simile.reflection import DEFAULT_CONFIG, Extraction, Intent, Reflection, Reflector, gather
from simile.reflection.extraction import prompt
from simile.reflection.intentions import broken, due, intentions, kept
from simile.schema import (
    PLAYER_ID,
    Conversation,
    Craft,
    Flag,
    FlagKind,
    Intention,
    IntentionKind,
    Medium,
    MemoryKind,
    Npc,
)
from simile.social import meet, open_flag

from .conftest import make_npc

Talk = Callable[..., Conversation]

END = datetime(2026, 1, 1, 9, 2, tzinfo=UTC)
COFFEE = "a mural of an ocean of coffee with cups half-sunk in it"
PLACES = {"house_6": "home", "coffee_shop": "The Daily Grind", "park": "Lotus Lake Park"}
TERMINALS = {"terminal_1": "News terminal on the square"}
KOFI = make_npc("kofi", "Kofi Mensah").model_copy(
    update={"craft": Craft(medium=Medium.MURAL, form="big murals")}
)
MURALIST = Options(
    "house_6", PLACES, TERMINALS, Medium.MURAL, {"banyan_row": "the banyan row wall"}
)
NO_CRAFT = Options("house_1", PLACES, TERMINALS, None, {})
PAINT_IT = (
    ("player", "That sounds amazing. Will you paint it?"),
    ("kofi", "I'll go and paint it now, on the Banyan Row wall. Come and watch!"),
    ("player", "Yes! See you there."),
)


@pytest.fixture
def cast(npcs: dict[str, Npc]) -> dict[str, Npc]:
    return {**npcs, KOFI.id: KOFI}


def options(npc: str) -> Options | None:
    return MURALIST if npc == "kofi" else NO_CRAFT


def intent(**fields: object) -> Intent:
    return Intent.model_validate(
        {"who": "kofi", "kind": "create", "description": COFFEE, "when": "now", **fields}
    )


def extract(*found: Intent) -> Extraction:
    return Extraction(reflections=[], intentions=list(found))


@pytest.mark.anyio
async def test_ill_go_and_paint_it_now_is_an_intention_to_make_it_due_now(
    cast: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    said: list[Intention] = []

    def reply(request: Request) -> str:
        return Extraction(
            reflections=[
                Reflection(
                    npc="kofi",
                    summary="I told Visitor I'd paint the coffee ocean now.",
                    valence=0.7,
                    salience=0.8,
                )
            ],
            intentions=[
                intent(target="banyan_row", promised_to=["Visitor"]),
                intent(kind="go", target="Paris", description="move to Paris one day"),
            ],
        ).model_dump_json()

    llm = LLMClient(FakeProvider([reply]))
    reflector = Reflector(
        store,
        lambda: cast,
        lambda: llm,
        options=options,
        intend=lambda intention: said.append(intention) or True,
    )

    result = await reflector.reflect(llm, talk(*PAINT_IT, participants=["player", "kofi"]))

    expected = Intention(
        id="talk_1/kofi/1",
        owner="kofi",
        kind=IntentionKind.CREATE,
        target="banyan_row",
        description=COFFEE,
        promised_to=[PLAYER_ID],
        created=END,
        due=END,
        expires=END + DEFAULT_CONFIG.expire_now,
        conversation_id="talk_1",
    )
    assert said == [expected]
    assert result is not None and result.intentions == [expected]


def test_the_prompt_says_what_each_can_do_and_has_already_planned(
    cast: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    planned = Intention(
        id="old/kofi/1",
        owner="kofi",
        kind=IntentionKind.GO,
        target="park",
        description="sketch the lake",
        created=END - timedelta(hours=1),
        due=END + timedelta(hours=3),
        expires=END + timedelta(hours=27),
    )
    conversation = talk(*PAINT_IT, participants=["player", "kofi"])

    context = gather(
        conversation, cast, store, options={"kofi": MURALIST}, planned={"kofi": [planned]}
    )
    text = prompt(context)

    assert text.startswith("It's Thursday 09:02.")
    assert (
        "Can do: go to house_6 (home), coffee_shop (The Daily Grind), park (Lotus Lake Park); news "
        "at terminal_1; seek anyone here or in the village, or the visitor (player); create "
        "(paint) at banyan_row (the banyan row wall)." in text
    )
    assert "Already planned: go park (today 12:02): sketch the lake." in text
    assert "Others in the village they could look up: ana (Ana Ferreira), ben (Ben Okafor)." in text


def test_vague_impossible_and_unfounded_plans_are_dropped(
    cast: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ana", "Hi."), participants=["ana", "kofi", PLAYER_ID])
    context = gather(conversation, cast, store, options={"ana": NO_CRAFT, "kofi": MURALIST})
    wanted = extract(
        intent(kind="go", target="Paris", description="go to Paris"),
        intent(when="one day"),
        intent(when="some time next week"),
        intent(kind="cook", description="cook dinner"),
        intent(who="player", kind="go", target="park", description="walk"),
        intent(who="ana", description="paint something"),
        intent(kind="seek", target="kofi", description="find myself"),
        intent(kind="seek", target="zed", description="find Zed"),
        intent(kind="go", target="park", description="  ", when="now"),
        intent(kind="go", target="park", description="late swim", when="tomorrow 23:00"),
    )

    assert intentions(context, wanted) == []


def test_targets_resolve_by_id_or_name_and_unknown_places_to_make_it_go_unnamed(
    cast: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ana", "Hi."), participants=["ana", "kofi"])
    context = gather(conversation, cast, store, options={"ana": NO_CRAFT, "kofi": MURALIST})

    found = intentions(
        context,
        extract(
            intent(who="Ana", kind="go", target="The Daily Grind", description="get a coffee"),
            intent(who="ana", kind="seek", target="Ben", description="tell Ben", when="15:30"),
            intent(target="the noodle bar wall", promised_to=["ana", "kofi", "nobody"]),
            intent(kind="news", target=None, description="read up", when="tomorrow 09:00"),
            intent(kind="seek", target="ana", description="one too many"),
        ),
    )

    assert [(i.owner, i.kind, i.target) for i in found] == [
        ("ana", IntentionKind.GO, "coffee_shop"),
        ("ana", IntentionKind.SEEK, "ben"),
        ("kofi", IntentionKind.CREATE, None),
        ("kofi", IntentionKind.NEWS, None),
    ]
    assert found[1].due == END.replace(hour=15, minute=30)
    assert found[1].expires == found[1].due + DEFAULT_CONFIG.expire_later
    assert found[2].promised_to == ["ana"]
    assert found[3].due == datetime(2026, 1, 2, 9, tzinfo=UTC)
    assert len({i.id for i in found}) == 4


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        ("now", END),
        ("Now", END),
        ("today 15:00", END.replace(hour=15, minute=0)),
        ("today 08:00", END),
        ("08:00", datetime(2026, 1, 2, 8, tzinfo=UTC)),
        ("tomorrow 9.30", datetime(2026, 1, 2, 9, 30, tzinfo=UTC)),
        ("tomorrow at 21:00", datetime(2026, 1, 2, 21, tzinfo=UTC)),
        ("tomorrow 22:00", None),
        ("later", None),
        ("25:00", None),
    ],
)
def test_when_they_said(when: str, expected: datetime | None) -> None:
    assert due(when, END) == expected


def broken_to(*promised: str, conversation: str | None = "talk_1") -> Intention:
    return Intention(
        id="talk_1/kofi/1",
        owner="kofi",
        kind=IntentionKind.CREATE,
        description=COFFEE,
        promised_to=list(promised),
        created=END - timedelta(hours=2),
        due=END - timedelta(hours=2),
        expires=END,
        conversation_id=conversation,
    )


def test_a_broken_promise_is_remembered_by_both_and_costs_trust(
    cast: dict[str, Npc], store: MemoryStore
) -> None:
    promise = Flag(
        id="talk_1/1",
        kind=FlagKind.PROMISE,
        owner="ana",
        about="kofi",
        description="painting the mural",
        created=END - timedelta(hours=2),
    )
    store.add(open_flag(meet(cast["ana"], "kofi"), promise))
    before = store.relationship("ana", "kofi")
    assert before is not None

    store.add(*broken(broken_to("ana", PLAYER_ID), cast, store, END))

    [mine] = store.recall("kofi", END)
    assert mine.content == f"I told Ana, Visitor I'd make {COFFEE}, and didn't."
    assert mine.kind is MemoryKind.OBSERVATION and mine.about == ["ana", PLAYER_ID]
    [theirs] = store.recall("ana", END, about="kofi")
    assert theirs.content == f"Kofi told me they'd make {COFFEE}, and didn't."
    [visitor] = store.recall(PLAYER_ID, END)
    assert visitor.about == ["kofi", "ana"]
    after = store.relationship("ana", "kofi")
    assert after is not None
    assert after.trust < before.trust
    assert after.familiarity == before.familiarity
    flags = {flag.kind: flag for flag in after.flags}
    assert flags[FlagKind.PROMISE].resolved == END
    assert flags[FlagKind.BROKEN_PROMISE].description == f"make {COFFEE}"
    [event] = store.shared_history("ana", "kofi", END).events
    assert event.action == f"broke a promise: make {COFFEE}"


def test_an_intention_promised_to_nobody_leaves_nothing_when_it_expires(
    cast: dict[str, Npc], store: MemoryStore
) -> None:
    assert broken(broken_to(), cast, store, END) == []


def test_a_kept_promise_resolves_the_promise_from_its_conversation(
    cast: dict[str, Npc], store: MemoryStore
) -> None:
    flags = [
        Flag(
            id=f"{conversation}/1",
            kind=FlagKind.PROMISE,
            owner="ana",
            about="kofi",
            description="painting it",
            created=END - timedelta(hours=1),
        )
        for conversation in ("talk_1", "talk_0")
    ]
    rel = meet(cast["ana"], "kofi")
    for flag in flags:
        rel = open_flag(rel, flag)
    store.add(rel)

    store.add(*kept(broken_to("ana", PLAYER_ID), cast, store, END))

    after = store.relationship("ana", "kofi")
    assert after is not None
    assert {flag.id: flag.resolved for flag in after.flags} == {"talk_1/1": END, "talk_0/1": None}
    assert kept(broken_to("ana", conversation=None), cast, store, END) == []


def test_the_reflector_records_what_became_of_a_promise(
    cast: dict[str, Npc], store: MemoryStore
) -> None:
    reflector = Reflector(store, lambda: cast, lambda: None)

    reflector.on_kept(IntentionKept(broken_to("ana")))
    reflector.on_broken(IntentionBroken(broken_to("ana")))

    assert [m.owner for m in store.recall("ana", END)] == ["ana"]
    assert len(store.recall("kofi", END)) == 1
