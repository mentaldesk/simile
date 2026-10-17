import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.llm import FakeProvider, LLMClient, Model
from simile.npc.content import load_npcs, readme, write_npcs
from simile.npc.crafts import SYSTEM, Choice, add_crafts
from simile.npc.generate import CRAFT, generate
from simile.npc.values import format_scores, ranked
from simile.schema import Craft, Medium, Npc

pytestmark = pytest.mark.anyio

runner = CliRunner()

MURAL = Craft(medium=Medium.MURAL, form="murals of the river at dawn")
NOTICES = Craft(medium=Medium.WRITING, form="stern notices for the residents' board")
CHOICES = [
    Choice(craft=MURAL, why="She paints what she walks past."),
    Choice(craft=None, why="He has nothing he wants to say."),
    Choice(craft=NOTICES, why="She likes the rules written down."),
]


@pytest.fixture
def cast(residents: Callable[[], FakeProvider]) -> list[Npc]:
    async def run() -> list[Npc]:
        return [npc async for npc in generate(LLMClient(residents()), 3, seed=5)]

    return sorted(asyncio.run(run()), key=lambda npc: npc.id)


@pytest.fixture
def village(cast: list[Npc], tmp_path: Path) -> Path:
    """The cast as it was before crafts, with no craft key at all."""
    write_npcs(cast, tmp_path, seed=5)
    for npc in cast:
        text = npc.model_dump_json(indent=2, exclude={"craft"}) + "\n"
        (tmp_path / f"{npc.id}.json").write_text(text, encoding="utf-8")
    return tmp_path


def files(directory: Path) -> dict[str, str]:
    return {path.stem: path.read_text(encoding="utf-8") for path in directory.glob("*.json")}


def everything_but_craft(text: str) -> str:
    head, _, _ = text.partition(',\n  "craft": ')
    return head.removesuffix("\n}\n")


def crafts(directory: Path, replies: list[Choice], *npcs: str) -> tuple[str, FakeProvider]:
    fake = FakeProvider(replies)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(LLMClient, "provider", property(lambda client: fake))
        result = runner.invoke(create_cli(), ["npc", "crafts", *npcs, "--dir", str(directory)])
    assert result.exit_code == 0, result.output
    return result.output, fake


def test_adds_crafts_and_changes_nothing_else(village: Path) -> None:
    before = files(village)

    output, fake = crafts(village, CHOICES)

    after = files(village)
    assert len(fake.requests) == 3
    assert [npc.craft for npc in load_npcs(village)] == [MURAL, None, NOTICES]
    assert '"craft": null\n}\n' in after[sorted(after)[1]]
    for id, text in after.items():
        assert everything_but_craft(text) == everything_but_craft(before[id]), id
    assert "Gave 2 of 3 NPCs a craft" in output
    assert "with 3 Claude calls" in output


def test_choosing_again_replaces_only_the_crafts(village: Path) -> None:
    crafts(village, CHOICES)
    before = files(village)

    crafts(village, CHOICES[::-1])

    after = files(village)
    assert [npc.craft for npc in load_npcs(village)] == [NOTICES, None, MURAL]
    for id, text in after.items():
        assert everything_but_craft(text) == everything_but_craft(before[id]), id


def test_chooses_again_for_only_the_residents_named(village: Path, cast: list[Npc]) -> None:
    crafts(village, CHOICES)
    before = files(village)

    output, fake = crafts(village, [CHOICES[1]], cast[0].id)

    after = files(village)
    assert [npc.craft for npc in load_npcs(village)] == [None, None, NOTICES]
    assert {id for id in after if after[id] != before[id]} == {cast[0].id}
    assert f"- {cast[2].name}, {cast[2].occupation}: writing: stern notices" in (
        fake.requests[0].messages[-1].content
    )
    assert "Gave 0 of 1 NPCs a craft" in output


def test_names_a_resident_who_isnt_there(village: Path) -> None:
    result = runner.invoke(create_cli(), ["npc", "crafts", "nobody", "--dir", str(village)])

    assert result.exit_code != 0
    assert "no such resident: nobody" in result.output


def test_prints_each_craft_and_why(village: Path, cast: list[Npc]) -> None:
    output, _ = crafts(village, CHOICES)

    assert f"{cast[0].id}: mural: murals of the river at dawn. She paints" in output
    assert f"{cast[1].id}: none. He has nothing he wants to say." in output


def test_rewrites_the_readme_with_the_crafts(village: Path) -> None:
    crafts(village, CHOICES)

    text = (village / "README.md").read_text()
    assert text == readme(load_npcs(village), seed=5)
    assert "| writing: stern notices for the residents' board |" in text


async def test_asks_sonnet_once_per_npc_from_who_they_are(cast: list[Npc]) -> None:
    fake = FakeProvider(CHOICES)

    crafted = [npc async for npc, _ in add_crafts(LLMClient(fake), cast)]

    assert [npc.craft for npc in crafted] == [MURAL, None, NOTICES]
    assert {request.model for request in fake.requests} == {Model.SONNET}
    assert all(request.system.startswith(SYSTEM) for request in fake.requests)
    for npc, request in zip(cast, fake.requests, strict=True):
        text = request.messages[-1].content
        order = ranked(npc.values)
        assert f"Choose a craft for {npc.name}, {npc.age}, {npc.occupation}." in text
        assert f"Cares most about: {format_scores(order[:5])}" in text
        assert f"Cares least about: {format_scores(order[::-1][:5])}" in text
        assert npc.persona in text
        assert "; ".join(npc.interests) in text
        assert CRAFT in text


async def test_each_prompt_lists_the_crafts_so_far(cast: list[Npc]) -> None:
    fake = FakeProvider(CHOICES)

    _ = [npc async for npc in add_crafts(LLMClient(fake), cast)]

    prompts = [request.messages[-1].content for request in fake.requests]
    first, second = cast[0], cast[1]
    assert "- none yet" in prompts[0]
    assert f"- {first.name}, {first.occupation}: mural: murals of the river at dawn" in prompts[1]
    assert f"- {second.name}, {second.occupation}: none" in prompts[2]


async def test_a_reply_without_a_craft_is_sent_back_once(cast: list[Npc]) -> None:
    fake = FakeProvider([json.dumps({"why": "No reason."}), CHOICES[0]])

    [(npc, why)] = [crafted async for crafted in add_crafts(LLMClient(fake), cast[:1])]

    assert npc.craft == MURAL
    assert why == CHOICES[0].why
    assert len(fake.requests) == 2
