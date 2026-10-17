import json
from collections.abc import Callable
from dataclasses import replace

import pytest
from pydantic import ValidationError

from simile.llm import FakeProvider, LLMClient, Model, StructuredOutputError
from simile.npc.generate import CRAFT, HOMES, SYSTEM, Draft, generate, npc_id, plan, prompt
from simile.npc.values import ranked
from simile.schema import Craft, LocationKind, Medium, Npc
from simile.world.map import load_map

MakeDraft = Callable[..., Draft]

pytestmark = pytest.mark.anyio


async def village(
    llm: LLMClient, count: int = 10, seed: int = 0, *, rich: bool = False
) -> list[Npc]:
    return [npc async for npc in generate(llm, count, seed, rich=rich)]


def test_plan_is_deterministic_for_a_seed() -> None:
    assert plan(10, 4) == plan(10, 4)
    assert plan(10, 4) != plan(10, 5)


def test_plan_gives_each_resident_a_home() -> None:
    assert [brief.home for brief in plan(10, 0)] == [f"house_{n}" for n in range(1, 11)]
    assert [brief.home for brief in plan(3, 0)] == ["house_1", "house_2", "house_3"]


def test_homes_are_the_houses_on_the_map() -> None:
    houses = {loc.id for loc in load_map().locations if loc.kind is LocationKind.HOUSE}

    assert set(HOMES) == houses


@pytest.mark.parametrize("count", [0, len(HOMES) + 1])
def test_plan_needs_a_home_for_everyone(count: int) -> None:
    with pytest.raises(ValueError, match="one per home"):
        plan(count, 0)


@pytest.mark.parametrize("seed", range(5))
def test_plan_spreads_ages_and_balances_genders(seed: int) -> None:
    briefs = plan(10, seed)
    ages = sorted(brief.age for brief in briefs)

    assert 19 <= ages[0] <= 25 and 74 <= ages[-1] <= 80
    assert all(b - a >= 1 for a, b in zip(ages, ages[1:], strict=False))
    assert sorted(brief.gender for brief in briefs) == ["man"] * 5 + ["woman"] * 5


def test_the_prompt_puts_the_values_up_front() -> None:
    brief = plan(10, 0)[1]
    order = ranked(brief.values)

    text = prompt(brief, 2, 10, [])

    top = ", ".join(f"{v.value.replace('_', ' ')} {s:.2f}" for v, s in order[:5])
    bottom = ", ".join(f"{v.value.replace('_', ' ')} {s:.2f}" for v, s in order[::-1][:5])
    assert f"Cares most about: {top}" in text
    assert f"Cares least about: {bottom}" in text
    assert f"Age: {brief.age}" in text
    assert f"Gender: {brief.gender}" in text
    assert "resident 2 of 10" in text


def test_the_prompt_asks_for_a_craft() -> None:
    assert CRAFT in prompt(plan(10, 0)[0], 1, 10, [])


@pytest.mark.parametrize("seed", range(3))
def test_a_rich_plan_samples_facts_on_top_of_the_same_plan(seed: int) -> None:
    rich = plan(10, seed, rich=True)

    assert [replace(brief, facts=None) for brief in rich] == plan(10, seed)
    assert all(brief.facts for brief in rich)
    assert plan(10, seed, rich=True) == rich
    assert [b.facts for b in plan(10, seed + 1, rich=True)] != [b.facts for b in rich]


def test_the_sampled_name_occupation_and_events_reach_the_prompt() -> None:
    brief = plan(10, 0, rich=True)[3]
    assert (facts := brief.facts)

    text = prompt(brief, 4, 10, [])

    assert f"- Name: {facts.name}\n" in text
    assert f"- Origin: {facts.origin}\n" in text
    assert f"- Occupation: {facts.occupation}\n" in text
    for age, event in facts.events:
        assert f"\n  - {age}: {event}\n" in text
    assert f'- name: "{facts.name}", exactly as given.' in text
    assert f'- occupation: "{facts.occupation}", exactly as given.' in text
    assert "The village is international." not in text
    assert "why they live here" not in text


def test_the_default_prompt_samples_nothing_more() -> None:
    text = prompt(plan(10, 0)[3], 4, 10, [])

    assert "- Name:" not in text and "Life events" not in text
    assert f"- Gender: {plan(10, 0)[3].gender}\n\nCore values" in text
    assert "- name: a first and last name. The village is international." in text


async def test_a_rich_village_takes_names_and_occupations_from_the_facts(
    residents: Callable[[], FakeProvider],
) -> None:
    fake = residents()

    npcs = await village(LLMClient(fake), seed=2, rich=True)

    briefs = plan(10, 2, rich=True)
    for npc, brief, request in zip(npcs, briefs, fake.requests, strict=True):
        assert (facts := brief.facts)
        assert npc.name == facts.name
        assert npc.occupation == facts.occupation[0].upper() + facts.occupation[1:]
        assert f"- Name: {facts.name}\n" in request.messages[-1].content
    assert len({npc.id for npc in npcs}) == 10


