from pathlib import Path

import pytest

from simile.art.characters import PLAYER
from simile.dolls.look import Look
from simile.dolls.paint import prompt
from simile.dolls.sheet import sheet


@pytest.mark.mlx
def test_flux_paints_over_a_sheet_in_edit_mode(tmp_path: Path) -> None:
    pytest.importorskip("mflux")
    from simile.dolls.flux import MODEL, FluxEdit
    from simile.works.flux import downloaded

    if downloaded(MODEL) is None:
        pytest.skip(f"{MODEL} isn't downloaded")
    look = Look.of(PLAYER, "player")
    path = tmp_path / "sheet.png"
    flat = sheet("side", look).image().resize((512, 384))
    flat.save(path)

    with FluxEdit(steps=2) as flux:
        painted = flux.paint(prompt("side", PLAYER, "player"), [path], (512, 384), 1)

    assert painted.size == (512, 384)
    assert painted.tobytes() != flat.tobytes()
