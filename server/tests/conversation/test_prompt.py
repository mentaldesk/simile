import re
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
from simile.conversation.prompt import (
    Player,
    WorkTopic,
    detailed,
    first_name,
    jokes,
    rough_edges,
    takes_leave,
)
from simile.memory import SharedHistory
from simile.npc import load_npcs
from simile.schema import (
    PLAYER_ID,
    Aspect,
    CoreValue,
    Flag,
    FlagKind,
    Humour,
    HumourStyle,
    InteractionEvent,
    Line,
    Medium,
    Memory,
    MemoryKind,
    Npc,
)
from simile.social import describe, meet
from simile.voice import SpeakingRate

from .conftest import remembers, work

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


def test_the_system_prompt_lists_their_mannerisms_as_verbal_habits() -> None:
    habits = ["answers a question with another question", "teases the people they like most"]

    prompt = system_prompt(KOFI.model_copy(update={"mannerisms": habits}))

    assert (
        f"How you speak: {KOFI.speaking_style}\n"
        f"Your verbal habits: {habits[0]}; {habits[1]}. Use these now and then, not in every line, "
        "and the same goes for your pet words and phrases."
    ) in prompt


def test_without_mannerisms_the_system_prompt_has_only_the_style() -> None:
    prompt = system_prompt(KOFI.model_copy(update={"mannerisms": []}))

    assert "verbal habits" not in prompt
    assert (
        f"How you speak: {KOFI.speaking_style} Use your pet words and phrases now and then, not in "
        "every line."
    ) in prompt


def test_the_system_prompt_gives_their_humour_with_its_guard_and_bounds() -> None:
    humour = Humour(style=HumourStyle.DEADPAN, seriousness=0.7)

    prompt = system_prompt(KOFI.model_copy(update={"humour": humour, "mannerisms": []}))

    assert (
        f"How you speak: {KOFI.speaking_style} Use your pet words and phrases now and then, not in "
        "every line.\n"
        "Your humour is deadpan: absurd or ironic remarks made with a perfectly straight face. You "
        "joke now and then, never in every line. Your jokes are never cruel and never punch down, "
        "and any sarcasm stays dry, never insulting.\n\n"
    ) in prompt


def test_someone_with_no_humour_is_told_to_say_what_they_mean() -> None:
    none = Humour(style=HumourStyle.NONE, seriousness=1)

    prompt = system_prompt(KOFI.model_copy(update={"humour": none}))

    assert "\nYou are not one for jokes: you say what you mean.\n\n" in prompt
    assert "Your jokes" not in prompt


def test_without_a_humour_the_system_prompt_doesnt_mention_one() -> None:
    prompt = system_prompt(KOFI.model_copy(update={"humour": None}))

    assert "humour" not in prompt and "joke" not in prompt


def test_the_system_prompt_keeps_the_resident_within_what_they_would_know() -> None:
    prompt = system_prompt(KOFI)

    assert "what someone with your life and job would know" in prompt
    assert "admit you don't know, or give your own angle rather than expert advice" in prompt
    assert "a chat between neighbours, not a consultation" in prompt
    assert "If they want to change the subject, go with it" in prompt
    assert "say once that you'd rather not and let it go" in prompt


def valuing(**scores: float) -> Npc:
    """Kofi caring 0.5 about everything but `scores`."""
    values = dict.fromkeys(CoreValue, 0.5) | {CoreValue(k): v for k, v in scores.items()}
    return KOFI.model_copy(update={"values": values})


COUNTERWEIGHT = (
    "Don't agree just to be pleasant. Saying no, being brief, or disagreeing is fine when it's in "
    "character."
)
BOUNDS = (
    "Keep to the game's tone: no slurs, abuse or cruelty, and rudeness means curtness, never "
    "insults. Any lie stays small and in character: about yourself, your reasons, plans or what "
    "you did or saw. Never make up facts about the village, its places, times or people."
)


def test_nobody_gets_direction_without_a_low_score() -> None:
    npc = valuing(honesty=0.4, compassion=0.4, peace_of_mind=0.4, self_respect=1.0)

    assert rough_edges(npc) == []
    assert f"\n\n{COUNTERWEIGHT} {BOUNDS}\n\n" in system_prompt(npc)


