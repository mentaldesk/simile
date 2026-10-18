import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from simile.characters import generate as engine
from simile.characters.brief import Brief
from simile.library import Library
from simile.library.generation import events
from simile.library.store import CONTENT, DEFAULT_ROOT, REPO, default_root
from simile.llm import CallRecord, FakeProvider, LLMClient
from simile.schema import Character, CharacterSource

from .conftest import PREMADE, character, clip


def test_the_library_sits_beside_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SIMILE_LIBRARY")
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "saves" / "simile.db"))
    assert default_root() == tmp_path / "saves" / "library"

    monkeypatch.setenv("SIMILE_DB", ":memory:")
    assert default_root() == DEFAULT_ROOT

    monkeypatch.setenv("SIMILE_LIBRARY", str(tmp_path / "elsewhere"))
    assert default_root() == tmp_path / "elsewhere"


@pytest.mark.parametrize("folder", ["content/characters", "CONTENT/characters", "content"])
def test_never_keeps_player_characters_in_content(folder: str) -> None:
    with pytest.raises(ValueError, match="player characters never go there"):
        Library(REPO / folder)


def test_finds_each_reference_clip(library: Library, root: Path) -> None:
    library.create(character())
    voiced = library.save_clip("wren_abernethy", clip())
    premade = Character.model_validate(
        PREMADE | {"voice": PREMADE["voice"] | {"reference_clip": "content/voices/x.wav"}}
    )

    assert voiced.voice.reference_clip == "clips/wren_abernethy.wav"
    assert library.clip(voiced) == root / "clips" / "wren_abernethy.wav"
    assert library.clip(premade) == CONTENT / "voices" / "x.wav"
    assert library.clip(library.get("tobiah_rennick")) is None


def test_moving_the_library_keeps_its_clips(library: Library, root: Path, tmp_path: Path) -> None:
    library.create(character())
    library.save_clip("wren_abernethy", clip())
    moved = tmp_path / "moved"
    root.rename(moved)

    elsewhere = Library(moved, library.premade_dir)
    voiced = elsewhere.get("wren_abernethy")

    assert elsewhere.clip(voiced) == moved / "clips" / "wren_abernethy.wav"
    assert elsewhere.clip(voiced).read_bytes() == clip()


def test_skips_a_file_that_isnt_a_player_character(library: Library, root: Path) -> None:
    (root / "characters").mkdir(parents=True)
    (root / "characters" / "broken.json").write_text("{")
    (root / "characters" / "renamed.json").write_text(json.dumps(character()))

    assert [c.id for c in library.characters()] == ["tobiah_rennick"]
    assert library.create(character(id="broken")).id == "broken_2"


def test_lists_the_premade_pool(root: Path) -> None:
    premade = Library(root).characters()

    assert premade
    assert {c.source for c in premade} == {CharacterSource.PREMADE}


def test_starting_the_server_loads_no_generator() -> None:
    code = (
        "import sys; import simile.library.routes, simile.library; "
        "print(sorted(m for m in ('fastembed', 'numpy', 'simile.characters.generate') "
        "if m in sys.modules))"
    )
    loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert loaded.stdout.strip() == "[]", loaded.stderr


@pytest.mark.anyio
async def test_leaving_the_stream_stops_the_claude_call(library: Library) -> None:
    hold = asyncio.Event()
    records: list[CallRecord] = []
    llm = LLMClient(FakeProvider([["{", hold]]), listeners=[records.append])
    brief = Brief(source=CharacterSource.PLAYER)
    stream = events(library, llm, lambda llm: engine.generate(llm, brief))

    first = [json.loads(await anext(stream)) for _ in range(2)]
    await stream.aclose()
    for _ in range(100):
        if records:
            break
        await asyncio.sleep(0.01)

    assert first == [
        {"type": "call", "purpose": "character-biography"},
        {"type": "text", "text": "{"},
    ]
    assert [record.error for record in records] == ["cancelled"]
    assert library.generating == 0
