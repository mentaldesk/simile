import json

import numpy as np
import pytest
from PIL import Image

from simile.art.iso import characters, formats
from simile.art.iso.lighting import SETS

FOLDER = characters.CONTENT_DIR / "art" / "iso" / "characters"
STALE = (
    "content/art/iso/characters is out of date: run `cd server && uv run simile art iso characters`"
)
PINNED_SOURCES = "65cf408cb78b04ce"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((FOLDER / characters.MANIFEST).read_text())


@pytest.fixture(scope="module")
def sheets(manifest: dict) -> dict[str, np.ndarray]:
    out = {}
    for key, sheet in manifest["characters"].items():
        with Image.open(FOLDER / sheet["image"]) as image:
            assert image.mode == "RGBA", key
            out[key] = np.asarray(image)
    return out


def test_every_resident_and_the_player_has_an_up_to_date_sheet(manifest: dict) -> None:
    residents = characters.residents(characters.CONTENT_DIR)
    assert list(manifest["characters"]) == list(residents), STALE
    for key, character in residents.items():
        assert manifest["characters"][key]["hash"] == characters.character_hash(character), STALE
    assert manifest["constants_hash"] == characters.constants_hash(residents[characters.PROBE])


def test_the_layout_and_animations_are_the_pipelines(manifest: dict) -> None:
    layout = characters.layout()
    assert {key: manifest[key] for key in layout} == layout, STALE


def test_the_folder_holds_the_manifest_and_its_sheets(manifest: dict) -> None:
    used = {characters.MANIFEST} | {s["image"] for s in manifest["characters"].values()}
    assert {p.name for p in FOLDER.iterdir()} == used


def test_sheets_are_lossless_in_the_character_format(manifest: dict) -> None:
    for sheet in manifest["characters"].values():
        assert sheet["image"].endswith(f".{formats.CHARACTERS.ext}")
        data = (FOLDER / sheet["image"]).read_bytes()
        if sheet["image"].endswith(".webp"):
            assert b"VP8L" in data and b"VP8 " not in data, sheet["image"]


def test_each_sheet_is_a_grid_of_frames(manifest: dict, sheets: dict[str, np.ndarray]) -> None:
    f, cols = manifest["frame"], manifest["columns"]
    for key, pixels in sheets.items():
        sheet = manifest["characters"][key]
        assert pixels.shape == (sheet["height"], sheet["width"], 4)
        assert (sheet["width"], sheet["height"]) == (cols * f["width"], 8 * f["height"])


def test_every_frame_stands_on_its_anchor_and_stays_inside(
    manifest: dict, sheets: dict[str, np.ndarray]
) -> None:
    f, cols = manifest["frame"], manifest["columns"]
    w, h = f["width"], f["height"]
    ax, ay = f["anchor"]
    for key, pixels in sheets.items():
        for index in range(cols * 8):
            row, col = divmod(index, cols)
            alpha = pixels[row * h : (row + 1) * h, col * w : (col + 1) * w, 3]
            assert alpha[ay - 40 : ay - 25, ax - 12 : ax + 12].max() == 255, (key, index)
            assert not alpha[0].any() and not alpha[:, 0].any() and not alpha[:, -1].any()
            assert not alpha[-1].any(), (key, index)
            ys = np.nonzero(alpha.max(axis=1) > 128)[0]
            assert ys.max() >= ay - 4, (key, index)


def test_no_frame_has_unlit_patches(sheets: dict[str, np.ndarray]) -> None:
    for key, pixels in sheets.items():
        unlit = (pixels[..., :3].max(axis=2) == 0) & (pixels[..., 3] == 255)
        assert not unlit.any(), f"{key}: {unlit.sum()} unlit px, a render glitch; rerun --force"


def test_walk_frames_differ_and_idle_frames_breathe(
    manifest: dict, sheets: dict[str, np.ndarray]
) -> None:
    f, cols = manifest["frame"], manifest["columns"]
    w, h = f["width"], f["height"]
    pixels = sheets["player"]

    def frame(index: int) -> np.ndarray:
        row, col = divmod(index, cols)
        return pixels[row * h : (row + 1) * h, col * w : (col + 1) * w].astype(int)

    for animation in ("walk", "idle"):
        for indices in manifest["animations"][animation]["frames"].values():
            frames = [frame(i) for i in indices]
            for a, b in zip(frames, frames[1:], strict=False):
                assert np.abs(a - b).max() > 0


def test_the_per_set_constants_follow_the_lighting_sets(manifest: dict) -> None:
    sets = manifest["sets"]
    assert list(sets) == list(SETS)
    for name, light in SETS.items():
        s = sets[name]
        assert s["sun"] == {"azimuth": light.azimuth, "elevation": light.elevation}
        geometry = characters.shadow(light.azimuth, light.elevation)
        assert {k: s["shadow"][k] for k in geometry} == geometry
        assert all(0 < c <= 1 for c in s["tint"])
        assert 0.3 < s["shadow"]["strength"] < 0.9
    assert sum(sets["night"]["tint"]) < sum(sets["evening"]["tint"]) < sum(sets["morning"]["tint"])
    assert sets["night"]["tint"][2] > sets["night"]["tint"][0]
    assert sets["evening"]["tint"][0] > sets["evening"]["tint"][2]


def test_the_readme_lists_the_per_set_constants(manifest: dict) -> None:
    readme = (characters.SIMILE / "art" / "iso" / "README.md").read_text()
    for name, s in manifest["sets"].items():
        row = f"| `{name}` | {', '.join(str(c) for c in s['tint'])} | {s['shadow']['strength']} |"
        assert row in readme, f"update the table in simile/art/iso/README.md: {row}"


def test_the_pipeline_code_is_pinned() -> None:
    changed = (
        "The character pipeline's code changed. If the sheets would change, bump "
        "PIPELINE_VERSION in simile/art/iso/characters.py and rerun "
        "`uv run simile art iso characters`; either way, update the pin here."
    )
    assert characters.sources_digest() == PINNED_SOURCES, changed