@pytest.mark.parametrize(
    ("value", "score", "expected"),
    [
        (
            "honesty",
            0.39,
            "You will shade the truth when it suits you, and won't always say everything you know.",
        ),
        (
            "honesty",
            0.2,
            "You will lie when it suits you: white lies, convenient excuses, keeping back what "
            "you'd rather not say.",
        ),
        (
            "honesty",
            0.1,
            "You will lie easily, without guilt, whenever it suits you: white lies, convenient "
            "excuses, keeping back whatever you'd rather not say.",
        ),
        ("compassion", 0.3, "You won't go out of your way to soften bad news."),
        (
            "compassion",
            0.2,
            "You won't soften bad news, will be short with complaints, and will put your own "
            "interests first.",
        ),
        (
            "compassion",
            0.0,
            "You won't soften anything, will have no patience for complaints, and will put your "
            "own interests first every time.",
        ),
        ("peace_of_mind", 0.3, "You will say so when you disagree."),
        (
            "peace_of_mind",
            0.2,
            "You will disagree openly and won't give ground just to keep the peace.",
        ),
        (
            "peace_of_mind",
            0.1,
            "You will disagree bluntly, won't concede anything to keep the peace, and can be curt "
            "or change the subject.",
        ),
    ],
)
def test_a_low_score_gives_direction_that_grows_as_it_falls(
    value: str, score: float, expected: str
) -> None:
    npc = valuing(**{value: score})

    assert rough_edges(npc) == [expected]
    assert f"\n\n{expected} {COUNTERWEIGHT} {BOUNDS}\n\n" in system_prompt(npc)


@pytest.mark.parametrize(
    ("compassion", "self_respect", "expected"),
    [
        (0.3, 0.6, "You can turn down a favour without feeling bad about it."),
        (0.2, 0.9, "You will turn down favours and say no without apologising."),
        (0.1, 0.9, "You will turn down most favours and say no without apologising."),
        (0.1, 0.59, None),
        (0.4, 1.0, None),
    ],
)
def test_high_self_respect_with_low_compassion_says_no(
    compassion: float, self_respect: float, expected: str | None
) -> None:
    edges = rough_edges(valuing(compassion=compassion, self_respect=self_respect))

    assert [edge for edge in edges if "favour" in edge] == ([expected] if expected else [])


def test_about_them_the_direction_names_them() -> None:
    npc = valuing(honesty=0.3, compassion=0.3, peace_of_mind=0.3, self_respect=0.7)

    assert rough_edges(npc, "Kofi") == [
        "Kofi will shade the truth when it suits them, and won't always say everything they know.",
        "Kofi won't go out of their way to soften bad news.",
        "Kofi will say so when they disagree.",
        "Kofi can turn down a favour without feeling bad about it.",
    ]


@pytest.mark.parametrize("npc", NPCS.values(), ids=NPCS.keys())
def test_every_residents_prompt_has_the_counterweight_and_the_bounds(npc: Npc) -> None:
    prompt = system_prompt(npc)

    assert prompt.count(COUNTERWEIGHT) == 1
    assert prompt.count(BOUNDS) == 1


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
        "Say one or two sentences, at most 40 words.\n\n"
        "Say your next line to Henrietta. Keep the conversation going: don't wrap it up or say "
        "goodbye yet."
    )


@pytest.mark.parametrize(
    ("joke", "direction"),
    [
        (True, "Work a joke into this line, in your own humour."),
        (False, "No joke in this line: say it plainly."),
    ],
)
def test_a_roll_tells_the_line_to_joke_or_not_before_its_length(joke: bool, direction: str) -> None:
    prompt = turn_prompt("BACKGROUND", [], NAMES, Cue.REPLY, "Henrietta", joke=joke)

    assert f"{direction}\n\nSay one or two sentences, at most 40 words." in prompt


def test_without_a_roll_a_turn_says_nothing_about_jokes() -> None:
    assert "joke" not in turn_prompt("BACKGROUND", [], NAMES, Cue.REPLY, "Henrietta").lower()


@pytest.mark.parametrize("seriousness", [0.1, 0.5, 0.8])
def test_lines_joke_as_often_as_seriousness_leaves_room_for(seriousness: float) -> None:
    humour = Humour(style=HumourStyle.DRY, seriousness=seriousness)

    rolls = [jokes(humour, f"talk/kofi/{n}") for n in range(2000)]

    assert sum(map(bool, rolls)) / len(rolls) == pytest.approx(1 - seriousness, abs=0.03)
    assert rolls == [jokes(humour, f"talk/kofi/{n}") for n in range(2000)]


