import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from simile.characters import novelty
from simile.characters.novelty import Embedder
from simile.characters.pool import (
    CONTENT_DIR,
    POOL_DIR,
    RENAMES,
    NotAPool,
    generate_pool,
    load_pool,
    name_structure,
    occupation_category,
    readme_command,
    rename,
)
from simile.cli import create_cli
from simile.llm import CallRecord, FakeProvider, LLMClient, Request

type Fakes = Callable[..., tuple[LLMClient, FakeProvider]]
type Reply = Callable[..., str]

runner = CliRunner()
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def quiet(_: str) -> None:
    pass


def said(result: Result) -> str:
    """The CLI's output with the error box's borders and line wrapping taken out."""
    return " ".join(result.output.replace("│", " ").split())


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
    assert "outside content/" in said(result)
    assert not fake.requests
    assert {path: path.read_bytes() for path in out.rglob("*") if path.is_file()} == before


def test_the_write_guard_ignores_case(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProvider()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))
    tables = CONTENT_DIR / "characters" / "tables"
    shouted = CONTENT_DIR.parent / "CONTENT" / "characters" / "tables"
    before = {path: path.read_bytes() for path in tables.iterdir()}

    result = runner.invoke(create_cli(), ["characters", "generate", "--out", str(shouted)])

    assert result.exit_code != 0
    assert "outside content/" in said(result)
    assert not fake.requests
    assert {path: path.read_bytes() for path in tables.iterdir()} == before


@pytest.mark.anyio
async def test_a_readme_the_generator_didnt_write_is_left_alone(
    fake_llm: Fakes, embedder: Embedder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "README.md").write_text("# My project\n")
    llm, fake = fake_llm()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))

    result = runner.invoke(create_cli(), ["characters", "generate", "--out", str(tmp_path)])
    with pytest.raises(NotAPool, match="isn't a character pool's README"):
        await generate_pool(llm, 1, 0, tmp_path, embedder=embedder, echo=quiet)

    assert result.exit_code != 0
    assert "isn't a character pool's README" in said(result)
    assert not fake.requests
    assert (tmp_path / "README.md").read_text() == "# My project\n"
    assert not list(tmp_path.glob("*.json"))


@pytest.mark.anyio
async def test_a_renamed_character_keeps_its_slot_in_the_plan(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path
) -> None:
    first, _ = await run(fake_llm, embedder, tmp_path, 2)
    old, kept = first.written
    given = old.name.split()[0]
    path = tmp_path / f"{old.id}.json"
    path.write_text(path.read_text().replace(old.persona, f"{given} keeps to himself."))

    character = rename(tmp_path, old.id, "Ana Folau", now=NOW)
    second, fake = await run(fake_llm, embedder, tmp_path, 2)

    assert (character.id, character.name, character.version) == ("ana_folau", "Ana Folau", 2)
    assert character.persona == "Ana keeps to himself."
    assert not path.exists()
    assert json.loads((tmp_path / RENAMES).read_text()) == {"3:0": "ana_folau"}
    assert not fake.requests
    assert second.skipped == ["ana_folau", kept.id]
    readme = (tmp_path / "README.md").read_text()
    assert "`ana_folau` Ana Folau" in readme
    assert old.name not in readme


@pytest.mark.anyio
async def test_renaming_again_points_the_slot_at_the_latest_name(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path
) -> None:
    first, _ = await run(fake_llm, embedder, tmp_path, 1)
    planned = first.written[0]

    rename(tmp_path, planned.id, "Ana Folau", now=NOW)
    rename(tmp_path, "ana_folau", "Bram de Wit", now=NOW)
    assert json.loads((tmp_path / RENAMES).read_text()) == {"3:0": "bram_de_wit"}

    rename(tmp_path, "bram_de_wit", planned.name, now=NOW)
    assert json.loads((tmp_path / RENAMES).read_text()) == {}
    assert [c.id for c in load_pool(tmp_path)] == [planned.id]


@pytest.mark.anyio
async def test_a_rename_never_takes_another_characters_id(
    fake_llm: Fakes, embedder: Embedder, tmp_path: Path
) -> None:
    first, _ = await run(fake_llm, embedder, tmp_path, 2)
    a, b = first.written

    with pytest.raises(ValueError, match="already in the pool"):
        rename(tmp_path, a.id, b.name)
    assert len(load_pool(tmp_path)) == 2


def test_the_cli_renames_a_character(
    fake_llm: Fakes, embedder: Embedder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, fake = fake_llm()
    monkeypatch.setattr(LLMClient, "provider", property(lambda client: fake))
    monkeypatch.setattr(novelty, "LocalEmbedder", lambda: embedder)
    args = ["characters", "generate", "--count", "1", "--seed", "1", "--out", str(tmp_path)]
    assert runner.invoke(create_cli(), args).exit_code == 0
    [character] = load_pool(tmp_path)

    args = ["characters", "rename", character.id, "Ana Folau", "--dir", str(tmp_path)]
    result = runner.invoke(create_cli(), args)

    assert result.exit_code == 0, result.output
    assert f"Renamed {character.id} to Ana Folau (ana_folau)" in result.output
    assert [c.name for c in load_pool(tmp_path)] == ["Ana Folau"]
