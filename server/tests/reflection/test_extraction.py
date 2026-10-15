from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from simile.memory import MemoryStore
from simile.reflection import DEFAULT_CONFIG, Extraction, gather, prompt
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


def test_the_prompt_lists_open_flags_under_their_owner_by_ref(
    npcs: dict[str, Npc], store: MemoryStore, talk: Talk
) -> None:
    def flag(id: str, resolved: datetime | None = None) -> Flag:
        return Flag(
            id=id,
            kind=FlagKind.PROMISE,
            owner="ben",
            about="ana",
            description=f"promise {id}",
            created=START - timedelta(days=1),
            resolved=resolved,
        )

    store.add(meet(npcs["ben"], "ana"), flag("kept", START), flag("fence"))

    context = gather(talk(("ana", "Hi.")), npcs, store)

    assert context.flags == {"F1": flag("fence")}
    ben = prompt(context).split("\n\nben (")[1]
    assert "Open flags:\n- F1 (promise about ana): promise fence" in ben


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
    reflection = Extraction.model_json_schema()["$defs"]["Reflection"]["properties"]

    assert list(reflection) == [
        "npc",
        "summary",
        "valence",
        "salience",
        "topics",
        "events",
        "flags_opened",
        "flags_resolved",
    ]
