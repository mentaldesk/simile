import json

import numpy as np
import pytest
from PIL import Image, ImageFilter

from simile.papercraft.build import CONTENT, MANIFEST, PPM, Build
from simile.papercraft.catalogue import paintings

BUDGET = 12_000_000
SOLID = 200
"""The least alpha well inside a machine: the lossy save softens it a little."""
MANIFEST_JSON = json.loads((CONTENT / MANIFEST).read_text())
PIECES = MANIFEST_JSON["pieces"]


def test_content_papercraft_stays_within_its_budget() -> None:
    size = sum(p.stat().st_size for p in CONTENT.rglob("*") if p.is_file())

    assert size < BUDGET, f"content/papercraft/ is {size / 1e6:.1f} MB"


def test_every_piece_the_village_needs_is_painted_and_up_to_date() -> None:
    build = Build()

    assert set(PIECES) == {p.key for p in paintings()}
    assert [p.key for p in build.stale(MANIFEST_JSON, build.pieces)] == []


@pytest.mark.parametrize("key", sorted(PIECES))
def test_each_piece_is_a_webp_of_the_size_and_scale_its_entry_gives(key: str) -> None:
    entry = PIECES[key]
    image = Image.open(CONTENT / entry["file"])

    assert image.format == "WEBP"
    assert list(image.size) == entry["size"]
    if entry["kind"] in ("sprite", "front"):
        assert image.mode == "RGBA"
        assert entry["size"][1] / entry["height"] == pytest.approx(PPM, rel=0.01)
        assert 0 <= entry["anchor"][0] <= 1 and 0 < entry["anchor"][1] <= 1
    if entry["kind"] == "landmark":
        assert entry["anchor"][0] == 0.5 and 0.9 < entry["anchor"][1] <= 1
    if entry["kind"] in ("layer", "strip"):
        assert image.mode == "RGBA"


VILLAGE_GROUNDS = {*MANIFEST_JSON["grounds"].values()} | {
    layers["ground"] for layers in MANIFEST_JSON["streets"].values() if "city" in layers
}


@pytest.mark.parametrize("key", sorted(VILLAGE_GROUNDS))
def test_the_ground_strips_are_opaque(key: str) -> None:
    image = Image.open(CONTENT / PIECES[key]["file"]).convert("RGBA")

    assert image.getchannel("A").getextrema()[0] == 255


def test_every_lookup_names_a_piece() -> None:
    named = [
        *(key for layers in MANIFEST_JSON["streets"].values() for key in layers.values()),
        *MANIFEST_JSON["grounds"].values(),
        *(key for b in MANIFEST_JSON["buildings"].values() for key in (b["front"], b["glow"])),
        *(key for b in MANIFEST_JSON["buildings"].values() for key in b["floors"]),
        *(f["piece"] for f in MANIFEST_JSON["furniture"].values()),
        *(k for f in MANIFEST_JSON["furniture"].values() for k in f.get("variants", {}).values()),
        *MANIFEST_JSON["platforms"].values(),
        *(key for below in MANIFEST_JSON["platforms_below"].values() for key in below.values()),
        MANIFEST_JSON["slab"],
        *(
            key
            for m in MANIFEST_JSON.get("landmarks", {}).values()
            for key in (m["piece"], m["glow"])
        ),
    ]

    assert set(named) <= set(PIECES)


LADDERS = [
    MANIFEST_JSON["platforms"]["ladder"],
    *(p["ladder"] for p in MANIFEST_JSON["platforms_below"].values() if "ladder" in p),
]
RAIL_M = 0.08
RUNG_M = 0.3
"""How wide the sketch draws each rail, and how far apart its rungs."""


@pytest.mark.parametrize("key", LADDERS)
def test_a_ladders_rails_and_rungs_are_opaque(key: str) -> None:
    alpha = np.asarray(Image.open(CONTENT / PIECES[key]["file"]).convert("RGBA"))[..., 3]
    width = alpha.shape[1]
    across = np.median(alpha[:, width // 3 : 2 * width // 3], axis=1) >= 250
    rungs = np.count_nonzero(np.diff(across.astype(int)) == 1)

    for side in (alpha[:, : width // 4], alpha[:, -(width // 4) :]):
        assert (np.median(side, axis=0) >= 250).sum() >= RAIL_M * PPM / 2
    assert rungs >= round(PIECES[key]["height"] / RUNG_M) - 1


@pytest.mark.parametrize("name", ["clean_lockers", "recycler", "recycler-broken"])
def test_a_solid_machine_has_nothing_see_through_inside_it(name: str) -> None:
    with Image.open(CONTENT / "furniture" / f"{name}.webp") as image:
        alpha = np.pad(np.asarray(image.convert("RGBA").getchannel("A")), 8)
    drawn = Image.fromarray(((alpha > 8) * 255).astype(np.uint8))
    inside = np.asarray(drawn.filter(ImageFilter.MinFilter(9))) > 0

    assert alpha[inside].min() >= SOLID