async def test_a_rich_village_sends_the_same_prompts_for_a_seed(
    residents: Callable[[], FakeProvider],
) -> None:
    first, second, other = residents(), residents(), residents()

    for fake, seed in [(first, 4), (second, 4), (other, 5)]:
        await village(LLMClient(fake), seed=seed, rich=True)

    assert first.requests == second.requests
    assert first.requests[0] != other.requests[0]


async def test_each_resident_gets_the_craft_claude_chose(make_draft: MakeDraft) -> None:
    mural = Craft(medium=Medium.MURAL, form="political street murals")
    fake = FakeProvider([make_draft(craft=mural), make_draft("Bram de Wit", craft=None)])

    npcs = await village(LLMClient(fake), count=2)

    assert [npc.craft for npc in npcs] == [mural, None]
    assert "Craft: mural: political street murals." in fake.requests[1].messages[-1].content


def test_draft_must_say_whether_they_have_a_craft(make_draft: MakeDraft) -> None:
    fields = make_draft().model_dump(mode="json")
    del fields["craft"]

    with pytest.raises(ValidationError):
        Draft.model_validate(fields)


async def test_generates_valid_npcs_for_every_home(llm: LLMClient, names: list[str]) -> None:
    npcs = await village(llm)

    assert [npc.name for npc in npcs] == names
    assert [npc.home for npc in npcs] == list(HOMES)
    assert len({npc.id for npc in npcs}) == 10
    for npc, brief in zip(npcs, plan(10, 0), strict=True):
        assert Npc.model_validate_json(npc.model_dump_json()) == npc
        assert npc.values == brief.values
        assert npc.age == brief.age
        assert npc.voice.reference_clip is None


async def test_generation_is_deterministic_for_a_seed(
    residents: Callable[[], FakeProvider],
) -> None:
    first, second = residents(), residents()

    assert await village(LLMClient(first), seed=3) == await village(LLMClient(second), seed=3)
    assert first.requests == second.requests


async def test_asks_sonnet_once_per_npc_with_the_system_prompt(
    residents: Callable[[], FakeProvider],
) -> None:
    fake = residents()

    await village(LLMClient(fake), count=4)

    assert len(fake.requests) == 4
    assert {request.model for request in fake.requests} == {Model.SONNET}
    assert all(request.system.startswith(SYSTEM) for request in fake.requests)


async def test_each_prompt_lists_the_residents_so_far_with_background_and_looks(
    residents: Callable[[], FakeProvider], names: list[str]
) -> None:
    fake = residents()

    npcs = await village(LLMClient(fake), count=3)

    prompts = [request.messages[-1].content for request in fake.requests]
    first = npcs[0]
    assert "- none yet" in prompts[0]
    assert (
        f"- {first.name}, {first.age}, {first.occupation}. {first.name} grew up by the sea. Looks: "
        in prompts[1]
    )
    assert "They moved here for the quiet." not in prompts[1]
    assert names[1] not in prompts[1]
    assert f"- {names[0]}, " in prompts[2] and f"- {names[1]}, " in prompts[2]
    assert (
        "Looks: average build, bun espresso hair, forest top, slate bottoms, apron." in prompts[2]
    )


async def test_a_bad_reference_line_is_sent_back_once(make_draft: MakeDraft) -> None:
    good = make_draft()
    bad = good.model_dump(mode="json") | {"reference_line": "Hello there."}
    fake = FakeProvider([json.dumps(bad), good.model_dump_json()])

    [npc] = await village(LLMClient(fake), count=1)

    assert npc.voice.reference_line == good.reference_line
    assert "12-25 words" in fake.requests[1].messages[-1].content


async def test_gives_up_after_two_bad_replies() -> None:
    fake = FakeProvider(['{"name": "Ana"}'] * 2)

    with pytest.raises(StructuredOutputError):
        await village(LLMClient(fake), count=1)


@pytest.mark.parametrize(
    "line",
    [
        "Too short to hear.",
        " ".join(["word"] * 26),
        "What a lovely morning it is down by the river, I could stay here all day!",
    ],
)
def test_reference_lines_must_be_short_and_neutral(make_draft: MakeDraft, line: str) -> None:
    with pytest.raises(ValidationError):
        make_draft(reference_line=line)


def test_draft_needs_three_to_six_interests(make_draft: MakeDraft) -> None:
    with pytest.raises(ValidationError):
        make_draft(interests=["tides"])
    with pytest.raises(ValidationError):
        make_draft(interests=[f"topic {n}" for n in range(7)])


@pytest.mark.parametrize(
    ("name", "taken", "expected"),
    [
        ("Mei Lin", set(), "mei"),
        ("Mei Lin", {"mei"}, "mei_lin"),
        ("Mei Lin", {"mei", "mei_lin"}, "mei_lin_2"),
        ("Zoë O'Brien", set(), "zoe"),
        ("Jean-Luc Picard", set(), "jean"),
        ("Player One", set(), "player_one"),
        ("42 Bao", set(), "npc"),
        ("李", set(), "npc"),
    ],
)
def test_ids_are_unique_lowercase_slugs(name: str, taken: set[str], expected: str) -> None:
    assert npc_id(name, taken) == expected
