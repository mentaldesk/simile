from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from simile.art.palette import rgba

if TYPE_CHECKING:
    from PIL import Image

Colour = str | None


class Canvas:
    """A grid of palette colour names; None is transparent."""

    def __init__(self, width: int = 16, height: int = 16, fill: Colour = None) -> None:
        self.width = width
        self.height = height
        self.pixels: list[list[Colour]] = [[fill] * width for _ in range(height)]

    def get(self, x: int, y: int) -> Colour:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.pixels[y][x]
        return None

    def px(self, x: int, y: int, colour: Colour) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y][x] = colour

    def rect(self, x: int, y: int, w: int, h: int, colour: Colour) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, colour)

    def hline(self, x: int, y: int, w: int, colour: Colour) -> None:
        self.rect(x, y, w, 1, colour)

    def vline(self, x: int, y: int, h: int, colour: Colour) -> None:
        self.rect(x, y, 1, h, colour)

    def stamp(self, rows: Iterable[str], key: Mapping[str, Colour], x: int = 0, y: int = 0) -> None:
        """Draw ASCII art; characters missing from key are left untouched."""
        for dy, row in enumerate(rows):
            for dx, char in enumerate(row):
                if char in key:
                    self.px(x + dx, y + dy, key[char])

    def paste(self, other: Canvas, x: int = 0, y: int = 0) -> None:
        for dy, row in enumerate(other.pixels):
            for dx, colour in enumerate(row):
                if colour is not None:
                    self.px(x + dx, y + dy, colour)

    def recolour(self, mapping: Mapping[str, Colour]) -> None:
        self.pixels = [[mapping.get(c, c) if c else c for c in row] for row in self.pixels]

    def flipped(self) -> Canvas:
        out = Canvas(self.width, self.height)
        out.pixels = [list(reversed(row)) for row in self.pixels]
        return out

    def outlined(self, colour: str) -> Canvas:
        out = Canvas(self.width, self.height)
        out.pixels = [list(row) for row in self.pixels]
        for y in range(self.height):
            for x in range(self.width):
                if self.pixels[y][x] is None and any(
                    self.get(x + dx, y + dy) is not None
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                ):
                    out.pixels[y][x] = colour
        return out

    def colours(self) -> set[str]:
        return {c for row in self.pixels for c in row if c is not None}

    def to_image(self) -> Image.Image:
        from PIL import Image

        image = Image.new("RGBA", (self.width, self.height))
        image.putdata([rgba(c) if c else (0, 0, 0, 0) for row in self.pixels for c in row])
        return image


_GLYPHS = {
    "A": ".#.|#.#|###|#.#|#.#",
    "B": "##.|#.#|##.|#.#|##.",
    "C": ".##|#..|#..|#..|.##",
    "D": "##.|#.#|#.#|#.#|##.",
    "E": "###|#..|##.|#..|###",
    "F": "###|#..|##.|#..|#..",
    "G": ".##|#..|#.#|#.#|.##",
    "H": "#.#|#.#|###|#.#|#.#",
    "I": "###|.#.|.#.|.#.|###",
    "J": "..#|..#|..#|#.#|.#.",
    "K": "#.#|#.#|##.|#.#|#.#",
    "L": "#..|#..|#..|#..|###",
    "M": "#.#|###|###|#.#|#.#",
    "N": "##.|#.#|#.#|#.#|#.#",
    "O": ".#.|#.#|#.#|#.#|.#.",
    "P": "##.|#.#|##.|#..|#..",
    "Q": ".#.|#.#|#.#|##.|.##",
    "R": "##.|#.#|##.|#.#|#.#",
    "S": ".##|#..|.#.|..#|##.",
    "T": "###|.#.|.#.|.#.|.#.",
    "U": "#.#|#.#|#.#|#.#|###",
    "V": "#.#|#.#|#.#|#.#|.#.",
    "W": "#.#|#.#|###|###|#.#",
    "X": "#.#|#.#|.#.|#.#|#.#",
    "Y": "#.#|#.#|.#.|.#.|.#.",
    "Z": "###|..#|.#.|#..|###",
    "0": "###|#.#|#.#|#.#|###",
    "1": ".#.|##.|.#.|.#.|###",
    "2": "##.|..#|.#.|#..|###",
    "3": "##.|..#|.#.|..#|##.",
    "4": "#.#|#.#|###|..#|..#",
    "5": "###|#..|##.|..#|##.",
    "6": ".##|#..|###|#.#|###",
    "7": "###|..#|.#.|.#.|.#.",
    "8": "###|#.#|###|#.#|###",
    "9": "###|#.#|###|..#|##.",
    "-": "...|...|###|...|...",
    "_": "...|...|...|...|###",
    ".": "...|...|...|...|.#.",
    ",": "...|...|...|.#.|#..",
    ":": "...|.#.|...|.#.|...",
    "/": "..#|..#|.#.|#..|#..",
    "(": ".#.|#..|#..|#..|.#.",
    ")": ".#.|..#|..#|..#|.#.",
    "+": "...|.#.|###|.#.|...",
    "=": "...|###|...|###|...",
    "'": ".#.|.#.|...|...|...",
    " ": "...|...|...|...|...",
}
GLYPH_WIDTH = 3
GLYPH_HEIGHT = 5


def text_width(text: str) -> int:
    return max(len(text) * (GLYPH_WIDTH + 1) - 1, 0)


def draw_text(canvas: Canvas, text: str, x: int, y: int, colour: str) -> None:
    for i, char in enumerate(text.upper()):
        rows = _GLYPHS.get(char, _GLYPHS[" "]).split("|")
        canvas.stamp(rows, {"#": colour}, x + i * (GLYPH_WIDTH + 1), y)
