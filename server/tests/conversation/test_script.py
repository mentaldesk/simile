import re
from datetime import UTC, datetime, timedelta

import pytest

from simile.conversation import ConversationConfig, Draft
from simile.conversation.plan import Plan, Stance
from simile.conversation.prompt import WorkTopic
from simile.conversation.script import (
    Character,
    ScriptLine,
    ScriptParser,
    continue_prompt,
    scene_prompt,
    script_system,
    third_person,
)
from simile.llm import Message, Request
from simile.llm.fake import cast
from simile.memory import SharedHistory
from simile.npc import load_npcs
from simile.schema import (
    Aspect,
    CoreValue,
    Flag,
    FlagKind,
    InteractionEvent,
    Medium,
    Memory,
    MemoryKind,
)
from simile.social import describe, meet

from .conftest import remembers, work

NPCS = {npc.id: npc for npc in load_npcs()}
KOFI, HENRIETTA = NPCS["kofi"], NPCS["henrietta"]
NOW = datetime(2026, 1, 1, 9, 30, tzinfo=UTC)
NAMES = {"kofi": ["Kofi", KOFI.name], "henrietta": ["Henrietta", HENRIETTA.name]}
C, H = CoreValue.CONNECTION, CoreValue.HONESTY


def parser() -> ScriptParser:
    return ScriptParser(NAMES)


def streamed(text: str, size: int = 3) -> list[ScriptLine]:
    """`text` fed to a parser `size` characters at a time, then ended."""
    found = parser()
    lines = [line for n in range(0, len(text), size) for line in found.feed(text[n : n + size])]
    return lines + found.end()


def test_each_line_comes_out_as_soon_as_it_ends() -> None:
    script = parser()

    assert script.feed("Kofi: Morning, Henrietta! [values: conn") == []
    assert script.feed("ection]\nHenrietta: Hm.") == [
        ScriptLine("kofi", Draft("Morning, Henrietta!", (C,)))
    ]
    assert script.feed(" Morning. [values: honesty]\n") == [
        ScriptLine("henrietta", Draft("Hm. Morning.", (H,)))
    ]
    assert script.end() == []


def test_a_stream_that_breaks_mid_line_keeps_only_the_lines_it_finished() -> None:
    script = parser()

    lines = script.feed("Kofi: Morning! [values: connection]\nHenrietta: Good mor")

    assert lines == [ScriptLine("kofi", Draft("Morning!", (C,)))]


def test_the_last_line_counts_once_the_stream_ends_without_a_newline() -> None:
    assert streamed("Kofi: Morning!\nHenrietta: Bye then. [values: honesty]") == [
        ScriptLine("kofi", Draft("Morning!")),
        ScriptLine("henrietta", Draft("Bye then.", (H,))),
    ]


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("**Kofi:** Hi there. [values: connection]", ScriptLine("kofi", Draft("Hi there.", (C,)))),
        ("Kofi (grinning): Hi there.", ScriptLine("kofi", Draft("Hi there."))),
        ("Kofi: *grins* Hi there.", ScriptLine("kofi", Draft("Hi there."))),
        ('Kofi: "Hi there."', ScriptLine("kofi", Draft("Hi there."))),
        (f"{HENRIETTA.name}: Good day.", ScriptLine("henrietta", Draft("Good day."))),
        ("henrietta: Good day.", ScriptLine("henrietta", Draft("Good day."))),
        ("Kofi: I told Henrietta: no.", ScriptLine("kofi", Draft("I told Henrietta: no."))),
    ],
)
def test_a_line_is_cleaned_like_a_reply(text: str, line: ScriptLine) -> None:
    assert streamed(text) == [line]


def test_narration_headings_and_other_people_are_left_out() -> None:
    text = (
        "Scene: the coffee shop, mid-morning.\n\n"
        "Kofi: Morning!\n"
        "*Henrietta looks up from her paper.*\n"
        "Odalys: Hello both!\n"
        "Henrietta: [values: honesty]\n"
        "Henrietta: Hm. Morning.\n"
    )

    assert [(line.speaker, line.draft.text) for line in streamed(text)] == [
        ("kofi", "Morning!"),
        ("henrietta", "Hm. Morning."),
    ]


