from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.characters import novelty
from simile.characters.novelty import Embedder
from simile.characters.pool import (
    POOL_DIR,
    generate_pool,
    load_pool,
    name_structure,
    occupation_category,
    readme_command,
)
from simile.cli import create_cli
from simile.llm import CallRecord, FakeProvider, LLMClient, Request

type Fakes = Callable[..., tuple[LLMClient, FakeProvider]]
type Reply = Callable[..., str]

runner = CliRunner()


def quiet(_: str) -> None:
    pass


async def run(fakes: Fakes, embedder: Embedder, directory: Path, count: int, **options):
    llm, fake = fakes(*options.pop("replies", ()))
    calls: list[CallRecord] = []
    llm.listeners.append(calls.append)
    result = await generate_pool(
        llm, count, 3, directory, embedder=embedder, calls=calls, echo=quiet, **options
    )
    return result, fake


@pytest.mark.anyio
async def test_a_resumed_run_skips_finished_characters(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path
) -> None:
    first, _ = await run(fake_llm, embedder, tmp_path, 2)
    before = {path.name: path.read_bytes() for path in tmp_path.glob("*.json")}

    second, fake = await run(fake_llm, embedder, tmp_path, 3)

    assert len(first.written) == 2
    assert second.skipped == [c.id for c in first.written]
    assert len(second.written) == 1
    assert len(fake.requests) == 2
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.json") if p.name in before} == before
    assert len(load_pool(tmp_path)) == 3
    assert readme_command(tmp_path) == (3, 3)


@pytest.mark.anyio
async def test_max_calls_stops_starting_characters(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path
) -> None:
    result, fake = await run(fake_llm, embedder, tmp_path, 4, max_calls=5)

    assert len(result.written) == 2
    assert result.unstarted == 2
    assert len(fake.requests) == 4


@pytest.mark.anyio
async def test_a_character_too_close_to_the_pool_is_reported_not_written(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path, reply: Reply
) -> None:
    first, _ = await run(fake_llm, embedder, tmp_path, 1)
    existing = first.written[0]

    def copy(request: Request) -> str:
        same = {"persona": existing.persona, "backstory": existing.backstory}
        return reply(request, overrides=same)

    second, _ = await run(fake_llm, embedder, tmp_path, 2, replies=[copy] * 4)

    assert len(second.failed) == 1
    assert not second.written
    assert len(load_pool(tmp_path)) == 1


@pytest.mark.anyio
async def test_the_readme_reports_the_spread(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path
) -> None:
    await run(fake_llm, embedder, tmp_path, 4)
    readme = (tmp_path / "README.md").read_text()

    for heading in ("Name structure", "Occupation category", "Origin", "Voice"):
        assert f"| {heading} | Characters |" in readme
    for character in load_pool(tmp_path):
        assert f"`{character.id}` {character.name}" in readme
    assert "uv run simile characters generate --count 4 --seed 3" in readme


@pytest.mark.parametrize(
    ("name", "structure"),
    [
        ("Ana Folau", "given name and surname"),
        ("Pieter van Wyk", "surname with a particle"),
        ("Miguel Ángel Ruiz", "two given names"),
        ("Kerry-Ann Campbell", "hyphenated given name"),
        ("Ana Salazar-Holm", "double-barrelled surname"),
    ],
)
def test_name_structure(name: str, structure: str) -> None:
    assert name_structure(name) == structure


@pytest.mark.parametrize(
    ("occupation", "category"),
    [
        ("Bus driver", "operators"),
        ("Retired bricklayer", "retired"),
        ("Apprentice plumber", "student"),
        ("Out of work", "not in work"),
    ],
)
def test_occupation_category(occupation: str, category: str) -> None:
    assert occupation_category(occupation) == category


def test_the_cli_writes_the_pool_and_counts_calls(
    fake_llm: Fakes,
    embedder: Embedder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, fake = fake_llm()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))
    monkeypatch.setattr(novelty, "LocalEmbedder", lambda: embedder)
    args = ["characters", "generate", "--count", "2", "--seed", "1", "--out", str(tmp_path)]

    result = runner.invoke(create_cli(), args)

    assert result.exit_code == 0, result.output
    assert len(load_pool(tmp_path)) == 2
    assert "Wrote 2 characters" in result.output
    calls = "Claude calls: 4 fake-haiku (2 character-biography, 2 character-critic)."
    assert calls in result.output


@pytest.mark.parametrize("folder", ["npcs", "voices", "characters/tables"])
def test_the_cli_never_writes_where_current_residents_live(
    folder: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeProvider()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))
    out = POOL_DIR.parents[1] / folder
    before = {path: path.read_bytes() for path in out.rglob("*") if path.is_file()}

    result = runner.invoke(create_cli(), ["characters", "generate", "--out", str(out)])

    assert result.exit_code != 0
    assert "outside content/" in result.output
    assert not fake.requests
    assert {path: path.read_bytes() for path in out.rglob("*") if path.is_file()} == before
