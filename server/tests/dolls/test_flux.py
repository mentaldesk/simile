import pytest

from simile.characters.palette import PLAYER
from simile.dolls.figure import edit_prompt, stand_prompt
from simile.dolls.flux import Flux


@pytest.mark.mlx
def test_paints_from_text_then_edits_the_painting() -> None:
    pytest.importorskip("mflux")
    from simile.works.config import DEFAULT_CONFIG
    from simile.works.flux import downloaded

    if downloaded(DEFAULT_CONFIG.image_model) is None:
        pytest.skip(f"{DEFAULT_CONFIG.image_model} isn't downloaded")

    with Flux() as painter:
        stand = painter.paint(stand_prompt(PLAYER, "player"), (256, 352), 1)
        sit = painter.paint(edit_prompt("sit", PLAYER, "player"), (256, 352), 1, [stand])

    assert stand.size == sit.size == (256, 352)
    assert stand.tobytes() != sit.tobytes()