def test_a_long_line_is_cut_at_a_sentence_past_max_words() -> None:
    script = ScriptParser(NAMES, ConversationConfig(max_words=4))

    lines = script.feed("Kofi: One two three four. Five six. Seven.\n")

    assert lines == [ScriptLine("kofi", Draft("One two three four."))]


def test_lines_without_a_speakers_name_are_left_out() -> None:
    assert streamed("Morning! How are things?\nOh, not bad.") == []
    assert [line.speaker for line in streamed("Hello.\nKofi: Hi.\nBye.")] == ["kofi"]


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ({"like": 0.95, "familiarity": 0.8}, "Ana likes Kofi a lot. Ana knows them well."),
        (
            {"like": 0.8, "trust": 0.1, "respect": 0.9},
            "Ana likes Kofi a lot and has great respect for them but doesn't trust them at all. "
            "Ana barely knows them.",
        ),
        (
            {"like": 0.05, "trust": 0.3, "respect": 0.25},
            "Ana can't stand Kofi, doesn't trust them and doesn't think much of them. "
            "Ana barely knows them.",
        ),
        ({}, "Ana has no strong feelings about Kofi. Ana barely knows them."),
    ],
)
def test_feelings_are_told_in_the_third_person(scores: dict[str, float], expected: str) -> None:
    base = {"like": 0.5, "trust": 0.5, "respect": 0.5, "familiarity": 0.1}
    rel = meet(HENRIETTA, "kofi").model_copy(update={**base, **scores})

    assert third_person(describe(rel, "Kofi"), "Ana") == expected


def test_your_and_you_become_the_name() -> None:
    assert third_person("Kofi once saved your life: you fell in.", "Ana") == (
        "Kofi once saved Ana's life: Ana fell in."
    )


def memory(
    owner: str, content: str, kind: MemoryKind = MemoryKind.CONVERSATION, news: str | None = None
) -> Memory:
    return Memory(
        owner=owner,
        kind=kind,
        content=content,
        salience=0.8,
        valence=0.2,
        timestamp=NOW,
        news_id=news,
    )


PLAN = Plan(
    {"kofi": "Kofi", "henrietta": "Henrietta"},
    {"kofi": Stance(0.8, 20), "henrietta": Stance(0.35, 3, ("tired",))},
    "kofi",
    "henrietta",
    5,
)


def test_a_scene_has_both_sides_whats_between_them_and_the_direction() -> None:
    kofi = Character(
        KOFI,
        meet(KOFI, "henrietta").model_copy(update={"like": 0.1, "familiarity": 0.5}),
        [memory("kofi", "Odalys fed half the square on Sunday.")],
        [
            memory("kofi", "Read about painted bridges.", MemoryKind.NEWS, "bridges"),
            memory("kofi", "Read about a mural festival.", MemoryKind.NEWS, "murals"),
        ],
        [("Odalys", "she's leaving the village in spring")],
    )
    henrietta = Character(HENRIETTA, meet(HENRIETTA, "kofi"))
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
            )
        ],
        flags=[
            Flag(
                id=f"f{n}",
                kind=kind,
                owner=owner,
                about=about,
                description=description,
                created=NOW - timedelta(days=3),
            )
            for n, (kind, owner, about, description) in enumerate(
                [
                    (FlagKind.DEBT, "henrietta", "kofi", "a broken window."),
                    (FlagKind.GRUDGE, "kofi", "henrietta", "the mural"),
                    (FlagKind.SECRET, "henrietta", "kofi", "he can't read music"),
                ]
            )
        ],
    )

    prompt = scene_prompt(kofi, henrietta, history, "The Daily Grind", NOW, PLAN)

    intro, kofis, henriettas, between, direction = prompt.split("\n\n## ")
    assert cast(Request((Message("user", prompt),), "", "haiku")) == ("Kofi", "Henrietta", 5)
    assert intro == "It's 09:30, at The Daily Grind. Kofi has just walked up to Henrietta."
    assert kofis.startswith(f"Kofi\n{KOFI.name}, aged 21. Occupation: {KOFI.occupation}.")
    assert f"How Kofi speaks: {KOFI.speaking_style}" in kofis
    assert "Cares most about: open mindedness, adventure, creativity" in kofis
    assert "Cares least about: discipline, security, obedience." in kofis
    assert (
        "Kofi can't stand Henrietta but trusts them. Kofi knows them a little.\n\n"
        "Kofi holds a grudge against Henrietta over the mural, which only Kofi knows."
    ) in kofis
    assert "grudge" not in henriettas
    assert "On Kofi's mind, which only Kofi knows:\n- Odalys fed half" in kofis
    assert (
        "Told to Kofi in confidence, which only Kofi knows:\n"
        "- Odalys: she's leaving the village in spring"
    ) in kofis
    assert (
        "News Kofi read and might bring up:\n"
        "- Read about painted bridges.\n"
        "- Read about a mural festival."
    ) in kofis
    assert henriettas.startswith("Henrietta\n") and HENRIETTA.persona in henriettas
    assert "Odalys" not in henriettas and "On Henrietta's mind" not in henriettas
    assert between == (
        "Between them\n"
        "- 3 days ago, Henrietta: reported his mural to the council\n"
        "- Kofi still owes Henrietta for a broken window.\n"
        "- Kofi told Henrietta a secret: he can't read music. Only the two of them know it."
    )
    assert direction.startswith("Direction\n- Kofi is keen to talk.\n")


