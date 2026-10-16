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
from simile.conversation.prompt import Player, first_name, takes_leave
from simile.memory import SharedHistory
from simile.npc import load_npcs
from simile.schema import (
    PLAYER_ID,
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
    assert "now and then, not in every line" in prompt
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


def test_the_player_is_a_newcomer_called_visitor() -> None:
    rel = meet(KOFI, PLAYER_ID)
    history = SharedHistory(
        events=[
            InteractionEvent(
                actor=PLAYER_ID,
                target="kofi",
                action="asked about his murals",
                aspects=[Aspect.LIKE],
                valence=0.4,
                magnitude=0.3,
                timestamp=NOW - timedelta(days=1),
            )
        ],
        flags=[],
    )

    text = background(KOFI, Player(), rel, history, [], [], None, NOW)

    assert "You're with Visitor (a newcomer to the village)." in text
    assert describe(rel, "Visitor") in text
    assert "- yesterday, Visitor: asked about his murals" in text
    assert first_name(Player()) == "Visitor"


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
        "Say your next line to Henrietta. Keep the conversation going: don't wrap it up or say "
        "goodbye yet."
    )


def test_a_speaker_sees_how_their_latest_lines_began() -> None:
    said = ["Ha, mostly paint and pavement.", "Ha! Fair enough.", "Go on, then.", "Ha, a wall?"]
    lines = [line(n, "kofi", text) for n, text in enumerate(["Morning, all.", *said], 1)]

    prompt = turn_prompt("B", lines, NAMES, Cue.REPLY, "Henrietta", speaker="kofi")

    assert prompt.endswith(
        'Your lines so far began "Ha, mostly paint...", "Ha! Fair enough...", "Go on, then...", '
        '"Ha, a wall...". Begin this one another way.\n\n'
        "Say your next line to Henrietta. Keep the conversation going: don't wrap it up or say "
        "goodbye yet."
    )
    assert "began" not in turn_prompt("B", lines, NAMES, Cue.REPLY, "Kofi", speaker="henrietta")


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


@pytest.mark.parametrize(
    "text",
    [
        "Quite right. I shall leave you to your porridge and your cones.",
        "Aye, thanks Tobias. Keep your mornings steady, and I'll see you at the riverside.",
        "Right you are, Lachlan. Off you go, and mind the cones. Good morning to you.",
        "Send the rate, and I'll have the calendar ready. Good day to you.",
        "Ha, Wednesday noon, got it! Catch you later, and I'll bring the numbers.",
        "Right, I’d better be off. Take care!",
        "Bye now.",
        "Must dash, the kiln's on.",
        "See you at the quiz!",
        "Right, see you.",
        "See you later, Kofi.",
        "Lovely chat. See you soon!",
        "Anyway, see you around.",
        "The cones go out at six, so see you tomorrow.",
        "I'll see you tomorrow, then.",
        "We'll see you there.",
        "Thanks for the tea. Hope to see you soon.",
        "See ya!",
    ],
)
def test_lines_that_say_goodbye(text: str) -> None:
    assert takes_leave(text)


@pytest.mark.parametrize(
    "text",
    [
        "Good morning, Lachlan. Are the young players keeping you busy?",
        "Rain or shine, the cones are out by six, no excuses.",
        "I'll see you at the riverside on Saturday, then? What time do they start?",
        "I take care of the bins on Tuesdays.",
        "A farewell party for the vicar, of all things. Were you there?",
        "By the way, the bylaw says otherwise.",
        "Frankly, a fixed date concentrates the mind wonderfully.",
        "I said goodbye to my old studio when I moved here, you know.",
        "Good morning to you too, Desmond! What brings you out so early?",
        "Good morning to you too, Desmond.",
        "Will I see you at the quiz tonight?",
        "Did you have a good night at the quiz?",
        "We had a good night at the quiz, mind.",
        "Do take care with that kiln, Ingrid. What are you firing?",
        "Do take care with that kiln, Ingrid.",
        "Lovely to see you again, Kofi.",
        "I see you've brought the dog.",
        "I see you've been reading about Mars.",
        "I see you're busy.",
        "I see you have been busy with the mural.",
        "I see you got the new kit.",
        "I can see you're keen.",
        "Ah, I see you brought the dog along.",
        "I see you around the market most mornings.",
        "If I see you at the quiz, the first round's on me.",
        "I'll see you've got a seat, don't worry.",
        "I'll leave you the keys, then. Anyway, how's the mural?",
        "Bye now, she said, and off he went to the market. Strange man.",
        "Catch you later, I said, but he never came back. Do you know him?",
        "Goodbye to all that, I thought.",
    ],
)
def test_lines_that_dont_say_goodbye(text: str) -> None:
    assert not takes_leave(text)


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
        ("Hi.\n[values: connection, adven", Draft("Hi.", (CoreValue.CONNECTION,))),
        ("Hi there.\n[val", Draft("Hi there.")),
        (
            "Hi.\n\nHenrietta: Oh, hello.\nKofi: How are you?\n[values: connection]",
            Draft("Hi.", (CoreValue.CONNECTION,)),
        ),
        ("Kofi: Hi.\nHenrietta Okonkwo-Bell: Hello, Kofi.", Draft("Hi.")),
        ("I told Henrietta: no.", Draft("I told Henrietta: no.")),
    ],
)
def test_parsing_a_reply(reply: str, draft: Draft) -> None:
    speaker, other = ["Kofi", "Kofi Lindqvist-Mensah"], ["Henrietta", "Henrietta Okonkwo-Bell"]

    assert parse_reply(reply, speaker, other) == draft


def test_a_line_takes_as_long_as_saying_it_at_200_words_a_minute() -> None:
    assert duration(" ".join(["word"] * 15)) == pytest.approx(4.5)
    assert duration("Hi.") == pytest.approx(1.0)
    assert duration("Hi.", ConversationConfig(min_line_seconds=0)) == pytest.approx(0.3)