def test_no_humour_rolls_nothing_and_none_never_jokes() -> None:
    none = Humour(style=HumourStyle.NONE, seriousness=1)

    assert jokes(None, "talk/kofi/1") is None
    assert not any(jokes(none, f"talk/kofi/{n}") for n in range(200))


def test_a_turn_has_the_works_they_might_bring_up_after_the_background() -> None:
    mural = work("kofi-1", "kofi", "First Coat", NOW)
    poem = work("tobias-1", "tobias", "The Tables", NOW, medium=Medium.WRITING)
    works = [
        WorkTopic(remembers("kofi", mural, 'I painted "First Coat".', NOW), mural),
        WorkTopic(remembers("kofi", poem, "I read Tobias's poem. Lovely.", NOW), poem),
    ]

    prompt = turn_prompt("B", [], NAMES, Cue.OPEN, "Henrietta", speaker="kofi", works=works)

    assert prompt.startswith(
        "B\n\n"
        'Your own works, which you might bring up and stand by:\n- I painted "First Coat".\n\n'
        "Works by others you might bring up:\n- I read Tobias's poem. Lovely.\n\n"
        "The conversation hasn't started yet."
    )


def test_a_turn_says_how_the_speaker_feels_after_the_background_in_words() -> None:
    feeling = ("starving", "tired")

    prompt = turn_prompt("B", [], NAMES, Cue.OPEN, "Henrietta", mood=feeling)

    assert prompt.startswith(
        "B\n\nRight now you're starving and tired.\n\nThe conversation hasn't started yet."
    )
    [said] = [part for part in prompt.split("\n\n") if part.startswith("Right now")]
    assert re.search(r"\d", said) is None
    assert "Right now" not in turn_prompt("B", [], NAMES, Cue.OPEN, "Henrietta")


def test_a_goodbye_says_what_their_need_sends_them_off_to_do() -> None:
    eat = "get something to eat"

    prompt = turn_prompt("B", [], NAMES, Cue.GOODBYE, "Henrietta", errand=eat)

    assert prompt.endswith(
        "You need to get something to eat. Wrap it up now with a brief, natural goodbye to "
        "Henrietta, and say why you're going."
    )
    for cue in (Cue.OPEN, Cue.REPLY, Cue.FAREWELL):
        assert turn_prompt("B", [], NAMES, cue, "H", errand=eat) == turn_prompt(
            "B", [], NAMES, cue, "H"
        )


def test_news_the_other_just_mentioned_follows_the_transcript() -> None:
    lines = [line(1, "henrietta", "They want to paint murals on Mars now.")]
    mars = memory("kofi", 'I read "Murals on Mars". Wild.', MemoryKind.NEWS)

    prompt = turn_prompt("B", lines, NAMES, Cue.REPLY, "Henrietta", recalled=[mars])

    assert (
        "Henrietta: They want to paint murals on Mars now.\n\n"
        "You read about what Henrietta just mentioned:\n"
        '- I read "Murals on Mars". Wild.\n\n'
        "Say one or two sentences"
    ) in prompt
    assert "You read about" not in turn_prompt("B", lines, NAMES, Cue.REPLY, "Henrietta")


def test_a_turn_gives_what_stuck_with_them_from_one_article() -> None:
    lines = [line(1, "henrietta", "They want to paint murals on Mars now.")]
    mars = memory("kofi", 'I read "Murals on Mars" in The Atlantic. Wild.', MemoryKind.NEWS)
    mars = mars.model_copy(update={"points": ["The first mural goes up in 2031.", "It's red."]})

    prompt = turn_prompt("B", lines, NAMES, Cue.REPLY, "Henrietta", recalled=[mars], detail=mars)

    assert (
        '- I read "Murals on Mars" in The Atlantic. Wild.\n\n'
        'What stuck with you from "Murals on Mars":\n'
        "- The first mural goes up in 2031.\n"
        "- It's red.\n\n"
        "Say one or two sentences"
    ) in prompt
    pointless = mars.model_copy(update={"points": []})
    assert "What stuck" not in turn_prompt("B", lines, NAMES, Cue.REPLY, "H", detail=pointless)


