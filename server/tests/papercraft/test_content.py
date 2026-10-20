import json

import pytest
from PIL import Image

from simile.papercraft.build import CONTENT, MANIFEST, PPM, Build
from simile.papercraft.catalogue import paintings

BUDGET = 12_000_000
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
    if entry["kind"] in ("layer", "strip", "ground"):
        assert image.mode == "RGBA"


def test_every_lookup_names_a_piece() -> None:
    named = [
        *(key for layers in MANIFEST_JSON["streets"].values() for key in layers.values()),
        *MANIFEST_JSON["grounds"].values(),
        *(key for b in MANIFEST_JSON["buildings"].values() for key in (b["front"], b["glow"])),
        *(key for b in MANIFEST_JSON["buildings"].values() for key in b["floors"]),
        *(f["piece"] for f in MANIFEST_JSON["furniture"].values()),
        *(k for f in MANIFEST_JSON["furniture"].values() for k in f.get("variants", {}).values()),
        *MANIFEST_JSON["platforms"].values(),
        MANIFEST_JSON["slab"],
    ]

    assert set(named) <= set(PIECES)
