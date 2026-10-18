from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from simile.memory import MemoryStore
from simile.reflection import DEFAULT_CONFIG, Extraction, gather, prompt
from simile.reflection.extraction import WHAT
from simile.schema import PLAYER_ID, Conversation, Flag, FlagKind, Npc
from simile.social import meet

Talk = Callable[..., Conversation]

START = datetime(2026, 1, 1, 9, tzinfo=UTC)


def test_the_prompt_says_who_reflects_and_what_they_care_about(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ana", "Morning, Ben!"), ("ben", "Morning."))

    text = prompt(gather(conversation, npcs, store))

    assert "ana (Ana Ferreira, " in text
    assert "ben (Ben Okafor, " in text
    assert npcs["ana"].persona in text
    assert "Cares most about: compassion 0.90, honesty 0.80" in text
    assert "Cares least about: ambition 0.10" in text
    assert "Cares most about: tradition 0.90, obedience 0.80" in text
    assert "Cares least about: creativity 0.20" in text
    assert text.endswith("The conversation:\nAna: Morning, Ben!\nBen: Morning.")


def test_the_prompt_gives_feelings_going_in_decayed_to_the_end(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    fond = meet(npcs["ana"], "ben").model_copy(
        update={"like": 0.9, "familiarity": 0.5, "last_interaction": START - timedelta(days=2)}
    )
    store.add(fond)

    context = gather(talk(("ana", "Hi."), started=START), npcs, store)

    going_in = context.feelings[("ana", "ben")]
    assert going_in.like < 0.9
    assert f"Going in, about Ben: like {going_in.like:.2f}, " in prompt(context)
    assert context.feelings[("ben", "ana")].familiarity == 0


def test_the_prompt_lists_open_flags_by_ref_as_who_did_what_to_whom(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    def flag(
        id: str, kind: FlagKind, owner: str, about: str, resolved: datetime | None = None
    ) -> Flag:
        return Flag(
            id=id,
            kind=kind,
            owner=owner,
            about=about,
            description=id,
            created=START - timedelta(days=1),
            resolved=resolved,
        )

    fence = flag("the fence", FlagKind.PROMISE, "ben", "ana")
    hedge = flag("the hedge", FlagKind.GRUDGE, "ana", "ben")
    store.add(
        meet(npcs["ben"], "ana"),
        meet(npcs["ana"], "ben"),
        flag("the gate", FlagKind.PROMISE, "ben", "ana", START),
        fence,
        hedge,
    )

    context = gather(talk(("ana", "Hi.")), npcs, store)

    assert context.flags == {"F1": hedge, "F2": fence}
    assert (
        "Open flags between them:\n"
        "- F1 (grudge): ana holds a grudge against ben: the hedge\n"
        "- F2 (promise): ana promised ben: the fence\n\n"
        "The conversation:"
    ) in prompt(context)


def test_the_player_is_named_but_doesnt_reflect(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(
        ("player", "Hello there."), ("ana", "Welcome!"), participants=[PLAYER_ID, "ana"]
    )

    context = gather(conversation, npcs, store)
    text = prompt(context)

    assert list(context.npcs) == ["ana"]
    assert list(context.feelings) == [("ana", PLAYER_ID)]
    assert f"- {PLAYER_ID} ({DEFAULT_CONFIG.player_name})" in text
    assert f"{DEFAULT_CONFIG.player_name}: Hello there.\nAna: Welcome!" in text
    assert "Going in, about Visitor:" in text


def test_long_transcripts_keep_their_latest_lines(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    config = DEFAULT_CONFIG.model_copy(update={"transcript_lines": 2})
    conversation = talk(("ana", "One."), ("ben", "Two."), ("ana", "Three."))

    text = prompt(gather(conversation, npcs, store, config), config)

    assert text.endswith("The conversation:\n...\nBen: Two.\nAna: Three.")


def test_names_resolve_to_participants(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    conversation = talk(("ana", "Hi."), participants=["ana", "ben", PLAYER_ID])

    context = gather(conversation, npcs, store)

    assert context.who("ben") == "ben"
    assert context.who(" Ben ") == "ben"
    assert context.who("Ana Ferreira") == "ana"
    assert context.who("visitor") == PLAYER_ID
    assert context.who("cal") is None


def test_the_schema_asks_for_each_part_of_a_reflection() -> None:
    schema = Extraction.model_json_schema()

    assert list(schema["properties"]) == ["reflections", "flags_opened", "flags_resolved", "loans"]
    assert list(schema["$defs"]["Reflection"]["properties"]) == [
        "npc",
        "summary",
        "valence",
        "salience",
        "topics",
        "events",
    ]
    assert list(schema["$defs"]["NewFlag"]["properties"]) == ["kind", "who", "whom", "description"]
    assert list(schema["$defs"]["Lending"]["properties"]) == ["lender", "borrower", "amount"]


def test_the_schema_says_who_did_what_to_whom_for_every_kind_of_flag() -> None:
    kind = Extraction.model_json_schema()["$defs"]["NewFlag"]["properties"]["kind"]

    assert kind["description"] == (
        "What `who` did to `whom`: debt, `who` owes `whom`; grudge, `who` holds a grudge against "
        "`whom`; promise, `who` promised `whom`; broken_promise, `who` broke a promise to `whom`; "
        "saved_life, `who` saved the life of `whom`; secret, `who` told `whom` a secret."
    )
    assert list(WHAT) == list(FlagKind)
