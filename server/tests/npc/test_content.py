import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest

from simile.llm import FakeProvider, LLMClient
from simile.npc.content import NPCS_DIR, load_npcs, readme, readme_seed, write_npcs
from simile.npc.generate import HOMES, MAX_WORDS, MIN_WORDS, first_sentence, generate, plan
from simile.npc.values import format_scores, ranked
from simile.schema import Medium, Npc


@pytest.fixture
def npcs(residents: Callable[[], FakeProvider]) -> list[Npc]:
    async def run() -> list[Npc]:
        return [npc async for npc in generate(LLMClient(residents()), 3, seed=5)]

    return asyncio.run(run())


def test_writes_each_npc_and_a_readme(npcs: list[Npc], tmp_path: Path) -> None:
    written = write_npcs(npcs, tmp_path / "npcs", seed=5)

    assert [path.name for path in written] == [f"{npc.id}.json" for npc in npcs] + ["README.md"]
    assert load_npcs(tmp_path / "npcs") == sorted(npcs, key=lambda npc: npc.id)
    assert (tmp_path / "npcs" / f"{npcs[0].id}.json").read_text().endswith("}\n")


def test_rewriting_replaces_npcs_from_an_earlier_run(npcs: list[Npc], tmp_path: Path) -> None:
    (tmp_path / "old_resident.json").write_text("{}")

    write_npcs(npcs[:2], tmp_path, seed=5)

    assert sorted(path.stem for path in tmp_path.glob("*.json")) == sorted(n.id for n in npcs[:2])


def test_rewriting_leaves_residents_who_dont_live_in_a_house(
    npcs: list[Npc], tmp_path: Path
) -> None:
    barista = npcs[2].model_copy(update={"id": "barista", "home": "coffee_shop"})
    (tmp_path / "barista.json").write_text(barista.model_dump_json())

    write_npcs(npcs[:2], tmp_path, seed=5)

    assert sorted(path.stem for path in tmp_path.glob("*.json")) == sorted(
        ["barista", *(n.id for n in npcs[:2])]
    )


def housed() -> list[Npc]:
    """The residents `generate-npcs` made: everyone living in a house."""
    return [npc for npc in load_npcs(NPCS_DIR) if npc.home in HOMES]


def test_the_readme_tables_top_values_against_persona(npcs: list[Npc]) -> None:
    text = readme(npcs, seed=5)

    assert "\nuv run simile generate-npcs --count 3 --seed 5\n" in text
    for npc in npcs:
        order = ranked(npc.values)
        [row] = [line for line in text.splitlines() if line.startswith(f"| `{npc.id}` ")]
        assert format_scores(order[:3]) in row
        assert format_scores(order[::-1][:3]) in row
        assert first_sentence(npc.persona) in row
        assert npc.persona not in row
        assert npc.craft and f"| {npc.craft.medium}: {npc.craft.form} |" in row


def test_the_readme_lists_the_facts_a_rich_brief_sampled(
    residents: Callable[[], FakeProvider],
) -> None:
    async def run() -> list[Npc]:
        return [npc async for npc in generate(LLMClient(residents()), 3, seed=5, rich=True)]

    npcs, briefs = asyncio.run(run()), plan(3, 5, rich=True)

    text = readme(npcs, 5, briefs)

    assert "\nuv run simile generate-npcs --count 3 --seed 5 --rich-brief --out <dir>\n" in text
    sampled = text.split("## Sampled facts")[1]
    for npc, brief in zip(npcs, briefs, strict=True):
        assert (facts := brief.facts)
        [row] = [line for line in sampled.splitlines() if line.startswith(f"| `{npc.id}` ")]
        assert f"| {facts.origin} | {facts.occupation} | " in row
        assert all(f"{age}: {event}" in row for age, event in facts.events)


def test_the_readme_lists_no_facts_without_a_rich_brief(npcs: list[Npc]) -> None:
    text = readme(npcs, 5, plan(3, 5))

    assert "Sampled facts" not in text and "--rich-brief" not in text


def test_the_readme_shows_a_resident_without_a_craft(npcs: list[Npc]) -> None:
    npc = npcs[0].model_copy(update={"craft": None})

    [row] = [line for line in readme([npc], seed=0).splitlines() if line.startswith("| `")]
    assert f"| {npc.occupation} | none |" in row


def test_the_readme_escapes_pipes(npcs: list[Npc]) -> None:
    npc = npcs[0].model_copy(update={"occupation": "Baker | baker"})

    assert "Baker \\| baker" in readme([npc], seed=0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Calm. Kind.", "Calm."),
        ("Is she ever late? Never.", "Is she ever late?"),
        ("No full stop", "No full stop"),
    ],
)
def test_first_sentence(text: str, expected: str) -> None:
    assert first_sentence(text) == expected


def test_the_committed_village_has_a_resident_in_every_home() -> None:
    village = load_npcs(NPCS_DIR)

    assert sorted(npc.home for npc in housed()) == sorted(HOMES)
    assert len({npc.id for npc in village}) == len(village)
    assert len({npc.name.split()[0] for npc in village}) == len(village)


def test_the_committed_reference_lines_are_neutral_and_short() -> None:
    for npc in load_npcs(NPCS_DIR):
        assert MIN_WORDS <= len(npc.voice.reference_line.split()) <= MAX_WORDS, npc.id
        assert "!" not in npc.voice.reference_line, npc.id


def test_readme_seed_reads_the_seed_from_the_readme(npcs: list[Npc], tmp_path: Path) -> None:
    write_npcs(npcs, tmp_path, seed=7)

    assert readme_seed(tmp_path) == 7


def test_the_committed_readme_matches_the_npcs() -> None:
    expected = readme(housed(), readme_seed())

    assert (NPCS_DIR / "README.md").read_text() == expected


def test_the_committed_values_and_ages_come_from_the_seed() -> None:
    briefs = {brief.home: brief for brief in plan(len(HOMES), readme_seed())}

    for npc in housed():
        assert npc.values == briefs[npc.home].values, npc.id
        assert npc.age == briefs[npc.home].age, npc.id


def test_most_of_the_committed_cast_has_a_craft_and_every_medium_is_made() -> None:
    crafts = [npc.craft for npc in housed() if npc.craft]

    assert len(crafts) > len(HOMES) / 2
    assert {craft.medium for craft in crafts} == set(Medium)
    assert len({craft.form for craft in crafts}) == len(crafts)