def test_a_scene_leaves_out_what_there_isnt() -> None:
    kofi = Character(KOFI, meet(KOFI, "henrietta"))
    henrietta = Character(HENRIETTA, meet(HENRIETTA, "kofi"))

    prompt = scene_prompt(kofi, henrietta, SharedHistory([], []), None, NOW, PLAN)

    assert prompt.startswith("It's 09:30, out in the street.")
    for missing in ("Between them", "'s mind", "confidence", "News", "works"):
        assert missing not in prompt


def read(owner: str, title: str, *points: str) -> Memory:
    content = f'I read "{title}" on the news terminal. Huh.'
    found = memory(owner, content, MemoryKind.NEWS, title.lower())
    return found.model_copy(update={"points": list(points)})


@pytest.mark.parametrize("opener_has_points", [True, False], ids=["opener", "other"])
def test_a_scene_gives_what_stuck_from_one_article_only(opener_has_points: bool) -> None:
    points = ["Blue paint.", "Six bridges."] if opener_has_points else []
    bridges = read("kofi", "Painted bridges", *points)
    kofi = Character(KOFI, meet(KOFI, "henrietta"), topics=[read("kofi", "Murals"), bridges])
    bins = read("henrietta", "New bins", "Collected on Tuesdays.")
    henrietta = Character(
        HENRIETTA, meet(HENRIETTA, "kofi"), topics=[bins, read("henrietta", "Fete", "Rained off.")]
    )

    prompt = scene_prompt(kofi, henrietta, SharedHistory([], []), None, NOW, PLAN)

    _, kofis, henriettas, _ = prompt.split("\n\n## ")
    assert prompt.count("What stuck with") == 1
    assert "Rained off." not in prompt
    if opener_has_points:
        assert kofis.endswith(
            '- I read "Painted bridges" on the news terminal. Huh.\n\n'
            'What stuck with Kofi from "Painted bridges":\n- Blue paint.\n- Six bridges.'
        )
        assert "Collected on Tuesdays." not in prompt
    else:
        assert henriettas.endswith(
            'What stuck with Henrietta from "New bins":\n- Collected on Tuesdays.'
        )