def test_one_article_at_most_gives_its_points() -> None:
    def read(title: str, *points: str) -> Memory:
        content = f'I read "{title}" on the news terminal. Huh.'
        return memory("kofi", content, MemoryKind.NEWS).model_copy(update={"points": points})

    mars, bees, fete = read("Mars", "Red."), read("Bees", "Fewer."), read("Fete", "Rained off.")

    assert detailed([read("Rain")], [mars, bees], [fete]) == mars
    assert detailed([], [read("Rain"), fete]) == fete
    assert detailed([read("Rain")], []) is None


def test_a_speaker_sees_how_their_latest_lines_began() -> None:
    said = ["Ha, mostly paint and pavement.", "Ha! Fair enough.", "Go on, then.", "Ha, a wall?"]
    lines = [line(n, "kofi", text) for n, text in enumerate(["Morning, all.", *said], 1)]

    prompt = turn_prompt("B", lines, NAMES, Cue.REPLY, "Henrietta", speaker="kofi")

    assert prompt.endswith(
        'Your lines so far began "Ha, mostly paint...", "Ha! Fair enough...", "Go on, then...", '
        '"Ha, a wall...". Begin this one another way, and don\'t greet Henrietta again.\n\n'
        "Say one or two sentences, at most 40 words.\n\n"
        "Say your next line to Henrietta. Keep the conversation going: don't wrap it up or say "
        "goodbye yet."
    )
    assert "began" not in turn_prompt("B", lines, NAMES, Cue.REPLY, "Kofi", speaker="henrietta")


def test_a_turn_asks_for_at_most_max_words() -> None:
    prompt = turn_prompt("B", [], NAMES, Cue.OPEN, "Kofi", ConversationConfig(max_words=25))

    assert "Say one or two sentences, at most 25 words." in prompt


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
        "Lovely to see you, bye!",
        "I'll see you out there on Saturday.",
        "I'll see you right there at six.",
        "I'll see you right here at six.",
        "I'll see you right after church.",
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
        "Nice to see you.",
        "Don't get up, I'll see you out.",
        "I'll see you right, don't worry.",
        "We'll see you through the winter.",
        "I'll see you home after the quiz.",
        "I'll see you off at the station.",
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
        (
            "Sit, will you? [connection, warmth]",
            Draft("Sit, will you?", (CoreValue.CONNECTION,)),
        ),
        ("Hi. [laughs] Okay.", Draft("Hi. [laughs] Okay.")),
    ],
)
def test_parsing_a_reply(reply: str, draft: Draft) -> None:
    speaker, other = ["Kofi", "Kofi Lindqvist-Mensah"], ["Henrietta", "Henrietta Okonkwo-Bell"]

    assert parse_reply(reply, speaker, other) == draft


LONG = (
    "Kia orana, Marguerite. I read that Mars piece in Scientific American this morning, and I "
    "keep thinking about the families on my list who can't make rent. Mrs. Puna down the road "
    "has had three notices this year. Right, so, who pays for the domes?"
)


def test_sentences_that_start_past_max_words_are_dropped() -> None:
    draft = parse_reply(f"{LONG} The council won't say.\n[values: justice, compassion]")

    assert draft == Draft(LONG, (CoreValue.JUSTICE, CoreValue.COMPASSION))


def test_the_sentence_that_crosses_max_words_is_kept() -> None:
    assert parse_reply(LONG, config=ConversationConfig(max_words=40)).text == LONG


def test_a_trim_never_ends_on_an_abbreviation() -> None:
    draft = parse_reply(LONG, config=ConversationConfig(max_words=28))

    assert draft.text == LONG.removesuffix(" Right, so, who pays for the domes?")


def test_a_voice_without_a_measured_rate_takes_200_words_a_minute() -> None:
    assert duration(" ".join(["word"] * 15)) == pytest.approx(4.5)
    assert duration("Hi.") == pytest.approx(1.0)
    assert duration("Hi.", ConversationConfig(min_line_seconds=0)) == pytest.approx(0.3)


def test_a_measured_voice_takes_as_long_as_its_rate_says() -> None:
    rate = SpeakingRate(base_seconds=0.6, seconds_per_word=0.27)

    assert duration(" ".join(["word"] * 15), rate=rate) == pytest.approx(4.65)
    assert duration("Hi.", rate=rate) == pytest.approx(1.0)
    assert duration("Hi.", ConversationConfig(min_line_seconds=0), rate) == pytest.approx(0.87)
