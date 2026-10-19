import json
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from simile.art.palette import PALETTE
from simile.characters.brief import LOCKABLE, SECTIONS, Brief
from simile.characters.generate import TooSimilar, character_id, generate, reroll
from simile.characters.novelty import Embedder, Novelty
from simile.characters.sheet import draw
from simile.characters.tables import load_tables
from simile.characters.voice import accent_sentence
from simile.llm import FakeProvider, LLMClient, Request
from simile.schema import (
    Appearance,
    Arrival,
    Character,
    CharacterSource,
    CharacterVoice,
    CoreValue,
    Craft,
    Gender,
    Hook,
    HookKind,
    HookSide,
    Humour,
    HumourStyle,
    PastMemory,
    Traits,
)

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
LINE = "The early bus leaves at twenty to seven, and I like to be at the stop by half past."
LOOK = {
    "skin": "#c28569",
    "hair_style": "bob",
    "hair_colour": "#8b9bb4",
    "top_colour": "#3a4466",
    "bottom_colour": "#262b44",
    "shoe_colour": "#262b44",
    "build": "average",
    "accessories": ["glasses"],
}

type Fakes = Callable[..., tuple[LLMClient, FakeProvider]]
type Reply = Callable[..., str]

FULL = {
    "name": "Danuta Sobczak",
    "birth_year": 1968,
    "gender": Gender.WOMAN,
    "origin": "Poland",
    "arrival": Arrival(age=34, reason="for a job"),
    "occupation": "Bus driver",
    "values": {value: 0.5 for value in CoreValue},
    "backstory": "Runs the early route and has never once been late.",
    "persona": "Dry, exacting and impossible to hurry.",
    "speaking_style": "Short sentences, times and numbers.",
    "mannerisms": ["answers a question with another question"],
    "humour": Humour(style=HumourStyle.DEADPAN, seriousness=0.8),
    "interests": ["timetables", "Polish crime novels", "tomatoes"],
    "past": [
        PastMemory(age=22, content="Passed the bus test first time.", salience=0.6, valence=0.6)
    ],
    "hooks": [Hook(kind=HookKind.DEBT, side=HookSide.TARGET, description="Lent her savings.")],
    "traits": Traits(sociability=0.35),
    "appearance": Appearance.model_validate(LOOK),
    "voice": CharacterVoice(description="A Polish accent. Low and dry.", reference_line=LINE),
    "craft": Craft(medium="writing", form="stern notices"),
}


def requested_fields(request: Request) -> set[str]:
    schema = json.loads(request.system.split("no code fence:\n", 1)[1])
    return set(schema["properties"])


async def make(fakes: Fakes, brief: Brief | None = None, seed: int = 0, **options: Any):
    llm, fake = fakes()
    result = await generate(llm, brief, rng=random.Random(seed), now=NOW, **options)
    return result, fake


async def test_a_premade_character_is_written_then_critiqued(fake_llm: Fakes) -> None:
    result, fake = await make(fake_llm)
    character = result.character

    assert [r.system.split(".")[0] for r in fake.requests] == [
        "You write characters for a library that a life-simulation game casts its villagers from",
        "You edit characters for a library that a life-simulation game casts its villagers from",
    ]
    assert character.source is CharacterSource.PREMADE
    assert character.id == character_id(character.name)
    assert character.persona.startswith("Revised: ")
    assert all(memory.content.startswith("past ") for memory in character.past)
    assert 2 <= len(character.hooks) <= 4
    assert len(character.voice.reference_line.split()) >= 12
    assert result.notes == ["Swapped a stock phrase for something specific."]
    assert (character.created, character.updated, character.version) == (NOW, NOW, 1)


@pytest.mark.parametrize("fields", [LOCKABLE, *([field] for field in LOCKABLE)], ids=str)
async def test_locked_fields_survive_every_stage(fake_llm: Fakes, fields: tuple[str, ...]) -> None:
    brief = Brief(**{field: FULL[field] for field in fields})

    result, fake = await make(fake_llm, brief)

    assert {field: getattr(result.character, field) for field in fields} == {
        field: FULL[field] for field in fields
    }
    for request in fake.requests:
        assert not requested_fields(request) & set(fields)


