import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageSequence
from typer.testing import CliRunner

from simile.art.build import BUILTIN, CONTENT_DIR, generate, load_npcs
from simile.art.palette import RGB
from simile.cli import create_cli

FIXTURES = Path(__file__).parents[1] / "fixtures" / "npcs"
FIXTURE_IDS = sorted(p.stem for p in FIXTURES.glob("*.json"))
HAND_WRITTEN = {"README.md"}


@pytest.fixture
def content(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURES, tmp_path / "npcs")
    return tmp_path


def files(directory: Path) -> set[str]:
    return {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}


def pixels(path: Path) -> list[bytes]:
    with Image.open(path) as image:
        return [frame.convert("RGBA").tobytes() for frame in ImageSequence.Iterator(image)]


def assert_phaser_atlas(path: Path) -> None:
    atlas = json.loads(path.read_text())
    assert isinstance(atlas["frames"], dict), path.name
    with Image.open(path.parent / atlas["meta"]["image"]) as image:
        assert atlas["meta"]["size"] == {"w": image.width, "h": image.height}, path.name
        for name, frame in atlas["frames"].items():
            r = frame["frame"]
            box = (r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])
            assert box[2] <= image.width and box[3] <= image.height, f"{path.name} {name}"
            assert image.crop(box).getbbox() is not None, f"{path.name} {name} is empty"
            assert frame["sourceSize"] == {"w": r["w"], "h": r["h"]}


def test_generate_writes_the_tileset_sprites_and_previews(content: Path) -> None:
    generate(content)

    art = content / "art"
    sprites = {f"characters/{i}.{ext}" for i in [*BUILTIN, *FIXTURE_IDS] for ext in ("png", "json")}
    previews = {f"preview/{name}" for name in ("tiles.png", "scene.png", "characters.png")}
    previews |= {"preview/walk.gif", "preview/npcs.png"}
    assert files(art) == {"tiles.png", "tiles.tsj", "tiles.md"} | sprites | previews

    tileset = json.loads((art / "tiles.tsj").read_text())
    with Image.open(art / tileset["image"]) as image:
        assert image.size == (tileset["imagewidth"], tileset["imageheight"])
    for character_id in [*BUILTIN, *FIXTURE_IDS]:
        assert_phaser_atlas(art / "characters" / f"{character_id}.json")


def test_every_npc_in_content_renders_a_phaser_atlas(tmp_path: Path) -> None:
    shutil.copytree(CONTENT_DIR / "npcs", tmp_path / "npcs")
    generate(tmp_path, npcs_only=True)

    for npc_id in load_npcs(CONTENT_DIR / "npcs"):
        assert_phaser_atlas(tmp_path / "art" / "characters" / f"{npc_id}.json")


def test_every_opaque_pixel_is_from_the_palette(content: Path) -> None:
    generate(content)
    palette = {(*rgb, 255) for rgb in RGB.values()}
    for path in [content / "art" / "tiles.png", *(content / "art" / "characters").glob("*.png")]:
        with Image.open(path) as image:
            colours = {c for _, c in image.convert("RGBA").getcolors(maxcolors=4096)}
        assert {c for c in colours if c[3] != 0} <= palette, path.name
        assert all(c[3] in (0, 255) for c in colours), path.name


def test_walk_preview_plays_every_direction(content: Path) -> None:
    generate(content)
    with Image.open(content / "art" / "preview" / "walk.gif") as gif:
        assert gif.n_frames == 8 * 2 * 4


def test_npcs_only_renders_just_the_npcs(content: Path) -> None:
    generate(content, npcs_only=True)

    expected = {f"characters/{i}.{ext}" for i in FIXTURE_IDS for ext in ("png", "json")}
    assert files(content / "art") == expected | {"preview/npcs.png"}


def test_regenerating_removes_sprites_for_npcs_that_are_gone(content: Path) -> None:
    generate(content)
    (content / "npcs" / "mei.json").unlink()
    (content / "art" / "characters" / "stray.png").write_bytes(b"")

    generate(content, npcs_only=True)

    sprites = files(content / "art" / "characters")
    assert "mei.png" not in sprites and "stray.png" not in sprites
    assert {"player.png", "suki.png"} <= sprites


def test_npcs_that_look_alike_get_different_accents(content: Path) -> None:
    npc = json.loads((FIXTURES / "mei.json").read_text())
    npc["appearance"]["accessories"] = ["cap"]
    for npc_id in ("lachlan", "tobias"):
        (content / "npcs" / f"{npc_id}.json").write_text(json.dumps(npc | {"id": npc_id}))

    generate(content, npcs_only=True)

    sprites = content / "art" / "characters"
    assert pixels(sprites / "lachlan.png") != pixels(sprites / "tobias.png")


def test_npc_ids_cannot_shadow_built_in_sprites(content: Path) -> None:
    npc = json.loads((FIXTURES / "mei.json").read_text())
    (content / "npcs" / "sample_coder.json").write_text(json.dumps(npc | {"id": "sample_coder"}))

    with pytest.raises(ValueError, match="sample_coder"):
        generate(content)


def test_generation_is_deterministic(tmp_path: Path, content: Path) -> None:
    generate(content)
    shutil.copytree(FIXTURES, tmp_path / "again" / "npcs")
    generate(tmp_path / "again")

    for name in files(content / "art"):
        first, second = content / "art" / name, tmp_path / "again" / "art" / name
        assert first.read_bytes() == second.read_bytes(), name


def test_art_command(content: Path) -> None:
    result = CliRunner().invoke(create_cli(), ["art", "--npcs", "--content", str(content)])

    assert result.exit_code == 0, result.output
    assert (content / "art" / "characters" / "mei.png").exists()
    assert not (content / "art" / "tiles.png").exists()


def is_npc_output(name: str) -> bool:
    path = Path(name)
    npc_sprite = path.parent.name == "characters" and path.stem not in BUILTIN
    return npc_sprite or name == "preview/npcs.png"


def test_committed_art_is_up_to_date(tmp_path: Path) -> None:
    generate(tmp_path)

    fresh, committed = tmp_path / "art", CONTENT_DIR / "art"
    stale = "content/art is out of date: run `cd server && uv run simile art`"
    built_in = {
        name
        for name in files(committed) - HAND_WRITTEN
        if not is_npc_output(name) and not name.startswith("iso/")
    }
    assert built_in == files(fresh), stale
    for name in files(fresh):
        if name.endswith((".png", ".gif")):
            assert pixels(committed / name) == pixels(fresh / name), f"{name}: {stale}"
        else:
            assert (committed / name).read_text() == (fresh / name).read_text(), f"{name}: {stale}"
