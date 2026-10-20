from pathlib import Path

import pytest

from simile.characters.palette import PLAYER
from simile.dolls.look import Look
from simile.dolls.paint import EditPainter, prompt
from simile.dolls.sheet import sheet


@pytest.mark.mlx
def test_part_3s_painter_paints_over_a_sheet(tmp_path: Path) -> None:
    pytest.importorskip("mflux")
    from simile.works.config import DEFAULT_CONFIG
    from simile.works.flux import downloaded

    if downloaded(DEFAULT_CONFIG.image_model) is None:
        pytest.skip(f"{DEFAULT_CONFIG.image_model} isn't downloaded")
    path = tmp_path / "sheet.png"
    flat = sheet("side", Look.of(PLAYER, "player")).image().resize((512, 384))
    flat.save(path)

    with EditPainter() as painter:
        painted = painter.paint(prompt("side", PLAYER, "player"), [path], (512, 384), 1)

    assert painted.size == (512, 384)
    assert painted.tobytes() != flat.tobytes()
