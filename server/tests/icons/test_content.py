import json

import numpy as np
import pytest
from PIL import Image

from simile.icons.build import CONTENT, MANIFEST, SIDE, fingerprint
from simile.icons.catalogue import ICONS

BUDGET = 1024 * 1024
PREVIEW = "preview.webp"


def entries() -> dict:
    return json.loads((CONTENT / MANIFEST).read_text())["icons"]


def test_content_icons_stay_within_budget() -> None:
    assert sum(path.stat().st_size for path in CONTENT.rglob("*") if path.is_file()) < BUDGET


def test_every_icon_in_the_catalogue_is_painted_and_nothing_else() -> None:
    assert list(entries()) == list(ICONS)
    painted = {path.name for path in CONTENT.glob("*.webp")} - {PREVIEW}
    assert painted == {entry["file"] for entry in entries().values()}


@pytest.mark.parametrize("name", ICONS)
def test_every_icon_is_painted_from_its_catalogue_entry(name: str) -> None:
    entry = entries()[name]
    image = Image.open(CONTENT / entry["file"])

    assert entry["hash"] == fingerprint(ICONS[name]), "run `uv run simile icons paint`"
    assert list(image.size) == entry["size"]
    assert max(image.size) <= SIDE + 4
    assert (np.asarray(image.convert("RGBA").getchannel("A")) >= 128).mean() > 0.15
