"""What the painter is asked for, and the interface it paints through. Never imports MLX."""

import zlib
from importlib.util import find_spec
from pathlib import Path
from typing import Protocol

from PIL import Image

from simile.papercraft.painter import EditPainter as Papercraft
from simile.papercraft.painter import styled
from simile.schema import Appearance

SKIN = {
    "cream": "pale",
    "peach": "light",
    "sand": "golden tan",
    "tan": "light brown",
    "brown": "brown",
    "umber": "dark brown",
}
HAIR = {
    "ink": "black",
    "night": "black",
    "espresso": "dark brown",
    "umber": "reddish brown",
    "brown": "chestnut",
    "maroon": "dark red",
    "concrete": "grey",
    "steel": "grey",
    "pavement": "silver-grey",
    "white": "white",
    "cream": "blonde",
    "sand": "sandy blonde",
    "yellow": "blonde",
    "amber": "golden",
}
STYLES = {
    "buzz": "very short cropped {} hair",
    "short": "short {} hair",
    "curly": "curly {} hair",
    "bob": "{} hair cut in a bob",
    "long": "long {} hair",
    "ponytail": "{} hair in a ponytail",
    "bun": "{} hair in a bun",
}


class SheetPainter(Protocol):
    """Paints over a sheet in edit mode: `images[0]` is the sheet, the rest style references.
    Returns a picture of `size`."""

    def paint(
        self, prompt: str, images: list[Path], size: tuple[int, int], seed: int
    ) -> Image.Image: ...


CLOTH = {
    "ink": "black",
    "night": "dark navy",
    "slate": "slate blue",
    "steel": "blue-grey",
    "concrete": "grey",
    "pavement": "pale grey",
    "ice": "pale blue",
    "sand": "tan",
    "umber": "brown",
    "espresso": "dark brown",
    "maroon": "dark red",
    "amber": "golden yellow",
    "lime": "lime green",
    "forest": "dark green",
    "deep": "dark teal",
    "cyan": "turquoise",
    "neon": "hot pink",
}
WEARS = {
    "glasses": "round glasses",
    "sunglasses": "dark sunglasses",
    "cap": "{a_accent} cap",
    "beanie": "{a_accent} beanie",
    "headphones": "{accent} headphones",
    "scarf": "{a_accent} scarf",
    "backpack": "{a_accent} backpack",
    "apron": "{a_apron} apron",
}


def an(word: str) -> str:
    return f"{'an' if word[0] in 'aeiou' else 'a'} {word}"


def named(hex_colour: str, names: dict[str, str]) -> str:
    from simile.art.palette import PALETTE, hex_to_rgb, nearest

    name = nearest(hex_to_rgb(hex_colour), tuple(PALETTE))
    return names.get(name, name)


def person(appearance: Appearance, who: str | None) -> str:
    """The resident in words, so the painter keeps their skin, hair and accessories. Naming
    their clothes makes it paint the rest of them."""
    from simile.art.characters import Colours
    from simile.art.palette import PALETTE

    style = appearance.hair_style.value
    hair = (
        "a bald head"
        if style == "bald"
        else STYLES[style].format(named(appearance.hair_colour, HAIR))
    )
    sprite = Colours.of(appearance, seed=who)
    accent = named(PALETTE[sprite.accent], CLOTH)
    colours = {
        "accent": accent,
        "a_accent": an(accent),
        "a_apron": an(named(PALETTE[sprite.apron], CLOTH)),
    }
    worn = [WEARS[a.value].format(**colours) for a in appearance.accessories]
    wears = f", and wears {' and '.join(worn)}" if worn else ""
    return f"The person has {named(appearance.skin, SKIN)} skin and {hair}{wears}."


def back_of_head(appearance: Appearance) -> str:
    hat = next((a.value for a in appearance.accessories if a.value in ("cap", "beanie")), None)
    if hat:
        return f"the back of the {hat} over the hair, and no face"
    return "with no face" if appearance.hair_style.value == "bald" else "all hair and no face"


def prompt(sheet: str, appearance: Appearance, who: str | None) -> str:
    if sheet == "side":
        layout = "a face drawn on the head in profile."
    else:
        layout = (
            "the head on the left faces the viewer with the face drawn on it, the head on the "
            f"right is the back of the same head, {back_of_head(appearance)}, and between them "
            "are the front and the back of the torso alone, with no head, arms or legs."
        )
    return styled(
        "Redraw image 1 as paper doll parts cut from coloured paper and card in the style of the "
        f"villagers in image 2: visible paper fibres and texture, cut card edges, {layout} "
        f"{person(appearance, who)} Keep every piece exactly where it is, with the same outline "
        "and the same colours, and add nothing to it, on a plain light grey background."
    )


def seed(who: str, sheet: str, reroll: int = 0) -> int:
    return zlib.crc32(f"{who}/{sheet}/{reroll}".encode()) % 2**31


class NoPainter(RuntimeError):
    """This machine can't paint dolls: FLUX needs Apple Silicon and the `images` extra."""


class EditPainter:
    """Part 3's edit-mode painter, `simile.papercraft.painter.EditPainter`, behind
    `SheetPainter`: FLUX.2 [klein] 4B at 8-bit, on Apple Silicon with the `images` extra. Loads
    on entering and unloads on leaving."""

    def __init__(self) -> None:
        if find_spec("mflux") is None:
            raise NoPainter(
                "Painting dolls needs FLUX: on Apple Silicon, `uv sync --extra images`."
            )
        self._painter = Papercraft()

    def __enter__(self) -> "EditPainter":
        self._painter.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._painter.__exit__(*exc_info)

    def paint(
        self, prompt: str, images: list[Path], size: tuple[int, int], seed: int
    ) -> Image.Image:
        pictures = [Image.open(path).convert("RGB") for path in images]
        return self._painter.paint(prompt, size, seed, pictures)


class FakeSheetPainter:
    """Returns the sheet itself, lightly mottled, without a model: for tests and dry runs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def paint(
        self, prompt: str, images: list[Path], size: tuple[int, int], seed: int
    ) -> Image.Image:
        import numpy as np

        self.calls.append((prompt, seed))
        sheet = np.asarray(Image.open(images[0]).convert("RGB").resize(size), dtype=np.float64)
        noise = np.random.default_rng(seed).normal(0, 6, sheet.shape[:2])[..., None]
        return Image.fromarray(np.clip(sheet * 0.94 + noise, 0, 255).astype(np.uint8))
