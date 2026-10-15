from datetime import UTC, datetime, timedelta

import pytest

from simile.conversation import (
    ConversationConfig,
    Cue,
    Draft,
    background,
    duration,
    parse_reply,
    system_prompt,
    turn_prompt,
)
from simile.memory import SharedHistory
from simile.npc import load_npcs
from simile.schema import (
    Aspect,
    CoreValue,
    Flag,
    FlagKind,
    InteractionEvent,
    Line,
    Memory,
    MemoryKind,
)
from simile.social import describe, meet

NPCS = {npc.id: npc for npc in load_npcs()}
KOFI, HENRIETTA = NPCS["kofi"], NPCS["henrietta"]
NOW = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)


def memory(owner: str, content: str, kind: MemoryKind = MemoryKind.CONVERSATION) -> Memory:
    return Memory(owner=owner, kind=kind, content=content, salience=0.8, valence=0.2, timestamp=NOW)


def test_the_system_prompt_is_the_speakers_persona_values_and_style() -> None:
    prompt = system_prompt(KOFI, ConversationConfig(max_words=30))

    assert KOFI.name in prompt
    assert KOFI.persona in prompt
    assert KOFI.backstory in prompt
    assert f"How you speak: {KOFI.speaking_style}" in prompt
    assert "care about most: open mindedness, adventure, creativity" in prompt
    assert "care about least: discipline, security, obedience." in prompt
    assert "at most 30 words" in prompt
    assert "[values: honesty, ambition]" in prompt
    assert "peace of mind" in prompt


def test_the_background_has_the_relationship_history_memories_and_news() -> None:
    rel = meet(KOFI, "henrietta").model_copy(update={"like": 0.1, "familiarity": 0.5})
    history = SharedHistory(
        events=[
            InteractionEvent(
                actor="henrietta",
                target="kofi",
                action="reported his mural to the council",
                aspects=[Aspect.LIKE],
                valence=-0.7,
                magnitude=0.6,
                timestamp=NOW - timedelta(days=3),
            ),
            InteractionEvent(
                actor="kofi",
                target="henrietta",
                action="carried her shopping home",
                aspects=[Aspect.LIKE],
                valence=0.5,
                magnitude=0.3,
                timestamp=NOW - timedelta(hours=2),
            ),
        ],
        flags=[
            Flag(
                id="f1",
                kind=FlagKind.DEBT,
                owner="henrietta",
                about="kofi",
                description="a broken window.",
                created=NOW - timedelta(days=3),
            ),
            Flag(
                id="f2",
                kind=FlagKind.GRUDGE,
                owner="kofi",
                about="henrietta",
                description="the mural",
                created=NOW - timedelta(days=3),
            ),
        ],
    )
    text = background(
        KOFI,
        HENRIETTA,
        rel,
        history,
        [memory("kofi", "Odalys fed half the square on Sunday.")],
        [memory("kofi", "Read about a city that paints its bridges.", MemoryKind.NEWS)],
        "The Daily Grind",
        NOW,
    )

    assert "It's 09:30, at The Daily Grind." in text
    assert f"Henrietta ({HENRIETTA.name}, aged 71, {HENRIETTA.occupation})" in text
    assert describe(rel, "Henrietta") in text
    assert "- 3 days ago, Henrietta: reported his mural to the council" in text
    assert "- 2 hours ago, you: carried her shopping home" in text
    assert "You still owe Henrietta for a broken window." in text
    assert "grudge" not in text
    assert "On your mind:\n- Odalys fed half the square on Sunday." in text
    assert "News you might bring up:\n- Read about a city that paints its bridges." in text


def test_the_background_leaves_out_what_there_isnt() -> None:
    text = background(
        KOFI, HENRIETTA, meet(KOFI, "henrietta"), SharedHistory([], []), [], [], None, NOW
    )

    assert "out in the street" in text
    assert "Between you" not in text
    assert "On your mind" not in text
    assert "News" not in text


def line(n: int, speaker: str, text: str) -> Line:
    return Line(id=n, conversation_id="c", speaker=speaker, text=text, timestamp=NOW, duration=1.0)


NAMES = {"kofi": "Kofi", "henrietta": "Henrietta"}


def test_a_turn_is_the_background_the_transcript_and_the_cue() -> None:
    lines = [line(1, "kofi", "Morning!"), line(2, "henrietta", "Hm. Morning.")]

    prompt = turn_prompt("BACKGROUND", lines, NAMES, Cue.REPLY, "Henrietta")

    assert prompt == (
        "BACKGROUND\n\n"
        "The conversation so far:\nKofi: Morning!\nHenrietta: Hm. Morning.\n\n"
        "Say your next line to Henrietta."
    )


def test_a_long_transcript_keeps_the_latest_lines() -> None:
    lines = [line(n, "kofi" if n % 2 else "henrietta", f"Line {n}.") for n in range(1, 21)]

    prompt = turn_prompt(
        "B", lines, NAMES, Cue.REPLY, "Kofi", ConversationConfig(transcript_lines=3)
    )

    assert "so far:\n...\nHenrietta: Line 18.\nKofi: Line 19.\nHenrietta: Line 20." in prompt


@pytest.mark.parametrize(
    ("cue", "expected"),
    [
        (Cue.OPEN, "You've just walked up to Henrietta."),
        (Cue.GOODBYE, "goodbye to Henrietta."),
        (Cue.FAREWELL, "Henrietta is leaving. Say a brief goodbye back."),
    ],
)
def test_cues(cue: Cue, expected: str) -> None:
    assert expected in turn_prompt("B", [], NAMES, cue, "Henrietta")


def test_the_first_turn_has_no_transcript() -> None:
    assert "The conversation hasn't started yet." in turn_prompt("B", [], NAMES, Cue.OPEN, "Ben")


@pytest.mark.parametrize(
    ("reply", "draft"),
    [
        (
            "Rules are there for a reason, Kofi.\n[values: obedience, Tradition]",
            Draft(
                "Rules are there for a reason, Kofi.", (CoreValue.OBEDIENCE, CoreValue.TRADITION)
            ),
        ),
        (
            "Honestly? It's brilliant.\n[values: open-mindedness, peace of mind, nonsense]",
            Draft(
                "Honestly? It's brilliant.",
                (CoreValue.OPEN_MINDEDNESS, CoreValue.PEACE_OF_MIND),
            ),
        ),
        ("Kofi: *grins* Morning!\nValues: adventure", Draft("Morning!", (CoreValue.ADVENTURE,))),
        ('"Well, I never."', Draft("Well, I never.")),
        ("Kofi Lindqvist-Mensah: Hi\nthere.", Draft("Hi there.")),
        (
            "Fine. [values: honesty] Truly. [values: justice]",
            Draft("Fine. Truly.", (CoreValue.JUSTICE,)),
        ),
        ("[values: honesty]", Draft("", (CoreValue.HONESTY,))),
    ],
)
def test_parsing_a_reply(reply: str, draft: Draft) -> None:
    assert parse_reply(reply, ["Kofi", "Kofi Lindqvist-Mensah"]) == draft


def test_a_line_takes_as_long_as_saying_it_at_150_words_a_minute() -> None:
    assert duration(" ".join(["word"] * 15)) == pytest.approx(6.0)
    assert duration("Hi.") == pytest.approx(1.0)
    assert duration("Hi.", ConversationConfig(min_line_seconds=0)) == pytest.approx(0.4)