async def test_one_or_two_mannerisms_are_drawn_in_code_and_stored(fake_llm: Fakes) -> None:
    listed = {item for group in load_tables().mannerisms.group for item in group.items}
    drawn = []
    for seed in range(6):
        mannerisms = draw(random.Random(seed), Brief()).mannerisms
        result, fake = await make(fake_llm, seed=seed)

        assert result.character.mannerisms == mannerisms
        assert 1 <= len(mannerisms) <= 2 and set(mannerisms) <= listed
        assert f"- Verbal habits: {'; '.join(mannerisms)}." in fake.requests[0].messages[-1].content
        for request in fake.requests:
            assert "mannerisms" not in requested_fields(request)
        drawn.append(len(mannerisms))
    assert set(drawn) == {1, 2}


async def test_locked_mannerisms_hint_at_the_speaking_style(fake_llm: Fakes) -> None:
    habits = ["trails off mid-sentence", "teases the people they like most"]

    result, fake = await make(fake_llm, Brief(mannerisms=habits))

    assert result.character.mannerisms == habits
    prompt = fake.requests[0].messages[-1].content
    assert f"- Verbal habits: {'; '.join(habits)}." in prompt
    assert "build on a verbal habit" in prompt


async def test_a_character_without_mannerisms_keeps_none(fake_llm: Fakes) -> None:
    original = (await make(fake_llm, seed=1))[0].character.model_copy(update={"mannerisms": []})
    llm, _ = fake_llm()

    character = (await reroll(llm, original, "voice", rng=random.Random(2), now=NOW)).character

    assert character.mannerisms == []
    assert "mannerisms" not in character.model_dump()


async def test_build_hair_and_top_are_drawn_in_code(fake_llm: Fakes) -> None:
    look = draw(random.Random(0), Brief()).look
    assert look is not None

    appearance = (await make(fake_llm, seed=0))[0].character.appearance

    assert (appearance.build, appearance.hair_style) == (look.build, look.hair_style)
    assert appearance.top_colour == PALETTE[look.top]


async def test_a_fully_locked_character_makes_no_calls(fake_llm: Fakes) -> None:
    result, fake = await make(fake_llm, Brief(**FULL))

    assert not fake.requests
    assert result.character.model_dump(include=set(FULL)) == Brief(**FULL).model_dump(
        include=set(FULL)
    )


@pytest.mark.parametrize("section", SECTIONS)
async def test_a_reroll_keeps_every_other_section(fake_llm: Fakes, section: str) -> None:
    original = (await make(fake_llm, seed=1))[0].character
    llm, fake = fake_llm()

    result = await reroll(llm, original, section, rng=random.Random(2), now=NOW)
    character = result.character

    rerolled = set(SECTIONS[section])
    kept = set(LOCKABLE) - rerolled
    assert character.model_dump(include=kept) == original.model_dump(include=kept)
    assert character.model_dump(include=rerolled) != original.model_dump(include=rerolled)
    assert (character.id, character.created, character.version) == (
        original.id,
        original.created,
        original.version + 1,
    )
    for request in fake.requests:
        assert requested_fields(request) <= rerolled | {"notes"}


async def test_rerolled_sections_can_be_combined(fake_llm: Fakes) -> None:
    original = (await make(fake_llm, seed=1))[0].character
    llm, _ = fake_llm()

    result = await reroll(llm, original, "past", "biography", rng=random.Random(3), now=NOW)
    character = result.character

    assert character.voice == original.voice
    assert character.past != original.past
    assert character.backstory != original.backstory


async def test_a_name_reroll_renames_them_in_their_own_prose(fake_llm: Fakes) -> None:
    original = (await make(fake_llm, seed=1))[0].character
    given = original.name.split()[0]
    named = original.model_copy(update={"persona": f"{given} keeps to herself."})
    llm, fake = fake_llm()

    character = (await reroll(llm, named, "name", rng=random.Random(4), now=NOW)).character

    assert not fake.requests
    assert set(character.name.split()).isdisjoint(original.name.split())
    assert character.persona == f"{character.name.split()[0]} keeps to herself."


