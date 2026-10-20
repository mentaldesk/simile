import pytest
from PIL import Image

from simile.papercraft.painter import NO_TEXT, REFERENCES, STYLE, EditPainter, reference, styled
from simile.works.config import DEFAULT_CONFIG

NAMES = ("street", "house", "rooftops", "furniture", "characters")


def test_the_references_live_in_content() -> None:
    assert sorted(p.stem for p in REFERENCES.glob("*.jpg")) == sorted(NAMES)
    assert REFERENCES.parts[-2:] == ("papercraft", "references")


@pytest.mark.parametrize("name", NAMES)
def test_a_reference_is_scaled_to_a_size_flux_reads(name: str) -> None:
    image = reference(name, 512)

    assert image.width == 512 and image.height % 16 == 0


def test_a_styled_prompt_asks_for_papercraft_and_no_lettering() -> None:
    prompt = styled("A teapot.")

    assert prompt.startswith("A teapot.") and STYLE in prompt and prompt.endswith(NO_TEXT)


def test_edit_mode_needs_an_image_to_paint_from() -> None:
    with pytest.raises(ValueError, match="at least one image"):
        EditPainter().paint("A teapot.", (256, 256), 1, [])


@pytest.mark.mlx
def test_flux_paints_in_edit_mode_from_a_reference() -> None:
    pytest.importorskip("mflux")
    from simile.works.flux import downloaded

    if downloaded(DEFAULT_CONFIG.image_model) is None:
        pytest.skip(f"{DEFAULT_CONFIG.image_model} isn't downloaded")

    with EditPainter(steps=2) as painter:
        picture = painter.paint(
            styled("A red teapot on a plain white background."),
            (256, 240),
            1,
            [reference("furniture", 256)],
        )

    assert picture.size == (256, 240)
    assert len(picture.getcolors(256 * 240) or []) > 100
    assert isinstance(picture, Image.Image)