def test_each_side_has_their_works_with_the_artist_marked() -> None:
    mural = work("kofi-1", "kofi", "First Coat", NOW, tags=["mars"])
    poem = work("tobias-1", "tobias", "The Tables", NOW, medium=Medium.WRITING)
    painted = 'I painted "First Coat" on the tower.'
    saw = 'I saw Kofi\'s mural "First Coat". A disgrace.'
    read = 'I read Tobias\'s "The Tables". Sound.'
    kofi = Character(
        KOFI,
        meet(KOFI, "henrietta"),
        works=[WorkTopic(remembers("kofi", mural, painted, NOW), mural)],
    )
    henrietta = Character(
        HENRIETTA,
        meet(HENRIETTA, "kofi"),
        works=[
            WorkTopic(remembers("henrietta", mural, saw, NOW), mural),
            WorkTopic(remembers("henrietta", poem, read, NOW), poem),
        ],
    )

    prompt = scene_prompt(kofi, henrietta, SharedHistory([], []), None, NOW, PLAN)

    _, kofis, henriettas, _ = prompt.split("\n\n## ")
    assert kofis.endswith(
        f"Kofi's own works, which Kofi might bring up and stand by, in notes only Kofi knows:\n"
        f"- {painted}"
    )
    assert henriettas.endswith(
        "Works by others Henrietta might bring up, which only Henrietta knows:\n"
        f"- {saw} (Kofi made it.)\n- {read}"
    )
    assert cast(Request((Message("user", prompt),), "", "haiku")) == ("Kofi", "Henrietta", 5)


def test_each_side_says_how_their_needs_feel_and_the_leaver_why_they_go() -> None:
    kofi = Character(KOFI, meet(KOFI, "henrietta"))
    henrietta = Character(HENRIETTA, meet(HENRIETTA, "kofi"))
    hungry = Stance(0.8, 6, mood=("starving", "tired"), errand="get something to eat", drain=4)
    planned = Plan(
        dict(PLAN.names), {"kofi": Stance(0.8, 20), "henrietta": hungry}, "kofi", "henrietta", 8
    )

    prompt = scene_prompt(kofi, henrietta, SharedHistory([], []), None, NOW, planned)

    _, kofis, henriettas, direction = prompt.split("\n\n## ")
    feelings = third_person(describe(meet(HENRIETTA, "kofi"), "Kofi"), "Henrietta")
    assert f"{feelings}\n\nRight now Henrietta is starving and tired." in henriettas
    assert "Right now" not in kofis
    assert direction.endswith(
        "About 8 lines in all, ending when Henrietta takes their leave to get something to eat "
        "and Kofi answers."
    )
    assert cast(Request((Message("user", prompt),), "", "haiku")) == ("Kofi", "Henrietta", 8)


def test_each_side_lists_their_own_mannerisms_as_verbal_habits() -> None:
    habits = ["answers a question with another question", "teases the people they like most"]
    kofi = Character(KOFI.model_copy(update={"mannerisms": habits}), meet(KOFI, "henrietta"))
    henrietta = Character(HENRIETTA.model_copy(update={"mannerisms": []}), meet(HENRIETTA, "kofi"))

    prompt = scene_prompt(kofi, henrietta, SharedHistory([], []), None, NOW, PLAN)

    _, kofis, henriettas, _ = prompt.split("\n\n## ")
    assert (
        f"How Kofi speaks: {KOFI.speaking_style}\n"
        f"Kofi's verbal habits: {habits[0]}; {habits[1]}. "
        "Use these now and then, not in every line."
    ) in kofis
    assert f"How Henrietta speaks: {HENRIETTA.speaking_style}\n\n" in henriettas
    assert "verbal habits" not in henriettas


def test_the_system_prompt_sets_the_rules_and_the_format() -> None:
    system = script_system(ConversationConfig(max_words=30))

    assert "written like a scene in a novel" in system
    assert "Neither mentions what only the other knows" in system
    assert "never recite them" in system
    assert "rather than expert advice" in system
    assert "not a consultation" in system
    assert "they let it go" in system
    assert "pet words, phrases and verbal habits now and then, not in every line" in system
    assert "Mara: Morning! Lovely out, isn't it? [values: connection]" in system
    assert "peace of mind" in system
    assert "at most 30 words" in system
    assert re.search(r"\{|\}", system) is None


def test_asking_for_the_rest_shows_the_scene_so_far() -> None:
    written = [
        ScriptLine("kofi", Draft("Morning!", (C,))),
        ScriptLine("henrietta", Draft("Hm.")),
    ]

    prompt = continue_prompt("SCENE", written, {"kofi": "Kofi", "henrietta": "Henrietta"})

    assert prompt == (
        "SCENE\n\n## The scene so far\nKofi: Morning!\nHenrietta: Hm.\n\n"
        "Write the rest of the scene, from the next line to the goodbyes, in the same format. "
        "If it has already ended, write nothing."
    )
