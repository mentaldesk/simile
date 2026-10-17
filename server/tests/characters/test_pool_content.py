from simile.characters.brief import Brief
from simile.characters.generate import character_id, settle
from simile.characters.pool import (
    POOL_DIR,
    character_files,
    load_pool,
    load_renames,
    readme,
    readme_command,
)
from simile.characters.sheet import plan
from simile.characters.tables import load_tables
from simile.schema import CharacterSource


def test_the_committed_pool_is_premade_characters_with_their_own_files() -> None:
    characters = load_pool()

    assert characters
    assert [path.stem for path in character_files()] == [c.id for c in characters]
    assert len({c.name for c in characters}) == len(characters)
    for character in characters:
        assert character.id == character_id(character.name)
        assert character.source is CharacterSource.PREMADE
        assert character.voice.reference_clip is None
        assert 12 <= len(character.voice.reference_line.split()) <= 25


def test_the_pool_readme_is_up_to_date() -> None:
    count, seed = readme_command()

    assert (POOL_DIR / "README.md").read_text(encoding="utf-8") == readme(load_pool(), count, seed)


def test_rerunning_the_readme_command_would_write_nothing() -> None:
    count, seed = readme_command()
    t = load_tables()
    renames = load_renames()
    sheets = plan(count, seed)
    planned = [character_id(settle(Brief(values=s.values), s, t)["name"]) for s in sheets]

    assert set(renames) <= set(planned)
    assert sorted(renames.get(id, id) for id in planned) == [c.id for c in load_pool()]