async def test_a_player_character_gets_suggestions_not_rewrites(fake_llm: Fakes) -> None:
    brief = Brief(source=CharacterSource.PLAYER, persona=FULL["persona"])

    result, fake = await make(fake_llm, brief)
    character = result.character

    assert character.source is CharacterSource.PLAYER
    assert character.persona == FULL["persona"]
    assert not character.backstory.startswith("Revised: ")
    assert "persona" in requested_fields(fake.requests[1])
    suggested = {s.field: s for s in result.suggestions}
    assert suggested["persona"].current == FULL["persona"]
    assert suggested["persona"].suggested.startswith("Revised: ")
    assert {"backstory", "past[0]"} <= set(suggested)


async def test_ages_in_a_backstory_are_sent_to_the_critic(fake_llm: Fakes, reply: Reply) -> None:
    timeline = "At 26 she left. At 31 she married. When she was forty she came here."

    def biography(request: Request) -> str:
        return reply(request, overrides={"backstory": timeline})

    llm, fake = fake_llm(biography)
    await generate(llm, rng=random.Random(0), now=NOW)

    assert "The backstory gives an age 3 times" in fake.requests[1].messages[-1].content


def duplicate_of(character: Character, reply: Reply) -> list[Callable[[Request], str]]:
    """A biography and a critic reply that both copy `character`'s persona and backstory."""

    def copy(request: Request) -> str:
        same = {"persona": character.persona, "backstory": character.backstory}
        return reply(request, overrides=same)

    return [copy, copy]


async def test_the_novelty_check_rewrites_a_near_duplicate_premade_character(
    fake_llm: Fakes, embedder: Embedder, reply: Reply
) -> None:
    existing = (await make(fake_llm, seed=1))[0].character
    llm, fake = fake_llm(*duplicate_of(existing, reply))

    result = await generate(
        llm, rng=random.Random(5), novelty=Novelty(embedder, [existing]), now=NOW
    )

    assert len(fake.requests) == 4
    assert "too close to a character already in the library" in (
        fake.requests[2].messages[-1].content
    )
    assert existing.name in fake.requests[2].messages[-1].content
    assert result.character.persona != existing.persona
    assert not result.warnings


async def test_the_novelty_check_rejects_a_near_duplicate_it_cant_shake(
    fake_llm: Fakes, embedder: Embedder, reply: Reply
) -> None:
    existing = (await make(fake_llm, seed=1))[0].character
    llm, _ = fake_llm(*duplicate_of(existing, reply), *duplicate_of(existing, reply))

    with pytest.raises(TooSimilar) as raised:
        await generate(llm, rng=random.Random(5), novelty=Novelty(embedder, [existing]))

    assert raised.value.match.id == existing.id
    assert raised.value.match.similarity > 0.99


async def test_the_novelty_check_only_warns_for_a_player_character(
    fake_llm: Fakes, embedder: Embedder
) -> None:
    existing = (await make(fake_llm, seed=1))[0].character
    brief = Brief(
        source=CharacterSource.PLAYER, persona=existing.persona, backstory=existing.backstory
    )
    llm, fake = fake_llm()

    result = await generate(
        llm, brief, rng=random.Random(5), novelty=Novelty(embedder, [existing]), now=NOW
    )

    assert len(fake.requests) == 2
    assert result.character.persona == existing.persona
    assert result.warnings == [f"Close to {existing.name} in the library (1.00)."]


@pytest.mark.parametrize(
    ("origin", "arrival", "recording"),
    [
        ("Poland", Arrival(age=30, reason="for a job"), True),
        ("Nigeria", Arrival(age=25, reason="to study"), True),
        ("England", Arrival(age=40, reason="for a job"), True),
        ("United States", Arrival(age=30, reason="for a job"), False),
        ("Poland", None, False),
    ],
)
async def test_an_accent_voicedesign_cant_do_needs_recording(
    fake_llm: Fakes, origin: str, arrival: Arrival | None, recording: bool
) -> None:
    result, _ = await make(fake_llm, Brief(origin=origin, arrival=arrival))
    voice = result.character.voice

    assert voice.needs_recording is recording
    assert voice.reference_clip is None
    first = voice.description.split(". ")[0] + "."
    assert first == accent_sentence(None) or first.endswith("accent.") or "accent," in first


def test_character_ids_are_plain_and_unique() -> None:
    assert character_id("Đức Nguyễn") == "duc_nguyen"
    assert character_id("Łukasz Wójcik") == "lukasz_wojcik"
    assert character_id("Ana Folau", taken={"ana_folau"}) == "ana_folau_2"
